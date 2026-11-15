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
    unit_stats / evaluate_units  unit DPM_u = median Z of built-up pixels,
                       units with < min_built_up_pixels_per_unit excluded+counted
    run_dpm_pass       one DPM pass; the identical code path runs the co-event
                       pass (ref=R, cmp=C) and the control pass (ref=K, cmp=R)
    adjusted_excess    E_C − E_K from two pass excesses; NaN stays NaN

The layover/shadow mask required by the design does not exist in the NISAR GUNW
product (verified against JPL D-102272 Rev E p.44 and the real granules: the GUNW
`mask` is water + subswath validity, not layover/shadow). It is recorded as
`missing` in provenance and never replaced with invented values.

CLI (network + GEE): python -m gee_math.earthquake_dpm_math --track 47
    reads the R/C/K triplet from the hour-2 gate catalog
    (nisar_colombia_granules_2026.json → quake_triplets; ASF discovery is only
    a fallback and a cross-check), streams only the AOI window of
    coherenceMagnitude at 20 m posting from the GUNW HDF5 files via h5py +
    fsspec (one bounded Earthdata session per granule: fresh client, socket
    timeouts, retries; docs/kb/nisar-gcov-read-timeouts.md), computes R, C, K on
    one grid, and writes local_cache/quake/dpm_track<N>.zarr plus
    local_cache/quake/dpm_units_track<N>.parquet (pyarrow). Unit polygons come
    from a GEE asset or a local GeoJSON/GeoPackage file. Until the
    pre-registration is frozen, C/K-pass statistics (μ, σ, medians, excess,
    per-unit DPM) are computed and stored ONLY inside those git-ignored
    outputs; every printed line is counts (validation/README.md deviation 1
    must not recur).
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
# src/ is not an installed package; tests/test_config.py uses the same insert.
sys.path.insert(0, str(ROOT / "src"))

from bailasar.config import load_config  # noqa: E402

PREREG_PATH = ROOT / "config" / "preregistered.yaml"
ENV_PATH = ROOT / ".env"
CACHE_DIR = ROOT / "local_cache" / "quake"
GATE_CATALOG_PATH = ROOT / "nisar_colombia_granules_2026.json"
QUAKE_AOI_NAME = "2_eje_cafetero_quake"
# Earthdata reader limits (docs/kb/nisar-gcov-read-timeouts.md pattern, as in
# gee_math/flood_polarimetric_math.py). Reader limits, not science thresholds.
GRANULE_ATTEMPTS = 3
GRANULE_BACKOFF_S = (2.0, 4.0)
SOCK_CONNECT_S = 30
SOCK_READ_S = 120
FSSPEC_BLOCK_SIZE = 32 * 1024 * 1024

EVENT_DATE = "2026-08-10"

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


def load_quake_prereg() -> dict:
    """The quake thresholds through the one shared loader
    (src/bailasar/config.py #load_config), never a second YAML reader and never
    a default: a missing or null key raises ConfigError instead of inventing a
    value. The preregistered hash is the loader's git-blob hash."""
    cfg = load_config()
    return {
        "built_up_min_footprint_fraction": float(
            cfg.prereg("quake.built_up_min_footprint_fraction")
        ),
        "non_built_max_footprint_fraction": float(
            cfg.prereg("quake.non_built_max_footprint_fraction")
        ),
        "min_built_up_pixels_per_unit": int(cfg.prereg("quake.min_built_up_pixels_per_unit")),
        "status": cfg.status,
        "is_frozen": cfg.is_frozen,
        "prereg_sha1": cfg.preregistered_hash,
    }


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
        "prereg_status": str(thresholds.get("status", "?")),
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


def adjusted_excess(excess_c: float, excess_k: float) -> float:
    """Control-adjusted built-up excess, E_C − E_K.

    Each input is one pass excess from run_dpm_pass: median Z over valid
    built-up pixels minus median Z over valid non-built pixels. A non-finite
    input stays NaN. This never imputes a zero and it does not decide whether
    a contrast is damage.
    """
    if not math.isfinite(excess_c) or not math.isfinite(excess_k):
        return float("nan")
    return float(excess_c) - float(excess_k)


