#! /usr/bin/env python
# gee_math/earthquake_dpm_math.py
"""Coherence-loss damage proxy map (DPM) for the Aug 10 2026 M7.4 Eje Cafetero
earthquake, under the frozen rules of docs/designs/bailasar.md (Hazard 2) and
the pre-registered thresholds in config/preregistered.yaml.

Pure functions (no IO, no network), unit-tested in tests/test_earthquake_dpm.py:
    delta_gamma        Δγ = γ_R − γ_C, unclamped, NaN-preserving
    classify_coverage  built-up (≥ 50% footprint coverage) / non-built (≤ 10%),
                       fractions from config/preregistered.yaml, never hardcoded
    gunw_mask_flags    JPL D-102272 p.44 three-digit mask: [water|ref-subswath|
                       sec-subswath], fill 255
    valid_pixels       finite Δγ, not vegetation/water/GUNW-invalid/layover
    standardize        μ, σ over valid NON-BUILT pixels; Z = (Δγ−μ)/σ
    dpm_from_z         DPM = max(Z, 0), clamped AFTER standardization
    unit_stats / evaluate_units  barrio DPM_u = median Z of built-up pixels,
                       units with < min_built_up_pixels_per_unit excluded+counted
    run_dpm_pass       one DPM pass; the identical code path runs the co-event
                       pass (ref=R, cmp=C) and the control pass (ref=K, cmp=R)

The layover/shadow mask required by the design does not exist in the NISAR GUNW
product (verified against JPL D-102272 Rev E p.44 and the real granules: the GUNW
`mask` is water + subswath validity, not layover/shadow). It is recorded as
`missing` in provenance and never replaced with invented values.

CLI (network + GEE): python -m gee_math.earthquake_dpm_math --track 11
    streams only the AOI window of coherenceMagnitude at 20 m posting from the
    GUNW HDF5 files via h5py + fsspec (Earthdata token), computes R, C, K on one
    grid, and writes local_cache/quake/dpm_track<N>.zarr plus
    local_cache/quake/barrio_dpm.parquet. C-pair statistics are computed and
    stored only (validation/README.md pre-registration pending); they are never
    interpreted by this code.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import struct
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
PREREG_PATH = ROOT / "config" / "preregistered.yaml"
OPS_PATH = ROOT / "config" / "bailasar.yaml"
ENV_PATH = ROOT / ".env"
CACHE_DIR = ROOT / "local_cache" / "quake"

EVENT_DATE = "2026-08-10"
# AOI fallback (estimate) from the hour-2 gate brief while
# config/bailasar.yaml aois.2_eje_cafetero_quake is null (estimate, not frozen).
EJE_CAFETERO_AOI_ESTIMATE = [-75.85, 4.40, -75.40, 5.15]  # [W, S, E, N] EPSG:4326

# GUNW product layout verified against NISAR_L2_PR_GUNW_026_011_D_086_028_*_001
# (productSpecificationVersion 1.5.0) and JPL D-102272 Rev E p.44: the 20 m
# coherence is in wrappedInterferogram/<pol>/, the 80 m one in
# unwrappedInterferogram/<pol>/. Mask values are [water][ref subswath][sec
# subswath] digits, fill 255, valid_max 155.
GUNW_GRIDS = "/science/LSAR/GUNW/grids/frequencyA"
GUNW_COH_20M_GROUP = "wrappedInterferogram"
GUNW_POL = "HH"
GUNW_BASE_URL = "https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GUNW_PROVISIONAL_V1"

# Earth Engine public assets (operational choices, not frozen thresholds).
VIDA_ASSET = "projects/sat-io/open-datasets/VIDA_COMBINED/COL"
WORLDCOVER_ASSET = "ESA/WorldCover/v200"
WORLDCOVER_WATER_CLASS = 80
WORLDCOVER_VEGETATION_CLASSES = (10, 20, 30, 40, 90, 95, 100)
UNIT_ASSETS = ("FAO/GAUL/2025/level2", "FAO/GAUL/2015/level2")
UNIT_FALLBACK_LABEL = (
    "municipio (FAO GAUL ADM2 fallback; official barrio/vereda polygons pending "
    "per validation/README.md)"
)
FOOTPRINT_FINE_SCALE_M = 5.0

PREREG_QUAKE_KEYS = (
    "built_up_min_footprint_fraction",
    "non_built_max_footprint_fraction",
    "min_built_up_pixels_per_unit",
)


def load_quake_prereg(path: Path | None = None) -> dict:
    """Read the frozen quake thresholds with yaml.safe_load; never defaults."""
    cfg = yaml.safe_load((path or PREREG_PATH).read_text(encoding="utf-8"))
    quake = cfg["quake"]
    missing = [k for k in PREREG_QUAKE_KEYS if k not in quake]
    if missing:
        raise KeyError(f"config/preregistered.yaml quake block is missing {missing}")
    return {
        "built_up_min_footprint_fraction": float(quake["built_up_min_footprint_fraction"]),
        "non_built_max_footprint_fraction": float(quake["non_built_max_footprint_fraction"]),
        "min_built_up_pixels_per_unit": int(quake["min_built_up_pixels_per_unit"]),
        "status": cfg.get("status", "?"),
    }


def git_blob_sha1(path: Path) -> str:
    """git hash-object equivalent (sha1 of the blob header + bytes)."""
    blob = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(blob) + blob).hexdigest()


def delta_gamma(gamma_ref: np.ndarray, gamma_cmp: np.ndarray) -> np.ndarray:
    """Δγ = γ_R − γ_C unclamped; NaN anywhere stays NaN (no zero-fill)."""
    return np.asarray(gamma_ref, dtype=np.float64) - np.asarray(gamma_cmp, dtype=np.float64)


def classify_coverage(
    coverage: np.ndarray,
    built_up_min_fraction: float,
    non_built_max_fraction: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Built-up ≥ built_up_min_fraction (inclusive), non-built ≤ max (inclusive);
    anything between (and NaN coverage, never filled) is neither."""
    cov = np.asarray(coverage, dtype=np.float64)
    finite = np.isfinite(cov)
    built = finite & (cov >= built_up_min_fraction)
    non_built = finite & (cov <= non_built_max_fraction)
    return built, non_built