# ---------------------------------------------------------------------------
# Parquet via pyarrow (real engine since #31; the hand-written footer-packing
# writer from the hour-2 gate is gone). Column names, kinds (int64/double/utf8)
# and NaN semantics are unchanged; NaN medians round-trip as NaN, not null.
# ---------------------------------------------------------------------------


def write_parquet(path: Path, columns: dict[str, tuple[str, list]]) -> None:
    """Write one row group, all columns REQUIRED (nullable=False), through
    pyarrow.parquet. Kind names ("int64", "double", "utf8") match the previous
    hand-written schema so callers and #32 (scoring) see identical columns."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    kinds = {"int64": pa.int64(), "double": pa.float64(), "utf8": pa.string()}
    cols = list(columns.items())
    n_rows = len(cols[0][1][1])
    for name, (_kind, values) in cols:
        if len(values) != n_rows:
            raise ValueError(f"column {name} has {len(values)} rows, expected {n_rows}")
    fields = [pa.field(name, kinds[kind], nullable=False) for name, (kind, _) in cols]
    arrays = [pa.array(values, type=kinds[kind]) for _, (kind, values) in cols]
    table = pa.Table.from_arrays(arrays, schema=pa.schema(fields))
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, row_group_size=n_rows)


def read_parquet(path: Path) -> dict[str, list]:
    """Read back what write_parquet wrote: column name -> python list. NaN
    doubles come back as float('nan') (a value), never as None."""
    import pyarrow.parquet as pq

    table = pq.read_table(Path(path))
    return {name: table.column(name).to_pylist() for name in table.schema.names}


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
    """AOI precedence: CLI > config/bailasar.yaml via the shared loader
    (AOIs are operational). An unset AOI raises ConfigError — the loader's
    "no made-up values" rule — instead of falling back to a hardcoded bbox."""
    if override:
        return [float(v) for v in override], "CLI --aoi argument"
    cfg = load_config()
    bbox = list(cfg.aoi_bbox(QUAKE_AOI_NAME))
    return bbox, f"config/bailasar.yaml aois.{QUAKE_AOI_NAME} via src/bailasar/config.py"


def _bbox_wkt(aoi: list[float]) -> str:
    w, s, e, n = aoi
    return f"POLYGON(({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))"


def _gunw_pair_dates(granule_id: str) -> tuple[str, str]:
    """(ref_date, sec_date) as YYYYMMDD from a GUNW granule ID: the four
    timestamps are ref start/end then secondary start/end."""
    stamps = re.findall(r"(\d{8}T\d{6})", granule_id)
    if len(stamps) < 4:
        raise RuntimeError(f"cannot parse dates from {granule_id}")
    return stamps[0][:8], stamps[2][:8]  # ref start, secondary start


def discover_pairs(track: int, aoi: list[float]) -> dict[str, dict]:
    """Select the R/C/K GUNW triplet for a track from a read-only ASF search
    (hour-2 gate): C spans the event; R is the pre-event pair immediately
    before C; K is the pre-event pair immediately before R (sharing no
    acquisition with C; its secondary may equal R's reference). Fallback only:
    the primary source of pairs is the gate catalog (pairs_from_catalog)."""
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

    for g in granules:
        g["ref_date"], g["sec_date"] = _gunw_pair_dates(g["granule_id"])
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


def pairs_from_prereg(track: int) -> dict:
    """R/C/K for a track from the frozen pre-registration (config/
    preregistered.yaml → quake.pairs) — the operative source since #134/#131.
    URLs, frame and flight direction are resolved from the gate catalog's
    granule records; a frozen ID absent from the catalog is an error, never a
    fallback to the old catalog K."""
    cfg = load_config()
    triplets = cfg.prereg("quake.pairs")
    triplets = list(triplets) if isinstance(triplets, tuple) else [triplets]
    entry = next(
        (t for t in triplets if dict(t).get("track") == track),
        None,
    )
    if entry is None:
        raise RuntimeError(f"no frozen quake.pairs entry for track {track}")
    catalog = json.loads(GATE_CATALOG_PATH.read_text(encoding="utf-8"))
    records = {
        g["scene_name"]: g
        for g in catalog.get("aois", {}).get(QUAKE_AOI_NAME, {}).get("granules", [])
    }
    pairs: dict = {"C": None, "R": None, "K": None}
    for role, key in (("C", "coevent_C"), ("R", "reference_R"), ("K", "control_K")):
        granule_id = entry.get(key)
        if not granule_id:
            continue
        rec = records.get(granule_id)
        if rec is None:
            raise RuntimeError(
                f"frozen {key} {granule_id} is absent from the gate catalog records; "
                "the catalog is evidence, not a substitute source"
            )
        ref_date, sec_date = _gunw_pair_dates(granule_id)
        pairs[role] = {
            "granule_id": granule_id,
            "url": rec["url"],
            "start_time": rec.get("start_time"),
            "ref_date": ref_date,
            "sec_date": sec_date,
            "baseline_days": int(
                _gunw_pair_dates(granule_id)[1]
                and (
                    datetime.strptime(sec_date, "%Y%m%d").date()
                    - datetime.strptime(ref_date, "%Y%m%d").date()
                ).days
            ),
            "frame": rec.get("frame"),
            "flight_direction": rec.get("flight_direction"),
        }
    pairs["pair_source"] = "config/preregistered.yaml quake.pairs (frozen)"
    pairs["control_K_timing"] = entry.get("control_K_timing")
    pairs["baseline_mismatch"] = entry.get("baseline_mismatch")
    return pairs


def pairs_from_catalog(track: int, catalog_path: Path | None = None) -> dict | None:
    """R/C/K for a track from the hour-2 gate catalog — the gate's frozen
    choice (nisar_colombia_granules_2026.json → quake_triplets), with URLs,
    frame and flight direction resolved from the same catalog's granule
    records. Returns None when the catalog or the track entry is absent (the
    caller then falls back to discover_pairs).

    Baselines are re-derived from the granule IDs and must match the catalog's
    recorded baseline_days, or something was edited after the gate: fail rather
    than paper over it.

    TODO(#86): quake.pairs in config/preregistered.yaml is changing shape;
    when it lands, read the frozen pair IDs from cfg.prereg("quake.pairs") and
    keep this catalog as the gate evidence, not the source.
    """
    path = catalog_path or GATE_CATALOG_PATH
    if not path.exists():
        return None
    catalog = json.loads(path.read_text(encoding="utf-8"))
    entry = next((t for t in catalog.get("quake_triplets", []) if t.get("track") == track), None)
    if entry is None:
        return None
    records = {
        g["scene_name"]: g
        for g in catalog.get("aois", {}).get(QUAKE_AOI_NAME, {}).get("granules", [])
    }
    pairs: dict = {"C": None, "R": None, "K": None}
    for role in ("C", "R", "K"):
        granule_id = entry.get(role)
        if not granule_id:
            continue
        rec = records.get(granule_id)
        if rec is None:
            raise RuntimeError(
                f"{role} granule {granule_id} is in quake_triplets but not in the gate "
                f"catalog granule records for {QUAKE_AOI_NAME}"
            )
        ref_date, sec_date = _gunw_pair_dates(granule_id)
        ref = datetime.strptime(ref_date, "%Y%m%d").date()
        sec = datetime.strptime(sec_date, "%Y%m%d").date()
        baseline = (sec - ref).days
        recorded = entry.get("baseline_days", {}).get(role)
        if recorded is not None and recorded != baseline:
            raise RuntimeError(
                f"{role} baseline from the granule ID ({baseline} d) differs from the "
                f"gate catalog's recorded {recorded} d for {granule_id}"
            )
        pairs[role] = {
            "granule_id": granule_id,
            "url": rec["url"],
            "start_time": rec.get("start_time"),
            "ref_date": ref_date,
            "sec_date": sec_date,
            "baseline_days": baseline,
            "frame": rec.get("frame"),
            "flight_direction": rec.get("flight_direction"),
        }
    pairs["pair_source"] = (
        "nisar_colombia_granules_2026.json quake_triplets (hour-2 gate frozen choice)"
    )
    pairs["catalog_baseline_days"] = entry.get("baseline_days", {})
    pairs["catalog_baseline_mismatch"] = entry.get("baseline_mismatch")
    return pairs


def resolve_pairs(track: int, aoi: list[float]) -> tuple[dict, str]:
    """Frozen pre-registration first (the operative source since #134/#131),
    the gate catalog as evidence, discovery as a cross-check for R and C only:
    the frozen K is a deliberate re-choice (#131) and must not be compared to
    the discovery rule."""
    pairs = pairs_from_prereg(track)
    discovered = None
    try:
        discovered = discover_pairs(track, aoi)
    except Exception as exc:  # noqa: BLE001 - verification only; frozen pairs stand
        print(f"  [WARN] verification ASF discovery failed ({exc}); frozen pairs stand")
    if discovered is not None:
        for role in ("C", "R"):
            frozen_id = pairs.get(role, {}).get("granule_id")
            dsc_id = discovered.get(role, {}).get("granule_id") if discovered.get(role) else None
            if frozen_id != dsc_id:
                print(
                    f"  [WARN] discovered {role} pair {dsc_id} differs from the frozen "
                    f"{frozen_id} — recorded as a finding; the frozen pair stands"
                )
    return pairs, "prereg"


def _new_gunw_filesystem():
    """One authenticated HTTPS filesystem for a single GUNW granule — a fresh
    Earthdata client with socket timeouts (not the memoized earthaccess
    session, which has no read timeout and can stall for hours; docs/kb/
    nisar-gcov-read-timeouts.md, same pattern as flood_polarimetric_math).
    Reader limits, not science thresholds."""
    import aiohttp
    import earthaccess
    import fsspec

    auth = earthaccess.login(strategy="environment", persist=False)
    if not getattr(auth, "authenticated", False):
        auth = earthaccess.login(strategy="netrc", persist=False)
    if not getattr(auth, "authenticated", False):
        raise RuntimeError("Earthdata login failed (strategy environment, then netrc)")
    token = auth.token["access_token"]
    return fsspec.filesystem(
        "https",
        client_kwargs={
            "headers": {"Authorization": f"Bearer {token}"},
            "trust_env": False,
            "timeout": aiohttp.ClientTimeout(sock_connect=SOCK_CONNECT_S, sock_read=SOCK_READ_S),
        },
    )


def _safe_error(exc: BaseException) -> str:
    """One-line, secret-free error for retry prints."""
    text = f"{type(exc).__name__}: {exc}".replace("\n", " ")
    return text[:200]


def load_gunw_window(fs, url: str, aoi: list[float]) -> dict:
    """Stream ONLY the AOI window of the 20 m coherence grid (h5py over fsspec;
    no full download). Returns arrays + grid geometry + product dates."""
    import h5py
    from pyproj import Transformer

    w, s, e, n = aoi
    tr = Transformer.from_crs("EPSG:4326", "EPSG:32618", always_xy=True)
    x0, y0 = tr.transform(w, s)
    x1, y1 = tr.transform(e, n)
    with fs.open(url, "rb", cache_type="blockcache", block_size=FSSPEC_BLOCK_SIZE) as fobj:
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
            if epsg != 32618:
                raise RuntimeError(
                    f"GUNW grid is EPSG:{epsg}, but the AOI-window transform assumes "
                    f"UTM zone 18N (EPSG:32618) for {url}; refusing to mix projections"
                )
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


def _rasterize_units(window: dict, shapes: list, names: dict[int, str], prov: dict):
    """Rasterize (geometry, unit_id) shapes onto the DPM grid by pixel center.
    (x0, y0) is the center of the top-left pixel; id 0 = outside every unit."""
    from rasterio.features import rasterize
    from rasterio.transform import Affine

    sp = float(window["spacing"])
    transform = Affine(sp, 0.0, window["x0"] - sp / 2.0, 0.0, -sp, window["y0"] + sp / 2.0)
    unit_ids = rasterize(
        shapes,
        out_shape=(window["rows"], window["cols"]),
        transform=transform,
        fill=0,
        dtype="int32",
    )
    prov["n_units"] = len(names)
    prov["crs"] = f"EPSG:{window['epsg']} (rasterized at {sp:g} m pixel centers)"
    return unit_ids, names, prov


def fetch_units(
    window: dict,
    aoi: list[float],
    asset: str | None,
    name_prop: str | None,
    units_file: Path | None = None,
    units_id_prop: str | None = None,
):
    """Unit polygons for the DPM grid, from one of two sources (pluggable so
    barrio layers drop in when #24 adopts them):

    - a local GeoJSON/GeoPackage file (--units-file PATH --units-id-prop NAME);
    - a public GEE asset (--units-asset/--units-name-prop; default the labeled
      FAO GAUL ADM2 municipio fallback — barrio polygons are pending per
      validation/README.md).

    Provenance records the source (asset ID, or file path + sha256), the CRS
    and the feature count; unit IDs are stable per source and unique.
    """
    if units_file is not None:
        if asset is not None or name_prop is not None:
            raise RuntimeError("--units-file and --units-asset/--units-name-prop are exclusive")
        return load_units_from_file(window, units_file, units_id_prop)
    if units_id_prop is not None:
        raise RuntimeError("--units-id-prop requires --units-file")
    import ee
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
    shapes = []
    names: dict[int, str] = {}
    for i, f in enumerate(features, start=1):
        geom = f.get("geometry") or {}
        if not geom.get("coordinates"):
            continue
        g = transform_geom("EPSG:4326", f"EPSG:{window['epsg']}", geom)
        shapes.append((g, i))
        names[i] = str(f["properties"].get(name_key, f"unit_{i}"))
    prov = {
        "unit_source": f"asset:{used_asset}",
        "unit_asset": used_asset,
        "unit_name_property": name_key,
        "unit_type": UNIT_FALLBACK_LABEL if "GAUL" in used_asset else used_asset,
        "unit_source_crs": "EPSG:4326",
        "n_source_features": len(features),
        "gee_project": project,
    }
    return _rasterize_units(window, shapes, names, prov)


def load_units_from_file(
    window: dict, units_path: Path, id_prop: str | None
) -> tuple[np.ndarray, dict[int, str], dict]:
    """Units from a local GeoJSON or GeoPackage file (--units-file
    PATH --units-id-prop NAME), rasterized onto the DPM grid locally. geopandas
    reads either format (available transitively via the osmnx dependency);
    geometries are reprojected to the window's UTM grid. The id property must
    identify units uniquely, or the run stops (duplicates are a data error,
    never silently merged). Provenance: path + sha256, CRS, feature count.

    Maru's candidate barrio layers (#97 reports) are NOT downloaded here; the
    loader only makes the code ready for whatever #24 adopts.
    """
    if id_prop is None:
        raise RuntimeError("--units-id-prop is required with --units-file")
    import geopandas as gpd

    units_path = Path(units_path)
    if not units_path.exists():
        raise RuntimeError(f"units file not found: {units_path}")
    gdf = gpd.read_file(units_path)
    if id_prop not in gdf.columns:
        raise RuntimeError(
            f"units file {units_path.name} has no property {id_prop!r}; columns={list(gdf.columns)}"
        )
    if gdf.crs is None:
        raise RuntimeError(f"units file {units_path.name} has no CRS")
    raw_ids = [str(v) for v in gdf[id_prop]]
    dupes = sorted({v for v in raw_ids if raw_ids.count(v) > 1})
    if dupes:
        raise RuntimeError(
            f"--units-id-prop {id_prop!r} values are not unique in {units_path.name}: "
            f"{dupes}; unit IDs must be unique"
        )
    src_crs = str(gdf.crs)
    target = f"EPSG:{window['epsg']}"
    gdf = gdf.to_crs(target)
    shapes = []
    names: dict[int, str] = {}
    for i, (geom, rid) in enumerate(zip(gdf.geometry, raw_ids, strict=True), start=1):
        if geom is None or geom.is_empty:
            continue
        shapes.append((geom, i))
        names[i] = rid
    if not shapes:
        raise RuntimeError(f"no usable geometries in {units_path.name}")
    sha256 = hashlib.sha256(units_path.read_bytes()).hexdigest()
    prov = {
        "unit_source": f"file:{units_path}",
        "unit_file_sha256": sha256,
        "unit_id_property": id_prop,
        "unit_type": f"units from local file ({units_path.name})",
        "unit_source_crs": src_crs,
        "n_source_features": len(raw_ids),
    }
    return _rasterize_units(window, shapes, names, prov)


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


# Summary keys that are pure counts/metadata: the only C/K-pass numbers that
# may be printed while the pre-registration is NOT frozen (brief,
# "C-pair statistics stay sealed"). Everything else (mu, sigma, medians,
# excess, n_px_zero_std) is a sealed statistic.
_SUMMARY_COUNT_KEYS = (
    "n_px_total",
    "n_px_valid",
    "n_px_built_up_valid",
    "n_px_non_built_valid",
    "n_reference_px",
    "n_units_total",
    "n_units_evaluated",
    "n_units_excluded",
    "min_built_up_pixels_per_unit",
    "layover_shadow_mask",
)
_SUMMARY_STAT_KEYS = (
    "mu",
    "sigma",
    "n_px_zero_std",
    "median_z_built_up",
    "median_z_non_built",
    "excess_e",
)


def _summary_line(summary: dict, pairs: dict, is_frozen: bool = False) -> None:
    """Print one pass summary. Until the pre-registration is frozen
    (validation/README.md deviation 1 must not recur) only pixel and unit
    counts are printed, plus the sealed line; μ, σ, median Z per class,
    excess E and any other statistic stay inside local_cache outputs only."""
    _print_pairs(pairs)
    keys = _SUMMARY_COUNT_KEYS if not is_frozen else _SUMMARY_COUNT_KEYS + _SUMMARY_STAT_KEYS
    for key in keys:
        print(f"  {summary['label']}_pass.{key} = {summary[key]}")
    if not is_frozen:
        print(
            "  C/K statistics sealed until pre-registration freeze "
            f"(status={summary.get('prereg_status', '?')})"
        )
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
    parser.add_argument(
        "--units-file",
        type=Path,
        default=None,
        help="local unit polygons (GeoJSON or GeoPackage) instead of a GEE asset",
    )
    parser.add_argument(
        "--units-id-prop",
        default=None,
        help="unique unit ID property for --units-file (e.g. a barrio code)",
    )
    parser.add_argument("--no-control", action="store_true")
    parser.add_argument("--tile", type=int, default=512)
    args = parser.parse_args(argv)

    _load_env()
    cfg = load_config()
    thresholds = load_quake_prereg()
    aoi, aoi_source = resolve_aoi(args.aoi)
    print(f"AOI [W,S,E,N] = {aoi} (source: {aoi_source})")
    print(
        "thresholds from config/preregistered.yaml via src/bailasar/config.py "
        f"(sha1 {cfg.preregistered_hash}, status={cfg.status}): "
        f"built_up>={thresholds['built_up_min_footprint_fraction']}, "
        f"non_built<={thresholds['non_built_max_footprint_fraction']}, "
        f"min_built_up_px={thresholds['min_built_up_pixels_per_unit']}"
    )
    if not cfg.is_frozen:
        print(
            "pre-registration NOT frozen: C/K statistics are computed and stored but "
            "sealed; this run prints counts only"
        )

    pairs, pairs_source = resolve_pairs(args.track, aoi)
    if pairs_source == "catalog":
        print(f"C/R/K for track {args.track} from the hour-2 gate catalog (frozen choice):")
    else:
        print(f"discovered C/R/K on track {args.track} (fallback: ASF read-only search):")
    _print_pairs(pairs)
    k_frame_note = "no K pair"
    if pairs["K"]:
        frames = {role: pairs[role].get("frame") for role in ("C", "R", "K") if pairs[role]}
        if any(f is None for f in frames.values()):
            k_frame_note = f"frame not recorded for every pair (frames {frames})"
        elif len(set(frames.values())) == 1:
            k_frame_note = f"K frame {frames['K']} matches R and C (frames {frames})"
        else:
            k_frame_note = f"K frame {frames['K']} differs from R/C (frames {frames})"
        print(f"  {k_frame_note}")

    windows: dict[str, dict] = {}
    missing_granules: list[dict] = []
    for role in ("C", "R", "K"):
        if role == "K" and (not pairs["K"] or args.no_control):
            print("control pass: SKIPPED (no K pair or --no-control)")
            continue
        g = pairs[role]
        print(f"streaming {role} = {g['granule_id']} (AOI window only, 20 m)...")
        wdw = None
        for attempt in range(GRANULE_ATTEMPTS):
            try:
                fs = _new_gunw_filesystem()
                wdw = load_gunw_window(fs, g["url"], aoi)
                break
            except Exception as exc:  # noqa: BLE001 - retried, then recorded missing
                if attempt >= GRANULE_ATTEMPTS - 1:
                    break
                delay = GRANULE_BACKOFF_S[min(attempt, len(GRANULE_BACKOFF_S) - 1)]
                print(
                    f"  [WARN] {role} read attempt {attempt + 1} failed "
                    f"({_safe_error(exc)}); retrying in {delay:.0f}s"
                )
                time.sleep(delay)
        if wdw is None:
            missing_granules.append(
                {"role": role, "granule_id": g["granule_id"], "status": "missing"}
            )
            print(
                f"  {role} granule {g['granule_id']} unreadable after "
                f"{GRANULE_ATTEMPTS} attempts: recorded as missing"
            )
            continue
        windows[role] = wdw
        print(
            f"  window {wdw['rows']}x{wdw['cols']} px, EPSG:{wdw['epsg']}, "
            f"ref={wdw['ref_time'][:10]} sec={wdw['sec_time'][:10]}, "
            f"coh outside [0,1]: {wdw['n_coh_outside_0_1']} px -> NaN"
        )
    if "C" not in windows or "R" not in windows:
        raise RuntimeError(
            f"both C and R windows are required; missing: "
            f"{[m['role'] + '=' + m['granule_id'] for m in missing_granules]}"
        )
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
        ref_window,
        aoi,
        args.units_asset,
        args.units_name_prop,
        units_file=args.units_file,
        units_id_prop=args.units_id_prop,
    )
    if args.units_file is not None:
        print(
            f"  {unit_prov['n_units']} of {unit_prov['n_source_features']} features from "
            f"{args.units_file.name} (id property {unit_prov['unit_id_property']}, "
            f"sha256 {unit_prov['unit_file_sha256'][:12]}…, CRS {unit_prov['unit_source_crs']})"
        )
    else:
        print(
            f"  {unit_prov['n_units']} units from {unit_prov['unit_source']} "
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
        k_timing = pairs.get("control_K_timing", "pre_event")
        if k_timing == "post_event":
            passes["K"]["summary"]["baseline_mismatch_disclosed"] = (
                f"control: K {pairs['K']['baseline_days']}d, R {pairs['R']['baseline_days']}d "
                "(post-event control: residual demolition/debris/aftershock change is "
                "expected; supports radar-vs-baseline only, never radar-beats-baseline)"
            )
        else:
            passes["K"]["summary"]["baseline_mismatch_disclosed"] = (
                f"control: K {pairs['K']['baseline_days']}d, R {pairs['R']['baseline_days']}d "
                "(both pre-event, mismatch recorded)"
            )

    print(
        "\nDPM results (computed and stored under local_cache/quake/; interpretation "
        "deferred to the pre-registered scorecard):"
    )
    for p in passes.values():
        _summary_line(p["summary"], pairs, is_frozen=cfg.is_frozen)

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
                "unit_source": unit_prov["unit_source"],
                "evaluated": 1 if evaluated else 0,
                "n_built_up_valid_px": s_c["n_px"],
                "n_non_built_valid_px": n_non_built,
                "median_z_built": s_c["median_z"] if evaluated else float("nan"),
                "median_z_built_control": s_k.get("median_z", float("nan")),
            }
        )
    out_dir = args.out_dir
    zarr_path = out_dir / f"dpm_track{args.track}.zarr"
    parquet_path = out_dir / f"dpm_units_track{args.track}.parquet"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_parquet(parquet_path, parquet_columns_from_rows(rows))
    print(
        f"\nwrote {parquet_path} ({len(rows)} unit rows, "
        f"{c_pass['summary']['n_units_excluded']} excluded, counted above; pyarrow)"
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
        "config_loader": "src/bailasar/config.py load_config()",
        "prereg_sha1": cfg.preregistered_hash,
        "prereg_status": cfg.status,
        "prereg_frozen": cfg.is_frozen,
        "pairs": {
            role: {
                "granule_id": pairs[role]["granule_id"],
                "ref_date": pairs[role]["ref_date"],
                "sec_date": pairs[role]["sec_date"],
                "baseline_days": pairs[role]["baseline_days"],
                "frame": pairs[role].get("frame"),
                "flight_direction": pairs[role].get("flight_direction"),
                "provisional": True,
            }
            for role in ("C", "R", "K")
            if pairs[role]
        },
        "pair_source": pairs.get("pair_source", "ASF discovery"),
        "control_K_timing": pairs.get("control_K_timing"),
        "pair_selection": pairs_source,
        "k_frame_note": k_frame_note,
        "missing_granules": missing_granules,
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