def gunw_mask_flags(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """GUNW grid mask (JPL D-102272 p.44): each value is [water][ref subswath]
    [sec subswath] digits; 255 = fill. Returns (valid_samples, water)."""
    m = np.asarray(mask)
    fill = m == 255
    water = (m >= 100) & (m < 200)
    valid = (((m // 10) % 10) > 0) & ((m % 10) > 0) & ~fill
    return valid, water


def valid_pixels(
    delta: np.ndarray,
    vegetation: np.ndarray | None,
    water: np.ndarray | None,
    gunw_valid: np.ndarray | None,
    layover_shadow: np.ndarray | None = None,
) -> np.ndarray:
    """A pixel is valid if Δγ is finite and no mask excludes it. A layover/shadow
    layer left as None (the GUNW product has none) does not exclude pixels."""
    valid = np.isfinite(np.asarray(delta, dtype=np.float64))
    if vegetation is not None:
        valid &= ~np.asarray(vegetation, dtype=bool)
    if water is not None:
        valid &= ~np.asarray(water, dtype=bool)
    if gunw_valid is not None:
        valid &= np.asarray(gunw_valid, dtype=bool)
    if layover_shadow is not None:
        valid &= ~np.asarray(layover_shadow, dtype=bool)
    return valid


def standardize(
    delta: np.ndarray, reference_mask: np.ndarray
) -> tuple[np.ndarray, float, float, int]:
    """μ, σ (population SD, ddof=0) over valid non-built pixels; Z = (Δγ−μ)/σ.
    If n < 2 or σ <= 0, Z is NaN everywhere (undefined, never zero-filled)."""
    d = np.asarray(delta, dtype=np.float64)
    ref = np.asarray(reference_mask, dtype=bool)
    values = d[ref & np.isfinite(d)]
    n = int(values.size)
    if n < 2:
        return np.full(d.shape, np.nan), float("nan"), float("nan"), n
    mu = float(values.mean())
    sigma = float(values.std(ddof=0))
    if not (sigma > 0.0) or not math.isfinite(sigma):
        return np.full(d.shape, np.nan), mu, sigma, n
    z = (d - mu) / sigma
    z[~np.isfinite(d)] = np.nan
    return z, mu, sigma, n


def dpm_from_z(z: np.ndarray) -> np.ndarray:
    """DPM = max(Z, 0): the clamp happens after standardization."""
    return np.maximum(np.asarray(z, dtype=np.float64), 0.0)


def median_of(z: np.ndarray, selection: np.ndarray) -> float:
    """NaN-ignoring median of z over selection pixels; NaN if none are finite."""
    vals = np.asarray(z, dtype=np.float64)[np.asarray(selection, dtype=bool)]
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return float("nan")
    return float(np.median(vals))


def unit_stats(
    z: np.ndarray,
    unit_ids: np.ndarray,
    selection: np.ndarray,
) -> dict[int, dict]:
    """Per-unit median Z (DPM_u) over selected pixels with finite Z.
    Returns {unit_id: {'median_z': float, 'n_px': int}}."""
    z = np.asarray(z, dtype=np.float64)
    ids = np.asarray(unit_ids)
    sel = np.asarray(selection, dtype=bool) & np.isfinite(z)
    out: dict[int, dict] = {}
    for uid in np.unique(ids[sel]):
        if uid == 0:
            continue
        vals = z[sel & (ids == uid)]
        out[int(uid)] = {"median_z": float(np.median(vals)), "n_px": int(vals.size)}
    return out


def evaluate_units(
    stats: dict[int, dict],
    min_built_up_pixels: int,
    all_unit_ids: list[int] | None = None,
) -> tuple[list[int], list[int]]:
    """A unit is evaluated only if it has >= min_built_up_pixels selected pixels.
    Units absent from stats (zero valid built-up pixels) count as excluded too,
    so every rasterized unit is either evaluated or explicitly excluded."""
    ids = sorted(all_unit_ids) if all_unit_ids is not None else sorted(stats)
    evaluated: list[int] = []
    excluded: list[int] = []
    for uid in ids:
        n_px = stats.get(uid, {}).get("n_px", 0)
        (evaluated if n_px >= min_built_up_pixels else excluded).append(uid)
    return evaluated, excluded


def run_dpm_pass(
    gamma_ref: np.ndarray,
    gamma_cmp: np.ndarray,
    coverage: np.ndarray,
    vegetation: np.ndarray,
    water: np.ndarray,
    gunw_mask: np.ndarray,
    unit_ids: np.ndarray,
    thresholds: dict,
    layover_shadow: np.ndarray | None = None,
    unit_names: dict[int, str] | None = None,
    label: str = "C",
) -> dict:
    """One full DPM pass. The co-event pass uses gamma_ref=γ_R, gamma_cmp=γ_C;
    the control pass is the identical code with gamma_ref=γ_K, gamma_cmp=γ_R.
    Nothing here interprets the result: it computes, labels and returns it."""
    delta = delta_gamma(gamma_ref, gamma_cmp)
    built, non_built = classify_coverage(
        coverage,
        thresholds["built_up_min_footprint_fraction"],
        thresholds["non_built_max_footprint_fraction"],
    )
    gunw_valid, gunw_water = gunw_mask_flags(gunw_mask)
    water_all = gunw_water if water is None else (water | gunw_water)
    valid = valid_pixels(delta, vegetation, water_all, gunw_valid, layover_shadow)
    z, mu, sigma, n_ref = standardize(delta, valid & non_built)
    dpm = dpm_from_z(z)
    built_valid = built & valid
    stats = unit_stats(z, unit_ids, built_valid)
    all_units = np.unique(unit_ids[unit_ids != 0]).tolist()
    evaluated, excluded = evaluate_units(
        stats, thresholds["min_built_up_pixels_per_unit"], all_units
    )
    med_built = median_of(z, built_valid)
    med_non_built = median_of(z, valid & non_built)
    summary = {
        "label": label,
        "n_px_total": int(delta.size),
        "n_px_valid": int(valid.sum()),
        "n_px_built_up_valid": int(built_valid.sum()),
        "n_px_non_built_valid": int((valid & non_built).sum()),
        "n_px_zero_std": 0 if math.isfinite(sigma) and sigma > 0 else int(valid.sum()),
        "mu": mu,
        "sigma": sigma,
        "n_reference_px": n_ref,
        "baseline_mismatch_disclosed": None,  # filled by the CLI with measured dates
        "median_z_built_up": med_built,
        "median_z_non_built": med_non_built,
        "excess_e": med_built - med_non_built
        if math.isfinite(med_built) and math.isfinite(med_non_built)
        else float("nan"),
        "n_units_total": len(all_units),
        "n_units_evaluated": len(evaluated),
        "n_units_excluded": len(excluded),
        "min_built_up_pixels_per_unit": thresholds["min_built_up_pixels_per_unit"],
        "layover_shadow_mask": "missing" if layover_shadow is None else "applied",
        "thresholds": {
            "built_up_min_footprint_fraction": thresholds["built_up_min_footprint_fraction"],
            "non_built_max_footprint_fraction": thresholds["non_built_max_footprint_fraction"],
        },
    }
    excluded_rows = []
    for uid in excluded:
        excluded_rows.append(
            {
                "unit_id": uid,
                "unit_name": (unit_names or {}).get(uid, str(uid)),
                "n_built_up_valid_px": stats.get(uid, {}).get("n_px", 0),
                "reason": f"n_built_up_valid_px < {thresholds['min_built_up_pixels_per_unit']}",
            }
        )
    return {
        "delta": delta,
        "z": z,
        "dpm": dpm,
        "built_up": built,
        "non_built": non_built,
        "valid": valid,
        "unit_stats": stats,
        "evaluated": evaluated,
        "excluded": excluded,
        "excluded_rows": excluded_rows,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Minimal parquet writer/reader (no pyarrow/fastparquet in the project deps).
# Writes INT64, DOUBLE and UTF8 columns, all REQUIRED, single row group, one
# PLAIN-encoded data page v1 per column, UNCOMPRESSED. Thrift compact-protocol
# footer per parquet.thrift. Verified against pyarrow outside the repo venv
# (see the brief report); read_parquet() is the matching reader used by tests.
# ---------------------------------------------------------------------------

_T_CTYPE = {"i32": 5, "i64": 6, "binary": 8, "list": 9, "struct": 12}
_PARQUET_PHYSTYPE = {"int64": 2, "double": 5, "utf8": 6}


class _CompactWriter:
    """Thrift compact protocol writer. Field ids are ABSOLUTE; deltas are
    computed automatically, with the long-form (zigzag) fallback."""

    def __init__(self) -> None:
        self.buf = bytearray()
        self._last = 0

    def _varint(self, n: int) -> None:
        n &= (1 << 64) - 1
        while True:
            b = n & 0x7F
            n >>= 7
            if n:
                self.buf.append(b | 0x80)
            else:
                self.buf.append(b)
                return

    def _zigzag(self, n: int) -> int:
        return (n << 1) ^ (n >> 63)

    def _field(self, fid: int, ctype: int) -> None:
        delta = fid - self._last
        if 0 < delta <= 15:
            self.buf.append((delta << 4) | ctype)
        else:
            self.buf.append(ctype)
            self._varint(self._zigzag(fid))
        self._last = fid

    def i32(self, fid: int, value: int) -> None:
        self._field(fid, _T_CTYPE["i32"])
        self._varint(self._zigzag(value))

    def i64(self, fid: int, value: int) -> None:
        self._field(fid, _T_CTYPE["i64"])
        self._varint(self._zigzag(value))

    def binary_(self, fid: int, value: bytes) -> None:
        self._field(fid, _T_CTYPE["binary"])
        self._varint(len(value))
        self.buf += value

    def struct_(self, fid: int) -> None:
        self._field(fid, _T_CTYPE["struct"])

    def list_(self, fid: int, size: int, elem_type: str) -> None:
        self._field(fid, _T_CTYPE["list"])
        et = _T_CTYPE[elem_type]
        if size < 15:
            self.buf.append((size << 4) | et)
        else:
            self.buf.append(0xF0 | et)
            self._varint(size)

    def binary_item(self, value: bytes) -> None:
        self._varint(len(value))
        self.buf += value

    def i32_item(self, value: int) -> None:
        self._varint(self._zigzag(value))

    def stop(self) -> None:
        self.buf.append(0)

    def bytes(self) -> bytes:
        return bytes(self.buf)


def _plain_bytes(kind: str, values: list) -> bytes:
    if kind == "int64":
        return np.asarray(values, dtype="<i8").tobytes()
    if kind == "double":
        return np.asarray(values, dtype="<f8").tobytes()
    out = bytearray()
    for v in values:
        b = str(v).encode("utf-8")
        out += struct.pack("<I", len(b)) + b
    return bytes(out)


def write_parquet(path: Path, columns: dict[str, tuple[str, list]]) -> None:
    """Minimal parquet writer: one row group, all REQUIRED columns, PLAIN
    data page v1, uncompressed, no levels (max def/rep level = 0). Field ids
    follow parquet.thrift (SchemaElement.name=4, ColumnMetaData.
    data_page_offset=9, ...)."""
    cols = list(columns.items())
    n_rows = len(cols[0][1][1])
    for name, (kind, values) in cols:
        if len(values) != n_rows:
            raise ValueError(f"column {name} has {len(values)} rows, expected {n_rows}")
        if kind not in _PARQUET_PHYSTYPE:
            raise ValueError(f"unsupported parquet kind {kind}")
    body = bytearray(b"PAR1")
    chunks = []
    for name, (kind, values) in cols:
        data = _plain_bytes(kind, values)
        ph = _CompactWriter()
        ph.i32(1, 0)  # PageType.DATA_PAGE
        ph.i32(2, len(data))  # uncompressed_page_size
        ph.i32(3, len(data))  # compressed_page_size
        ph.struct_(5)  # data_page_header
        dph = _CompactWriter()
        dph.i32(1, n_rows)  # num_values
        dph.i32(2, 0)  # Encoding.PLAIN
        dph.i32(3, 3)  # Encoding.RLE (definition levels; max level 0 -> none)
        dph.i32(4, 3)  # Encoding.RLE (repetition levels; max level 0 -> none)
        dph.stop()
        ph.buf += dph.buf
        ph.stop()
        page = ph.bytes() + data
        offset = len(body)
        body += page
        chunks.append((name, kind, offset, len(page)))
    footer = _CompactWriter()
    footer.i32(1, 1)  # FileMetaData.version
    footer.list_(2, len(cols) + 1, "struct")  # schema: root + leaves
    root = _CompactWriter()
    root.binary_(4, b"schema")  # name
    root.i32(5, len(cols))  # num_children
    root.stop()
    footer.buf += root.buf
    for name, (kind, _values) in cols:
        se = _CompactWriter()
        se.i32(1, _PARQUET_PHYSTYPE[kind])  # Type
        se.i32(3, 0)  # repetition REQUIRED
        se.binary_(4, name.encode("utf-8"))
        if kind == "utf8":
            se.i32(6, 0)  # ConvertedType.UTF8
        se.stop()
        footer.buf += se.buf
    footer.i64(3, n_rows)  # num_rows
    footer.list_(4, 1, "struct")  # row_groups
    rg = _CompactWriter()
    rg.list_(1, len(cols), "struct")  # columns
    total_size = 0
    for name, kind, offset, size in chunks:
        total_size += size
        cc = _CompactWriter()
        cc.i64(2, offset)  # file_offset
        cc.struct_(3)  # meta_data
        cm = _CompactWriter()
        cm.i32(1, _PARQUET_PHYSTYPE[kind])  # type
        cm.list_(2, 2, "i32")  # encodings: PLAIN, RLE
        cm.i32_item(0)
        cm.i32_item(3)
        cm.list_(3, 1, "binary")  # path_in_schema
        cm.binary_item(name.encode("utf-8"))
        cm.i32(4, 0)  # codec UNCOMPRESSED
        cm.i64(5, n_rows)  # num_values
        cm.i64(6, size)  # total_compressed_size
        cm.i64(7, size)  # total_uncompressed_size
        cm.i64(9, offset)  # data_page_offset
        cm.stop()
        cc.buf += cm.buf
        cc.stop()
        rg.buf += cc.buf
    rg.i64(2, total_size)  # total_byte_size
    rg.i64(3, n_rows)  # num_rows
    rg.stop()
    footer.buf += rg.buf
    footer.stop()
    fm = footer.bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(body) + fm + struct.pack("<I", len(fm)) + b"PAR1")


class _CompactReader:
    def __init__(self, blob: bytes) -> None:
        self.blob = blob
        self.pos = 0

    def _byte(self) -> int:
        b = self.blob[self.pos]
        self.pos += 1
        return b

    def varint(self) -> int:
        shift = 0
        out = 0
        while True:
            b = self._byte()
            out |= (b & 0x7F) << shift
            if not (b & 0x80):
                return out
            shift += 7

    def unzigzag(self) -> int:
        v = self.varint()
        return (v >> 1) ^ -(v & 1)

    def binary_r(self) -> bytes:
        n = self.varint()
        out = self.blob[self.pos : self.pos + n]
        self.pos += n
        return out

    def list_size(self, elem_type: int) -> int:
        h = self._byte()
        size = (h & 0xF0) >> 4
        if (h & 0x0F) != elem_type:
            raise ValueError(f"unexpected list element type {h & 0x0F}")
        return self.varint() if size == 15 else size

    def read_struct(self, spec: dict, out: dict) -> dict:
        """spec: field_id -> callable(out) consuming the field payload."""
        last = 0
        while True:
            h = self._byte()
            if h == 0:
                return out
            nibble = (h & 0xF0) >> 4
            if nibble == 0:
                fid = self.unzigzag()
            else:
                fid = last + nibble
            last = fid
            if fid not in spec:
                raise ValueError(f"unexpected parquet metadata field id {fid}")
            spec[fid](out)


def read_parquet(path: Path) -> dict[str, list]:
    """Reader matching write_parquet exactly (test round-trip; not a general
    parquet reader). Field ids per parquet.thrift."""
    blob = Path(path).read_bytes()
    if blob[:4] != b"PAR1" or blob[-4:] != b"PAR1":
        raise ValueError("not a parquet file")
    fm_len = struct.unpack("<I", blob[-8:-4])[0]
    rd = _CompactReader(blob[-8 - fm_len : -8])
    meta: dict = {"schema": [], "row_groups": []}

    def read_schema(_o):
        for _ in range(rd.list_size(_T_CTYPE["struct"])):
            se: dict = {}
            rd.read_struct(
                {
                    1: lambda o: o.__setitem__("type", rd.unzigzag()),
                    3: lambda o: o.__setitem__("repetition", rd.unzigzag()),
                    4: lambda o: o.__setitem__("name", rd.binary_r().decode("utf-8")),
                    5: lambda o: o.__setitem__("num_children", rd.unzigzag()),
                    6: lambda o: o.__setitem__("converted", rd.unzigzag()),
                },
                se,
            )
            meta["schema"].append(se)

    def read_row_groups(_o):
        for _ in range(rd.list_size(_T_CTYPE["struct"])):
            rg: dict = {"columns": []}

            def read_columns(_o2, rg=rg):
                for _k in range(rd.list_size(_T_CTYPE["struct"])):
                    cc: dict = {}

                    def read_cm(_o3, cc=cc):
                        cm: dict = {}

                        def read_enc(_o4, cm=cm):
                            n = rd.list_size(_T_CTYPE["i32"])
                            cm["encodings"] = [rd.unzigzag() for _ in range(n)]

                        def read_path(_o4, cm=cm):
                            n = rd.list_size(_T_CTYPE["binary"])
                            cm["path"] = [rd.binary_r().decode("utf-8") for _ in range(n)]

                        rd.read_struct(
                            {
                                1: lambda o: o.__setitem__("type", rd.unzigzag()),
                                2: read_enc,
                                3: read_path,
                                4: lambda o: o.__setitem__("codec", rd.unzigzag()),
                                5: lambda o: o.__setitem__("num_values", rd.unzigzag()),
                                6: lambda o: o.__setitem__("total_compressed_size", rd.unzigzag()),
                                7: lambda o: o.__setitem__(
                                    "total_uncompressed_size", rd.unzigzag()
                                ),
                                9: lambda o: o.__setitem__("data_page_offset", rd.unzigzag()),
                            },
                            cm,
                        )
                        cc["meta"] = cm

                    rd.read_struct(
                        {
                            2: lambda o: o.__setitem__("file_offset", rd.unzigzag()),
                            3: read_cm,
                        },
                        cc,
                    )
                    rg["columns"].append(cc["meta"])

            rd.read_struct(
                {
                    1: read_columns,
                    2: lambda o: o.__setitem__("total_byte_size", rd.unzigzag()),
                    3: lambda o: o.__setitem__("num_rows", rd.unzigzag()),
                },
                rg,
            )
            meta["row_groups"].append(rg)

    rd.read_struct(
        {
            1: lambda o: o.__setitem__("version", rd.unzigzag()),
            2: read_schema,
            3: lambda o: o.__setitem__("num_rows", rd.unzigzag()),
            4: read_row_groups,
        },
        meta,
    )
    out: dict[str, list] = {}
    for cm in meta["row_groups"][0]["columns"]:
        name = cm["path"][0]
        phys = cm["type"]
        page = blob[cm["data_page_offset"] : cm["data_page_offset"] + cm["total_compressed_size"]]
        pr = _CompactReader(page)
        state: dict = {}

        def read_dph(o, pr=pr, state=state):
            def n_vals(o2, pr=pr):
                o2.__setitem__("n_values", pr.unzigzag())

            def skip_enum(o2, pr=pr):
                pr.unzigzag()

            pr.read_struct(
                {1: n_vals, 2: skip_enum, 3: skip_enum, 4: skip_enum},
                state.setdefault("data_page_header", {}),
            )

        pr.read_struct(
            {
                1: lambda o, pr=pr: o.__setitem__("page_type", pr.unzigzag()),
                2: lambda o, pr=pr: o.__setitem__("uncompressed_page_size", pr.unzigzag()),
                3: lambda o, pr=pr: o.__setitem__("compressed_page_size", pr.unzigzag()),
                5: read_dph,
            },
            state,
        )
        if state.get("page_type") != 0:
            raise ValueError(f"expected DATA_PAGE v1 for column {name}")
        n_values = state.get("data_page_header", {}).get("n_values", cm["num_values"])
        data = page[pr.pos :]
        if phys == 2:  # INT64
            out[name] = np.frombuffer(data[: n_values * 8], dtype="<i8").tolist()
        elif phys == 5:  # DOUBLE
            out[name] = np.frombuffer(data[: n_values * 8], dtype="<f8").tolist()
        elif phys == 6:  # BYTE_ARRAY / utf8
            vals = []
            pos = 0
            for _ in range(n_values):
                ln = struct.unpack("<I", data[pos : pos + 4])[0]
                pos += 4
                vals.append(data[pos : pos + ln].decode("utf-8"))
                pos += ln
            out[name] = vals
        else:
            raise ValueError(f"unsupported physical type {phys} for column {name}")
    return out


def parquet_columns_from_rows(rows: list[dict]) -> dict[str, tuple[str, list]]:
    """Flatten unit rows into the parquet schema. NaN medians stay NaN."""
    names = [
        ("unit_id", "int64"),
        ("unit_name", "utf8"),
        ("unit_type", "utf8"),
        ("unit_source", "utf8"),
        ("evaluated", "int64"),
        ("n_built_up_valid_px", "int64"),
        ("n_non_built_valid_px", "int64"),
        ("median_z_built", "double"),
        ("median_z_built_control", "double"),
    ]
    out: dict[str, tuple[str, list]] = {}
    for key, kind in names:
        out[key] = (kind, [r.get(key, np.nan if kind == "double" else 0) for r in rows])
    return out


# ---------------------------------------------------------------------------
# CLI: discovery + streaming + Earth Engine layers + outputs. Network only.
# ---------------------------------------------------------------------------


def _load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def resolve_aoi(override: list[float] | None) -> tuple[list[float], str]:
    """AOI precedence: CLI > config/bailasar.yaml (AOIs are operational) > the
    hour-2 gate estimate recorded in the brief (labelled estimate)."""
    if override:
        return override, "CLI --aoi argument"
    try:
        ops = yaml.safe_load(OPS_PATH.read_text(encoding="utf-8"))
        aoi = ops.get("aois", {}).get("2_eje_cafetero_quake")
    except FileNotFoundError:
        aoi = None
    if aoi:
        return [float(v) for v in aoi], "config/bailasar.yaml aois.2_eje_cafetero_quake"
    return list(EJE_CAFETERO_AOI_ESTIMATE), (
        "hour-2 gate estimate from briefs/feat/data-quake-dpm.md (config value null)"
    )


def _bbox_wkt(aoi: list[float]) -> str:
    w, s, e, n = aoi
    return f"POLYGON(({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))"


def discover_pairs(track: int, aoi: list[float]) -> dict[str, dict]:
    """Select the R/C/K GUNW triplet for a track from a read-only ASF search
    (hour-2 gate): C spans the event; R is the pre-event pair immediately
    before C; K is the pre-event pair immediately before R (sharing no
    acquisition with C; its secondary may equal R's reference)."""
    import asf_search as asf

    results = asf.geo_search(
        platform=[asf.PLATFORM.NISAR],
        processingLevel=["GUNW"],
        intersectsWith=_bbox_wkt(aoi),
        start="2026-06-01T00:00:00Z",
        end="2026-11-13T23:59:59Z",
        maxResults=300,
    )
    seen: dict[str, dict] = {}
    for r in results:
        p = r.properties
        if p.get("pathNumber") != track:
            continue
        url = p["url"]
        entry = {
            "granule_id": p["sceneName"],
            "url": url,
            "start_time": p["startTime"],
        }
        seen[p["sceneName"]] = entry
    granules = sorted(seen.values(), key=lambda g: g["start_time"], reverse=True)
    if not granules:
        raise RuntimeError(f"no GUNW granules found over the AOI for track {track}")

    import re

    def dates_of(g):
        stamps = re.findall(r"(\d{8}T\d{6})", g["granule_id"])
        if len(stamps) < 4:
            raise RuntimeError(f"cannot parse dates from {g['granule_id']}")
        return stamps[0][:8], stamps[2][:8]  # ref start, secondary start

    for g in granules:
        g["ref_date"], g["sec_date"] = dates_of(g)
        g["ref"] = datetime.strptime(g["ref_date"], "%Y%m%d").date()
        g["sec"] = datetime.strptime(g["sec_date"], "%Y%m%d").date()
        g["baseline_days"] = (g["sec"] - g["ref"]).days
    event = datetime.strptime(EVENT_DATE, "%Y-%m-%d").date()
    cands_c = [g for g in granules if g["ref"] <= event < g["sec"]]
    if not cands_c:
        raise RuntimeError(f"no co-event (C) pair spanning {EVENT_DATE} on track {track}")
    c = cands_c[0]
    pre = [g for g in granules if g["sec"] <= event]
    cands_r = [g for g in pre if g["sec"] <= c["ref"] and g["ref"] < c["ref"]]
    if not cands_r:
        raise RuntimeError(f"no pre-event reference (R) pair before C on track {track}")
    r = max(cands_r, key=lambda g: g["sec"])
    cands_k = [
        g
        for g in pre
        if g is not r and {g["ref"], g["sec"]}.isdisjoint({c["ref"], c["sec"]})  # no C scene
    ]
    # K = the pre-event pair immediately before R (its secondary date may equal
    # R's reference date: K, R, C form the three-scene sequence
    # Jun26/Jul8/Jul20/Aug13 on track 11, per the hour-2 gate).
    k = max(cands_k, key=lambda g: g["sec"]) if cands_k else None
    return {"C": c, "R": r, "K": k, "all": granules}


def load_gunw_window(fs, url: str, aoi: list[float]) -> dict:
    """Stream ONLY the AOI window of the 20 m coherence grid (h5py over fsspec;
    no full download). Returns arrays + grid geometry + product dates."""
    import h5py
    from pyproj import Transformer

    w, s, e, n = aoi
    tr = Transformer.from_crs("EPSG:4326", "EPSG:32618", always_xy=True)
    x0, y0 = tr.transform(w, s)
    x1, y1 = tr.transform(e, n)
    with fs.open(url, "rb") as fobj:
        with h5py.File(fobj, "r") as h5:
            ident = h5["/science/LSAR/identification"]
            ref_t = ident["referenceZeroDopplerStartTime"][()].decode()
            sec_t = ident["secondaryZeroDopplerStartTime"][()].decode()
            grp = h5[f"{GUNW_GRIDS}/{GUNW_COH_20M_GROUP}"]
            xs = grp["xCoordinates"][:]
            ys = grp["yCoordinates"][:]
            dx = float(grp["xCoordinateSpacing"][()])
            dy = float(grp["yCoordinateSpacing"][()])
            epsg = int(grp["projection"][()])
            if abs(abs(dx) - 20.0) > 1e-6 or abs(abs(dy) - 20.0) > 1e-6:
                raise RuntimeError(f"expected 20 m posting, got x spacing {dx}, y {dy} for {url}")
            col_flip = xs[1] < xs[0]
            if col_flip:
                xs = xs[::-1]  # index space: ascending x
            if ys[1] > ys[0]:
                raise RuntimeError("expected descending y coordinates in the GUNW grid")
            xs0, ys0 = float(xs[0]), float(ys[0])
            px = abs(dx)
            c0 = max(math.ceil((x0 - xs0) / px), 0)
            c1 = min(math.ceil((x1 - xs0) / px), len(xs))
            r0 = max(math.ceil((ys0 - y1) / px), 0)
            r1 = min(math.ceil((ys0 - y0) / px), len(ys))
            if c1 - c0 <= 1 or r1 - r0 <= 1:
                raise RuntimeError(f"AOI window outside the GUNW frame for {url}")
            c0o, c1o = (len(xs) - c1, len(xs) - c0) if col_flip else (c0, c1)
            coh_ds = grp[f"{GUNW_POL}/coherenceMagnitude"]
            mask_ds = grp["mask"]
            coh = np.asarray(coh_ds[r0:r1, c0o:c1o], dtype=np.float32)
            mask = np.asarray(mask_ds[r0:r1, c0o:c1o])
            out_of_range = ~np.isfinite(coh) | (coh < -0.001) | (coh > 1.001)
            n_out = int(out_of_range.sum())
            coh[out_of_range] = np.nan
            return {
                "coh": coh,
                "mask": mask,
                "x0": float(xs[c0]),
                "y0": float(ys[r0]),
                "rows": int(r1 - r0),
                "cols": int(c1 - c0),
                "epsg": epsg,
                "spacing": 20.0,
                "ref_time": ref_t,
                "sec_time": sec_t,
                "n_coh_outside_0_1": n_out,
            }


def _translate_probe_ee() -> str:
    """Decide whether computePixels translate is pixel-CENTER or pixel-EDGE by
    asking GEE for a 1x1 pixelLonLat tile. Returns 'center' or 'edge'."""
    import ee

    img = ee.Image.pixelLonLat()
    params = {
        "expression": img,
        "fileFormat": "NPY",
        "grid": {
            "dimensions": {"width": 1, "height": 1},
            "affineTransform": {
                "scaleX": 20.0,
                "shearX": 0,
                "translateX": 400000.0,
                "shearY": 0,
                "scaleY": -20.0,
                "translateY": 500000.0,
            },
            "crsCode": "EPSG:32618",
        },
    }
    arr = np.load(io.BytesIO(ee.data.computePixels(params)))
    lon, lat = float(arr["longitude"][0, 0]), float(arr["latitude"][0, 0])
    from pyproj import Transformer

    back = Transformer.from_crs("EPSG:4326", "EPSG:32618", always_xy=True)
    x, y = back.transform(lon, lat)
    if abs(x - 400000.0) < 0.01 and abs(y - 500000.0) < 0.01:
        return "center"
    if abs(x - 400010.0) < 0.01 and abs(y - 499990.0) < 0.01:
        return "edge"
    raise RuntimeError(f"cannot classify GEE computePixels translate convention at {x},{y}")


def fetch_gee_layers(window: dict, tile: int = 512) -> tuple[np.ndarray, np.ndarray, dict]:
    """Footprint coverage fraction (VIDA footprints rasterized at
    FOOTPRINT_FINE_SCALE_M then reduced to the 20 m DPM grid) and ESA WorldCover
    class, tiled to keep each computePixels call small. Failed tiles stay NaN
    (missing) and are counted, never filled."""
    import ee

    from gee_math.ee_session import init_ee

    project = init_ee()
    convention = _translate_probe_ee()
    rows, cols = window["rows"], window["cols"]
    x0c, y0c = window["x0"], window["y0"]  # centers of the first (top-left) pixel
    coverage = np.full((rows, cols), np.nan, dtype=np.float32)
    landcover = np.zeros((rows, cols), dtype=np.uint8)
    missing_tiles = []
    vida = ee.FeatureCollection(VIDA_ASSET)
    wc = ee.ImageCollection(WORLDCOVER_ASSET).first().select("Map").rename("lc")

    def tile_region(r0, c0, h, wpx):
        # Grid y descends: row r center = y0c - 20*r. The tile region covers
        # the full pixel footprint (outer edges), used ONLY to pre-filter the
        # footprint FeatureCollection for the tile; computePixels samples by
        # the affineTransform, independently of this rectangle.
        west = x0c - 10.0 + 20.0 * c0
        east = x0c + 10.0 + 20.0 * (c0 + wpx - 1)
        north = y0c + 10.0 - 20.0 * r0
        south = y0c - 10.0 - 20.0 * (r0 + h - 1)
        return ee.Geometry.Rectangle([west, south, east, north], proj="EPSG:32618", geodesic=False)

    total_tiles = math.ceil(rows / tile) * math.ceil(cols / tile)
    done = 0
    for r0 in range(0, rows, tile):
        h = min(tile, rows - r0)
        for c0 in range(0, cols, tile):
            wpx = min(tile, cols - c0)
            region = tile_region(r0, c0, h, wpx)
            fine = (
                ee.Image()
                .paint(vida.filterBounds(region), 1)
                .gt(0)
                .reproject(crs="EPSG:32618", scale=FOOTPRINT_FINE_SCALE_M)
            )
            frac = fine.reduceResolution(ee.Reducer.mean(), maxPixels=1024).rename("fp")
            stack = ee.Image.cat([frac, wc])
            trans_x = x0c + 20.0 * c0 - (10.0 if convention == "edge" else 0.0)
            trans_y = y0c - 20.0 * r0 + (10.0 if convention == "edge" else 0.0)
            params = {
                "expression": stack,
                "fileFormat": "NPY",
                "grid": {
                    "dimensions": {"width": wpx, "height": h},
                    "affineTransform": {
                        "scaleX": 20.0,
                        "shearX": 0,
                        "translateX": trans_x,
                        "shearY": 0,
                        "scaleY": -20.0,
                        "translateY": trans_y,
                    },
                    "crsCode": "EPSG:32618",
                },
            }
            ok = False
            for attempt in range(3):
                try:
                    arr = np.load(io.BytesIO(ee.data.computePixels(params)))
                    cov = arr["fp"].astype(np.float32)
                    lc = arr["lc"].astype(np.uint8)
                    coverage[r0 : r0 + h, c0 : c0 + wpx] = cov[:h, :wpx]
                    landcover[r0 : r0 + h, c0 : c0 + wpx] = lc[:h, :wpx]
                    ok = True
                    break
                except Exception as exc:  # noqa: BLE001 - retried, then recorded missing
                    print(f"  [WARN] tile r{r0} c{c0} attempt {attempt + 1} failed: {exc}")
                    time.sleep(2.0 * (attempt + 1))
            if not ok:
                missing_tiles.append({"row": r0, "col": c0})
            done += 1
            print(f"  GEE tiles {done}/{total_tiles}", end="\r")
    print()
    prov = {
        "gee_project": project,
        "vida_asset": VIDA_ASSET,
        "worldcover_asset": WORLDCOVER_ASSET,
        "compute_pixels_translate_convention": convention,
        "n_missing_tiles": len(missing_tiles),
        "missing_tiles": missing_tiles,
        "footprint_fine_scale_m": FOOTPRINT_FINE_SCALE_M,
    }
    return coverage, landcover, prov


def fetch_units(window: dict, aoi: list[float], asset: str | None, name_prop: str | None):
    """Official unit polygons from public GEE assets, rasterized onto the DPM
    grid locally. Barrio polygons are pending (validation/README.md): the
    default is the labeled FAO GAUL ADM2 (municipio) fallback."""
    import ee
    from rasterio.features import rasterize
    from rasterio.transform import Affine
    from rasterio.warp import transform_geom

    from gee_math.ee_session import init_ee

    project = init_ee()
    assets = [asset] if asset else list(UNIT_ASSETS)
    aoi_geom = ee.Geometry.Rectangle(aoi, proj="EPSG:4326", geodesic=False)
    used_asset = None
    info = None
    err = []
    for a in assets:
        try:
            cand = ee.FeatureCollection(a).filterBounds(aoi_geom)
            cand_info = cand.getInfo()  # filtered, not the global table
            if not cand_info.get("features"):
                err.append(f"{a}: 0 features in the AOI")
                continue
            used_asset, info = a, cand_info
            break
        except Exception as exc:  # noqa: BLE001 - fall back to the next asset
            err.append(f"{a}: {exc}")
    if used_asset is None:
        raise RuntimeError(f"no unit asset reachable: {err}")
    features = cast(dict, info)["features"]
    if not features:
        raise RuntimeError(f"no unit polygons in the AOI from {used_asset}")
    props0 = features[0]["properties"]
    candidates = (
        [name_prop]
        if name_prop
        else ["GAUL2_NAME", "ADM2_NAME", "ADM2_EN", "adm2_name", "shapeName"]
    )
    name_key = next((k for k in candidates if k and k in props0), None)
    if not name_key:
        raise RuntimeError(f"no usable name property in {used_asset}: keys={list(props0)[:12]}")
    rows, cols = window["rows"], window["cols"]
    # rasterize pixel centers: (x0c,y0c) is the top-left pixel center
    transform = Affine(20.0, 0.0, window["x0"] - 10.0, 0.0, -20.0, window["y0"] + 10.0)
    shapes = []
    names: dict[int, str] = {}
    for i, f in enumerate(features, start=1):
        geom = f.get("geometry") or {}
        if not geom.get("coordinates"):
            continue
        g = transform_geom("EPSG:4326", "EPSG:32618", geom)
        shapes.append((g, i))
        names[i] = str(f["properties"].get(name_key, f"unit_{i}"))
    unit_ids = rasterize(shapes, out_shape=(rows, cols), transform=transform, fill=0, dtype="int32")
    prov = {
        "unit_asset": used_asset,
        "unit_name_property": name_key,
        "unit_type": UNIT_FALLBACK_LABEL if "GAUL" in used_asset else used_asset,
        "n_units": len(names),
        "gee_project": project,
    }
    return unit_ids, names, prov


def _print_pairs(pairs: dict) -> None:
    c, r, k = pairs["C"], pairs["R"], pairs["K"]

    def fmt(p):
        return f"{p['granule_id']} ({p['ref_date']}->{p['sec_date']}, {p['baseline_days']}d)"

    print(f"  R (pre-event reference): {fmt(r)}")
    print(f"  C (co-event):            {fmt(c)}")
    if k:
        print(f"  K (control pre-event):  {fmt(k)}")
    else:
        print("  K (control pre-event):  none found")
    if c["baseline_days"] != r["baseline_days"] or (k and k["baseline_days"] != r["baseline_days"]):
        print(
            "  BASELINE MISMATCH (disclosed next to every number): C spans "
            f"{c['baseline_days']} d while R and K span {r['baseline_days']}"
            f"/{k['baseline_days'] if k else '-'} d"
        )


def _summary_line(summary: dict, pairs: dict) -> None:
    _print_pairs(pairs)
    for key in (
        "n_px_total",
        "n_px_valid",
        "n_px_built_up_valid",
        "n_px_non_built_valid",
        "n_reference_px",
        "mu",
        "sigma",
        "median_z_built_up",
        "median_z_non_built",
        "excess_e",
        "n_units_total",
        "n_units_evaluated",
        "n_units_excluded",
        "layover_shadow_mask",
    ):
        print(f"  {summary['label']}_pass.{key} = {summary[key]}")
    for row in summary.get("excluded_rows_public", []):
        print(
            f"    excluded unit {row['unit_name']}: {row['n_built_up_valid_px']} px "
            f"({row['reason']})"
        )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Aug 10 2026 quake DPM (Hazard 2)")
    parser.add_argument("--track", type=int, default=11)
    parser.add_argument(
        "--aoi",
        type=float,
        nargs=4,
        metavar=("W", "S", "E", "N"),
        default=None,
        help="AOI bbox override (EPSG:4326)",
    )
    parser.add_argument("--out-dir", type=Path, default=CACHE_DIR)
    parser.add_argument("--units-asset", default=None, help="GEE unit polygons asset")
    parser.add_argument("--units-name-prop", default=None)
    parser.add_argument("--no-control", action="store_true")
    parser.add_argument("--tile", type=int, default=512)
    args = parser.parse_args(argv)

    _load_env()
    thresholds = load_quake_prereg()
    aoi, aoi_source = resolve_aoi(args.aoi)
    print(f"AOI [W,S,E,N] = {aoi} (source: {aoi_source})")
    print(
        "thresholds from config/preregistered.yaml "
        f"(sha1 {git_blob_sha1(PREREG_PATH)}, status={thresholds['status']}): "
        f"built_up>={thresholds['built_up_min_footprint_fraction']}, "
        f"non_built<={thresholds['non_built_max_footprint_fraction']}, "
        f"min_built_up_px={thresholds['min_built_up_pixels_per_unit']}"
    )

    pairs = discover_pairs(args.track, aoi)
    print(f"discovered C/R/K on track {args.track} (ASF read-only search):")
    _print_pairs(pairs)

    import earthaccess

    earthaccess.login(strategy="environment")
    fs = earthaccess.get_fsspec_https_session()
    windows: dict[str, dict] = {}
    for role in ("C", "R", "K"):
        if role == "K" and (not pairs["K"] or args.no_control):
            print("control pass: SKIPPED (no K pair or --no-control)")
            continue
        g = pairs[role]
        print(f"streaming {role} = {g['granule_id']} (AOI window only, 20 m)...")
        windows[role] = load_gunw_window(fs, g["url"], aoi)
        wdw = windows[role]
        print(
            f"  window {wdw['rows']}x{wdw['cols']} px, EPSG:{wdw['epsg']}, "
            f"ref={wdw['ref_time'][:10]} sec={wdw['sec_time'][:10]}, "
            f"coh outside [0,1]: {wdw['n_coh_outside_0_1']} px -> NaN"
        )
    if "C" not in windows or "R" not in windows:
        raise RuntimeError("both C and R windows are required")
    ref_window = windows["R"]
    for role, wdw in windows.items():
        if role == "R":
            continue
        if wdw["rows"] != ref_window["rows"] or wdw["cols"] != ref_window["cols"]:
            raise RuntimeError(
                f"grid mismatch between R and {role}: "
                f"{wdw['rows']}x{wdw['cols']} vs {ref_window['rows']}x{ref_window['cols']}"
            )
        if abs(wdw["x0"] - ref_window["x0"]) > 1e-6 or abs(wdw["y0"] - ref_window["y0"]) > 1e-6:
            raise RuntimeError(
                f"grid origin mismatch between R and {role}: "
                f"({wdw['x0']},{wdw['y0']}) vs ({ref_window['x0']},{ref_window['y0']})"
            )

    print("Earth Engine layers (footprint coverage + WorldCover)...")
    coverage, landcover, gee_prov = fetch_gee_layers(ref_window, tile=args.tile)
    n_cov_missing = int((~np.isfinite(coverage)).sum())
    cov_max = f"{np.nanmax(coverage):.3f}" if n_cov_missing < coverage.size else "n/a (all missing)"
    print(
        f"  coverage: {int(np.isfinite(coverage).sum())} px measured, "
        f"{n_cov_missing} px missing (NaN), max {cov_max}; "
        f"missing tiles: {gee_prov['n_missing_tiles']}"
    )
    lc_vals, lc_counts = np.unique(landcover, return_counts=True)
    print(
        "  WorldCover classes in window (class: px):",
        {int(v): int(c) for v, c in zip(lc_vals, lc_counts, strict=True)},
    )

    print("unit polygons (rasterized to the 20 m grid)...")
    unit_ids, unit_names, unit_prov = fetch_units(
        ref_window, aoi, args.units_asset, args.units_name_prop
    )
    print(
        f"  {unit_prov['n_units']} units from {unit_prov['unit_asset']} "
        f"(name property {unit_prov['unit_name_property']})"
    )

    vegetation = np.isin(landcover, WORLDCOVER_VEGETATION_CLASSES)
    water = landcover == WORLDCOVER_WATER_CLASS

    run_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    passes: dict[str, dict] = {}
    passes["C"] = run_dpm_pass(
        windows["R"]["coh"],
        windows["C"]["coh"],
        coverage,
        vegetation,
        water,
        windows["C"]["mask"],
        unit_ids,
        thresholds,
        None,
        unit_names,
        "C",
    )
    passes["C"]["summary"]["excluded_rows_public"] = passes["C"]["excluded_rows"]
    passes["C"]["summary"]["baseline_mismatch_disclosed"] = (
        f"C {pairs['C']['baseline_days']}d vs R {pairs['R']['baseline_days']}d"
    )
    if "K" in windows:
        passes["K"] = run_dpm_pass(
            windows["K"]["coh"],
            windows["R"]["coh"],
            coverage,
            vegetation,
            water,
            windows["K"]["mask"],
            unit_ids,
            thresholds,
            None,
            unit_names,
            "K(control)",
        )
        passes["K"]["summary"]["excluded_rows_public"] = passes["K"]["excluded_rows"]
        passes["K"]["summary"]["baseline_mismatch_disclosed"] = (
            f"control: K {pairs['K']['baseline_days']}d, R {pairs['R']['baseline_days']}d "
            "(both pre-event, mismatch recorded)"
        )

    print("\nDPM results (COMPUTED AND STORED; pre-registration pending, not interpreted):")
    for p in passes.values():
        _summary_line(p["summary"], pairs)

    c_pass = passes["C"]
    rows = []
    stats_c = c_pass["unit_stats"]
    stats_k = passes["K"]["unit_stats"] if "K" in passes else {}
    for uid, name in sorted(unit_names.items()):
        s_c = stats_c.get(uid, {"median_z": float("nan"), "n_px": 0})
        s_k = stats_k.get(uid, {"median_z": float("nan")})
        evaluated = uid in c_pass["evaluated"]
        n_non_built = int((c_pass["valid"] & c_pass["non_built"] & (unit_ids == uid)).sum())
        rows.append(
            {
                "unit_id": uid,
                "unit_name": name,
                "unit_type": unit_prov["unit_type"],
                "unit_source": unit_prov["unit_asset"],
                "evaluated": 1 if evaluated else 0,
                "n_built_up_valid_px": s_c["n_px"],
                "n_non_built_valid_px": n_non_built,
                "median_z_built": s_c["median_z"] if evaluated else float("nan"),
                "median_z_built_control": s_k.get("median_z", float("nan")),
            }
        )
    out_dir = args.out_dir
    zarr_path = out_dir / f"dpm_track{args.track}.zarr"
    parquet_path = out_dir / "barrio_dpm.parquet"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_parquet(parquet_path, parquet_columns_from_rows(rows))
    print(
        f"\nwrote {parquet_path} ({len(rows)} unit rows, "
        f"{c_pass['summary']['n_units_excluded']} excluded, counted above)"
    )

    import xarray as xr

    data_vars = {
        "coh_R": (("y", "x"), windows["R"]["coh"]),
        "coh_C": (("y", "x"), windows["C"]["coh"]),
        "delta_C": (("y", "x"), c_pass["delta"].astype(np.float32)),
        "z_C": (("y", "x"), c_pass["z"].astype(np.float32)),
        "dpm_C": (("y", "x"), c_pass["dpm"].astype(np.float32)),
        "footprint_coverage": (("y", "x"), coverage),
        "landcover": (("y", "x"), landcover),
        "gunw_mask": (("y", "x"), windows["C"]["mask"].astype(np.uint8)),
        "built_up": (("y", "x"), c_pass["built_up"].astype(np.uint8)),
        "non_built": (("y", "x"), c_pass["non_built"].astype(np.uint8)),
        "valid_px": (("y", "x"), c_pass["valid"].astype(np.uint8)),
        "unit_id": (("y", "x"), unit_ids.astype(np.int32)),
    }
    if "K" in windows:
        k_pass = passes["K"]
        data_vars["coh_K"] = (("y", "x"), windows["K"]["coh"])
        data_vars["delta_K"] = (("y", "x"), k_pass["delta"].astype(np.float32))
        data_vars["z_K"] = (("y", "x"), k_pass["z"].astype(np.float32))
        data_vars["dpm_K"] = (("y", "x"), k_pass["dpm"].astype(np.float32))
    xs = ref_window["x0"] + 20.0 * np.arange(ref_window["cols"], dtype=np.float64)
    ys = ref_window["y0"] - 20.0 * np.arange(ref_window["rows"], dtype=np.float64)
    prov = {
        "run_utc": run_utc,
        "track": args.track,
        "aoi": aoi,
        "aoi_source": aoi_source,
        "event_date": EVENT_DATE,
        "prereg_sha1": git_blob_sha1(PREREG_PATH),
        "prereg_status": thresholds["status"],
        "pairs": {
            role: {
                "granule_id": pairs[role]["granule_id"],
                "ref_date": pairs[role]["ref_date"],
                "sec_date": pairs[role]["sec_date"],
                "baseline_days": pairs[role]["baseline_days"],
                "provisional": True,
            }
            for role in ("C", "R", "K")
            if pairs[role]
        },
        "baseline_mismatch": (
            f"C spans {pairs['C']['baseline_days']} d; R and K span "
            f"{pairs['R']['baseline_days']} d and "
            f"{(pairs['K'] or {}).get('baseline_days', '-')} d (Aug 1 / Aug 4 missing)"
        ),
        "grid": {
            "epsg": ref_window["epsg"],
            "posting_m": 20.0,
            "rows": ref_window["rows"],
            "cols": ref_window["cols"],
        },
        "gee": gee_prov,
        "units": unit_prov,
        "layover_shadow_mask": "missing: NISAR GUNW has no layover/shadow layer "
        "(JPL D-102272 Rev E p.44: grid mask = water + subswath validity)",
        "summary_C": c_pass["summary"],
        "summary_K_control": passes["K"]["summary"] if "K" in passes else "skipped",
        "thresholds": {
            k: thresholds[k]
            for k in (
                "built_up_min_footprint_fraction",
                "non_built_max_footprint_fraction",
                "min_built_up_pixels_per_unit",
            )
        },
        "worldcover_classes": {
            "vegetation": list(WORLDCOVER_VEGETATION_CLASSES),
            "water": WORLDCOVER_WATER_CLASS,
        },
    }
    ds = xr.Dataset(
        data_vars,
        coords={"y": ys, "x": xs},
        attrs={"provenance": json.dumps(prov, default=str, allow_nan=True)},
    )
    try:
        ds.to_zarr(zarr_path, mode="w", zarr_format=3)
    except TypeError:  # older xarray without zarr_format kwarg
        ds.to_zarr(zarr_path, mode="w")
    print(f"wrote {zarr_path} ({ref_window['rows']}x{ref_window['cols']}, zarr v3)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
