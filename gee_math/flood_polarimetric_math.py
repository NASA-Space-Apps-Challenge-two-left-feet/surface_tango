"""La Mojana dual-pol flood classes from NISAR GCOV HH/HV.

Thresholds are read from ``config/preregistered.yaml`` (``flood:``). They are
literature-typical and uncalibrated. Missing samples stay NaN. When the
dry-baseline rule fails, or when the wettest open-water fraction is 0, Class 2
is null and only absolute water extent is reported.

The CLI writes class rasters under ``local_cache/mojana/`` and ``reports/mojana.md``.
``--lvsc`` only compares the cached open-water masks with Sentinel-1. It writes
the comparison report and ``lvsc_comparison.json``, and it does not rewrite
provenance or cube bands.

Each GCOV is read in its own subprocess: a new HTTPS session, socket timeouts,
two retries, and a hard time limit. The first pass strides to the analysis
grid instead of reading the native window. Three or fewer usable dates block
classification.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from pathlib import Path

import numpy as np
import yaml

# Hour-2 gate bbox [W, S, E, N]. Used only while bailasar.yaml leaves the AOI null.
# Source: briefs/feat/data-mojana-flood.md. It is an estimate, not a frozen threshold.
GATE_AOI_ESTIMATE = (-75.40, 7.90, -74.20, 9.20)

# MERIT Hydro HAND is posted at 3 arc-seconds. 90 m cells in UTM zone 18N
# (La Mojana sits on the zone-18 central meridian) keep hectares equal to
# pixel count times one cell. This is a grid choice, not a flood threshold.
ANALYSIS_CRS = "EPSG:32618"
ANALYSIS_CELL_M = 90.0

# Half of the 12-day NISAR repeat: S1 passes nearest the L-band date.
# Not a backscatter threshold. The comparison composites every IW scene in
# this window; it does not keep only the single nearest slice.
S1_HALF_WINDOW_DAYS = 6
# A stalled Sentinel-1 date is recorded missing. It is not retried into a zero.
S1_DATE_LIMIT_S = 15 * 60
CHIRPS_DAYS = 15

# Reader limits. Not flood thresholds. One session per attempt, then two
# retries. The subprocess limit stops a half-closed socket from stalling the run.
GRANULE_ATTEMPTS = 3
GRANULE_BACKOFF_S = (2.0, 4.0)
GRANULE_LIMIT_S = 20 * 60
FSSPEC_BLOCK_SIZE = 32 * 1024 * 1024
SOCK_CONNECT_S = 30
SOCK_READ_S = 120
# "3 or fewer" usable dates is not enough to classify.
MIN_USABLE_DATES = 4

FREQ_A = "/science/LSAR/GCOV/grids/frequencyA"
_POL_CODES = frozenset({"SH", "SV", "DH", "DV", "CL", "CR", "QP", "NA"})
_HH_HV_PRIMARY = frozenset({"DH", "QP"})
CLASS_NODATA = -1

CLAIM = (
    "Flooding during Jun–Nov 2026 with the Caregato breach still open. "
    "This is not a map of the May 2024 breach. "
    "Seasonal water and breach water are not separated."
)


@dataclass(frozen=True)
class FloodThresholds:
    """Science numbers from config. No defaults: a missing key is an error."""

    open_water_abs_hh_db: float
    class1_delta_hh_db_max: float
    class2_delta_hh_db_min: float
    class2_delta_hv_hh_db_abs_max: float
    hand_max_m: float
    no_baseline_relative_gap: float
    db_step: float
    hand_sensitivity_m: tuple[float, ...]
    uncalibrated: tuple[str, ...]
    source: str


@dataclass(frozen=True)
class DateStats:
    date: str
    granule_ids: tuple[str, ...]
    n_water: int
    n_valid: int


@dataclass(frozen=True)
class BaselineDecision:
    accepted: bool
    reason: str
    reference_date: str | None
    f_wet: str | None
    f_dry: str | None
    f_wet_float: float | None
    f_dry_float: float | None
    gap: str | None
    gap_float: float | None
    gap_limit: float
    wet_dates: tuple[str, ...]
    dry_dates: tuple[str, ...]


@dataclass(frozen=True)
class ClassCounts:
    n_class1: int
    n_valid_class1: int
    n_class2: int
    n_valid_class2: int


@dataclass(frozen=True)
class SensitivityCount:
    name: str
    n_water: int
    n_valid_water: int
    n_class1: int | None
    n_valid_class1: int | None
    n_class2: int | None
    n_valid_class2: int | None


@dataclass(frozen=True)
class DateCube:
    date: str
    granule_ids: tuple[str, ...]
    hh_linear: np.ndarray
    hv_linear: np.ndarray


@dataclass
class DateResult:
    date: str
    granule_ids: tuple[str, ...]
    n_water: int
    n_valid: int
    n_class1: int | None
    n_valid_class1: int | None
    n_class2: int | None
    n_valid_class2: int | None
    water_raster: np.ndarray
    class_raster: np.ndarray | None
    sensitivity: tuple[SensitivityCount, ...]


@dataclass
class Analysis:
    thresholds: FloodThresholds
    baseline: BaselineDecision
    dates: tuple[DateResult, ...]
    pixel_area_m2: float


@dataclass(frozen=True)
class GranuleRef:
    scene_name: str
    date: str
    track: int
    frame: int
    direction: str
    pole: str
    primary_pol: str
    url: str
    provisional: bool
    crid: str

    @property
    def has_hh_hv(self) -> bool:
        if self.primary_pol in _HH_HV_PRIMARY:
            return True
        text = self.pole.upper()
        return "HH" in text and "HV" in text


@dataclass(frozen=True)
class StackChoice:
    key: tuple[int, int, str] | None
    granules: tuple[GranuleRef, ...]
    reason: str
    excluded: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class S1Comparison:
    """C-band check. The dB cut is the L-band open-water figure, borrowed."""

    date: str
    kind: str
    threshold_db: float
    n_positive: int
    n_positive_with_s1: int
    n_positive_s1_missing: int
    n_missed: int
    n_domain: int
    n_s1_water: int
    n_s1_water_not_positive: int
    median_vv_positive: float | None
    median_vh_positive: float | None
    median_vv_domain: float | None
    s1_scene_count: int | None


@dataclass(frozen=True)
class S1Scene:
    """One Sentinel-1 IW GRD scene. Date bounds come from the product name."""

    scene_id: str
    orbit_pass: str
    start: str
    end: str
    relative_orbit: int | None


@dataclass(frozen=True)
class ProvenanceDate:
    """Open-water counts read from provenance. This object does not write them."""

    date: str
    granule_ids: tuple[str, ...]
    n_water: int
    n_valid: int


@dataclass(frozen=True)
class LvscDateResult:
    """One date of the L-band vs C-band open-water comparison.

    ``n_missed`` is None unless the miss fraction is measurable. A date with no
    Sentinel-1 scene, or with no NISAR open water, is not stored as zero misses.
    """

    date: str
    nisar_granule_ids: tuple[str, ...]
    n_open_water: int
    n_valid: int
    n_with_s1: int | None
    n_s1_missing_on_water: int | None
    n_s1_also_water: int | None
    n_missed: int | None
    median_vv_open_water_db: float | None
    scenes: tuple[S1Scene, ...]
    status: str
    detail: str

    @property
    def miss_fraction_text(self) -> str | None:
        """Unreduced missed/finite-S1. None when that denominator is not usable."""
        if self.status != "measured" or self.n_missed is None or self.n_with_s1 is None:
            return None
        if self.n_with_s1 <= 0:
            return None
        return f"{self.n_missed}/{self.n_with_s1}"

    @property
    def miss_fraction(self) -> Fraction | None:
        text = self.miss_fraction_text
        if text is None or self.n_missed is None or self.n_with_s1 is None:
            return None
        return Fraction(self.n_missed, self.n_with_s1)


@dataclass(frozen=True)
class MissFractionSummary:
    """Median and range of measurable per-date miss fractions."""

    n_dates: int
    median: Fraction
    median_text: str
    minimum_text: str
    maximum_text: str
    sorted_text: str
    even_count_averaged: bool


@dataclass(frozen=True)
class GranuleRead:
    hh: np.ndarray
    hv: np.ndarray
    units: str
    bytes_read: int
    seconds: float
    stride_row: int
    stride_col: int
    spacing_y_m: float
    spacing_x_m: float


@dataclass(frozen=True)
class AnalysisGrid:
    crs: str
    transform: tuple[float, float, float, float, float, float]
    width: int
    height: int
    cell_m: float

    @property
    def pixel_area_m2(self) -> float:
        return self.cell_m * self.cell_m

    def affine(self):
        from rasterio.transform import Affine

        return Affine(*self.transform)


@dataclass
class ReportContext:
    command: str
    generated_utc: str
    bbox: tuple[float, float, float, float]
    bbox_source: str
    window: tuple[str, str]
    config_path: str
    config_sha256: str
    granules: tuple[GranuleRef, ...]
    stack: StackChoice | None
    grid_text: str
    hand_source: str
    gcov_units: tuple[tuple[str, str], ...]
    chirps_mm: dict[str, float | None]
    s1: tuple[S1Comparison, ...]
    read_failures: tuple[tuple[str, str], ...]
    notes: tuple[str, ...]
    blocked: str | None = None
    search_count: int = 0


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_env(path: Path | None = None) -> None:
    """Load KEY=VALUE lines. Existing variables win. Values are never printed."""
    env_path = path if path is not None else repo_root() / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_flood_thresholds(path: Path | str) -> FloodThresholds:
    """Read ``flood:`` with yaml.safe_load. Missing keys raise. No hardcoded fallback."""
    source = Path(path)
    doc = yaml.safe_load(source.read_text(encoding="utf-8"))
    flood = doc["flood"]
    sensitivity = flood["sensitivity"]
    labels = doc.get("labels", {}).get("uncalibrated", [])
    return FloodThresholds(
        open_water_abs_hh_db=float(flood["open_water_abs_hh_db"]),
        class1_delta_hh_db_max=float(flood["class1_delta_hh_db_max"]),
        class2_delta_hh_db_min=float(flood["class2_delta_hh_db_min"]),
        class2_delta_hv_hh_db_abs_max=float(flood["class2_delta_hv_hh_db_abs_max"]),
        hand_max_m=float(flood["hand_max_m"]),
        no_baseline_relative_gap=float(flood["no_baseline_relative_gap"]),
        db_step=float(sensitivity["db_step"]),
        hand_sensitivity_m=tuple(float(value) for value in sensitivity["hand_m"]),
        uncalibrated=tuple(str(item) for item in labels),
        source=str(source),
    )


def resolve_bbox(ops_path: Path) -> tuple[tuple[float, float, float, float], str]:
    doc = yaml.safe_load(ops_path.read_text(encoding="utf-8")) or {}
    box = (doc.get("aois") or {}).get("3_la_mojana_caregato")
    if box:
        parsed = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
        return parsed, "config/bailasar.yaml aois.3_la_mojana_caregato"
    return (
        GATE_AOI_ESTIMATE,
        "briefs/feat/data-mojana-flood.md hour-2 gate bbox "
        "(estimate; config/bailasar.yaml aois.3_la_mojana_caregato is null)",
    )


def power_to_db(linear: np.ndarray) -> np.ndarray:
    """10*log10(power). Non-positive and non-finite stay NaN. Never zero-filled."""
    src = np.asarray(linear, dtype=np.float64)
    out = np.full(src.shape, np.nan, dtype=np.float64)
    valid = np.isfinite(src) & (src > 0)
    out[valid] = 10.0 * np.log10(src[valid])
    return out


def db_to_power(db: np.ndarray) -> np.ndarray:
    """Inverse of power_to_db. Non-finite dB stays NaN."""
    src = np.asarray(db, dtype=np.float64)
    out = np.full(src.shape, np.nan, dtype=np.float64)
    valid = np.isfinite(src)
    out[valid] = np.power(10.0, src[valid] / 10.0)
    return out


def mosaic_linear(layers: list[np.ndarray]) -> np.ndarray:
    """Mean of finite linear-power samples. A cell with no sample stays NaN."""
    if not layers:
        raise ValueError("no layers to mosaic")
    shape = np.asarray(layers[0]).shape
    acc = np.zeros(shape, dtype=np.float64)
    count = np.zeros(shape, dtype=np.int32)
    for layer in layers:
        values = np.asarray(layer, dtype=np.float64)
        if values.shape != shape:
            raise ValueError("mosaic layers must share a shape")
        valid = np.isfinite(values)
        acc[valid] += values[valid]
        count[valid] += 1
    out = np.full(shape, np.nan, dtype=np.float64)
    valid = count > 0
    out[valid] = acc[valid] / count[valid]
    return out


def hectares(n_pixels: int, pixel_area_m2: float) -> float:
    return n_pixels * pixel_area_m2 / 10_000.0


def absolute_water_counts(
    hh_db: np.ndarray,
    hand_m: np.ndarray,
    thresholds: FloodThresholds,
) -> tuple[int, int]:
    """Return (n_water, n_valid). Valid: finite HH, finite HAND, HAND < hand_max."""
    valid = np.isfinite(hh_db) & np.isfinite(hand_m) & (hand_m < thresholds.hand_max_m)
    water = valid & (hh_db < thresholds.open_water_abs_hh_db)
    return int(np.count_nonzero(water)), int(np.count_nonzero(valid))


def water_raster(
    hh_db: np.ndarray,
    hand_m: np.ndarray,
    thresholds: FloodThresholds,
) -> np.ndarray:
    """int16: -1 missing, 0 valid and not water, 1 water. Outside HAND stays missing."""
    out = np.full(hh_db.shape, CLASS_NODATA, dtype=np.int16)
    valid = np.isfinite(hh_db) & np.isfinite(hand_m) & (hand_m < thresholds.hand_max_m)
    out[valid] = 0
    out[valid & (hh_db < thresholds.open_water_abs_hh_db)] = 1
    return out


def class_masks(
    hh_db: np.ndarray,
    hv_db: np.ndarray,
    hh_ref_db: np.ndarray,
    hv_ref_db: np.ndarray,
    hand_m: np.ndarray,
    thresholds: FloodThresholds,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Boolean class1, class2, valid1, valid2.

    HV/HH in dB is HV_dB - HH_dB. Class 2 needs a finite ratio on both dates.
    Class 1 needs only finite ΔHH. The two ΔHH tests are mutually exclusive
    for the configured signs; if a config ever overlaps them, class 1 wins
    in the raster and both counts still increment.
    """
    delta_hh = hh_db - hh_ref_db
    delta_ratio = (hv_db - hh_db) - (hv_ref_db - hh_ref_db)
    hand_ok = np.isfinite(hand_m) & (hand_m < thresholds.hand_max_m)
    valid1 = hand_ok & np.isfinite(delta_hh)
    valid2 = valid1 & np.isfinite(delta_ratio)
    class1 = valid1 & (delta_hh < thresholds.class1_delta_hh_db_max)
    class2 = (
        valid2
        & (delta_hh > thresholds.class2_delta_hh_db_min)
        & (np.abs(delta_ratio) < thresholds.class2_delta_hv_hh_db_abs_max)
    )
    return class1, class2, valid1, valid2


def change_class_counts(
    hh_db: np.ndarray,
    hv_db: np.ndarray,
    hh_ref_db: np.ndarray,
    hv_ref_db: np.ndarray,
    hand_m: np.ndarray,
    thresholds: FloodThresholds,
) -> ClassCounts:
    class1, class2, valid1, valid2 = class_masks(
        hh_db, hv_db, hh_ref_db, hv_ref_db, hand_m, thresholds
    )
    return ClassCounts(
        n_class1=int(np.count_nonzero(class1)),
        n_valid_class1=int(np.count_nonzero(valid1)),
        n_class2=int(np.count_nonzero(class2)),
        n_valid_class2=int(np.count_nonzero(valid2)),
    )


def class_raster_from_db(
    hh_db: np.ndarray,
    hv_db: np.ndarray,
    hh_ref_db: np.ndarray,
    hv_ref_db: np.ndarray,
    hand_m: np.ndarray,
    thresholds: FloodThresholds,
) -> np.ndarray:
    """int16: -1 missing, 0 neither class, 1 open-water change, 2 flooded vegetation."""
    class1, class2, valid1, _valid2 = class_masks(
        hh_db, hv_db, hh_ref_db, hv_ref_db, hand_m, thresholds
    )
    out = np.full(hh_db.shape, CLASS_NODATA, dtype=np.int16)
    out[valid1] = 0
    out[class1] = 1
    out[class2 & ~class1] = 2
    return out


def choose_baseline(rows: list[DateStats], gap_limit: float) -> BaselineDecision:
    """Driest date is the minimum open-water fraction.

    No baseline when f_wet is 0 (the ratio is undefined) or when
    (f_wet - f_dry) / f_wet is strictly below ``gap_limit``. Equality keeps
    the baseline. Fractions use integer counts so the boundary is exact.
    Ties on the driest fraction take the earliest date.
    """
    limit = Fraction(gap_limit).limit_denominator(1_000_000)
    usable = [row for row in rows if row.n_valid > 0]
    empty = BaselineDecision(
        accepted=False,
        reason="no_valid_dates",
        reference_date=None,
        f_wet=None,
        f_dry=None,
        f_wet_float=None,
        f_dry_float=None,
        gap=None,
        gap_float=None,
        gap_limit=float(limit),
        wet_dates=(),
        dry_dates=(),
    )
    if not usable:
        return empty

    def fraction_of(row: DateStats) -> Fraction:
        return Fraction(row.n_water, row.n_valid)

    wet = max(fraction_of(row) for row in usable)
    dry = min(fraction_of(row) for row in usable)
    wet_dates = tuple(sorted(row.date for row in usable if fraction_of(row) == wet))
    dry_dates = tuple(sorted(row.date for row in usable if fraction_of(row) == dry))
    if wet == 0:
        return BaselineDecision(
            accepted=False,
            reason="f_wet_zero",
            reference_date=None,
            f_wet=str(wet),
            f_dry=str(dry),
            f_wet_float=float(wet),
            f_dry_float=float(dry),
            gap=None,
            gap_float=None,
            gap_limit=float(limit),
            wet_dates=wet_dates,
            dry_dates=dry_dates,
        )
    drop = (wet - dry) / wet
    accepted = not (drop < limit)
    return BaselineDecision(
        accepted=accepted,
        reason="accepted" if accepted else "relative_gap",
        reference_date=dry_dates[0] if accepted else None,
        f_wet=str(wet),
        f_dry=str(dry),
        f_wet_float=float(wet),
        f_dry_float=float(dry),
        gap=str(drop),
        gap_float=float(drop),
        gap_limit=float(limit),
        wet_dates=wet_dates,
        dry_dates=dry_dates,
    )


def iter_sensitivity(thresholds: FloodThresholds):
    """Nominal, then each dB threshold ± db_step, then each HAND value."""
    yield "nominal", thresholds
    step = thresholds.db_step
    fields = (
        "open_water_abs_hh_db",
        "class1_delta_hh_db_max",
        "class2_delta_hh_db_min",
        "class2_delta_hv_hh_db_abs_max",
    )
    for field in fields:
        base = getattr(thresholds, field)
        yield f"{field}_minus", replace(thresholds, **{field: base - step})
        yield f"{field}_plus", replace(thresholds, **{field: base + step})
    for hand in thresholds.hand_sensitivity_m:
        if hand == thresholds.hand_max_m:
            continue
        yield f"hand_{hand:g}", replace(thresholds, hand_max_m=hand)


def finite_median(values: np.ndarray) -> float | None:
    flat = np.asarray(values, dtype=np.float64).reshape(-1)
    valid = flat[np.isfinite(flat)]
    if valid.size == 0:
        return None
    return float(np.median(valid))


def compare_s1(
    positive: np.ndarray,
    domain: np.ndarray,
    s1_vv_db: np.ndarray,
    s1_vh_db: np.ndarray | None,
    threshold_db: float,
    date: str,
    kind: str,
    s1_scene_count: int | None,
) -> S1Comparison:
    """Count where the borrowed L-band threshold, applied to S1 VV, misses a positive pixel.

    Missing S1 stays missing and is not a miss. The threshold is uncalibrated for C-band.
    """
    positive = np.asarray(positive, dtype=bool) & np.asarray(domain, dtype=bool)
    domain = np.asarray(domain, dtype=bool)
    vv = np.asarray(s1_vv_db, dtype=np.float64)
    finite_vv = np.isfinite(vv)
    s1_water = domain & finite_vv & (vv < threshold_db)
    missed = positive & finite_vv & (vv >= threshold_db)
    vh = np.asarray(s1_vh_db, dtype=np.float64) if s1_vh_db is not None else None
    return S1Comparison(
        date=date,
        kind=kind,
        threshold_db=threshold_db,
        n_positive=int(np.count_nonzero(positive)),
        n_positive_with_s1=int(np.count_nonzero(positive & finite_vv)),
        n_positive_s1_missing=int(np.count_nonzero(positive & ~finite_vv)),
        n_missed=int(np.count_nonzero(missed)),
        n_domain=int(np.count_nonzero(domain)),
        n_s1_water=int(np.count_nonzero(s1_water)),
        n_s1_water_not_positive=int(np.count_nonzero(s1_water & ~positive)),
        median_vv_positive=finite_median(vv[positive]) if np.any(positive) else None,
        median_vh_positive=(
            finite_median(vh[positive]) if vh is not None and np.any(positive) else None
        ),
        median_vv_domain=finite_median(vv[domain]) if np.any(domain) else None,
        s1_scene_count=s1_scene_count,
    )


_S1_PRODUCT_TIMES = re.compile(
    r"^S1[A-D]_[A-Z0-9]+_[A-Z0-9]+_[A-Z0-9]+_(\d{8}T\d{6})_(\d{8}T\d{6})_"
)


def s1_window_bounds(date: str, half_days: int = S1_HALF_WINDOW_DAYS) -> tuple[str, str]:
    """Inclusive start and exclusive end for ``filterDate``.

    ``half_days`` of 6 covers the NISAR date and the six calendar days on
    either side. The exclusive end is the morning after the last included day.
    """
    day = datetime.strptime(date, "%Y-%m-%d").date()
    start = (day - timedelta(days=half_days)).isoformat()
    end = (day + timedelta(days=half_days + 1)).isoformat()
    return start, end


def miss_fraction(n_missed: int, n_with_s1: int) -> Fraction | None:
    """Missed / open-water pixels with finite S1. None when the denominator is 0.

    Missing S1 is not a miss, so the denominator is the finite-S1 count. It
    equals the NISAR open-water count only when every open-water pixel has S1.
    """
    if n_with_s1 < 0 or n_missed < 0:
        raise ValueError("counts must be non-negative")
    if n_missed > n_with_s1:
        raise ValueError("misses cannot exceed the finite-S1 denominator")
    if n_with_s1 == 0:
        return None
    return Fraction(n_missed, n_with_s1)


def _text_or_missing(value: object) -> str:
    if value is None:
        return "missing"
    text = str(value).strip()
    return text or "missing"


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _iso_from_s1_token(token: str) -> str:
    return f"{token[0:4]}-{token[4:6]}-{token[6:8]}T{token[9:11]}:{token[11:13]}:{token[13:15]}Z"


def _ee_millis_to_iso(value: object) -> str | None:
    """Earth Engine ``system:time_start`` is milliseconds since the UTC epoch."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        millis = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(millis):
        return None
    return datetime.fromtimestamp(millis / 1000.0, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def scene_from_ee_row(row: dict) -> S1Scene:
    """Build a scene record. Product-name bounds win over the EE timestamp."""
    raw = _text_or_missing(row.get("scene_id"))
    product = raw.split("/")[-1] if raw != "missing" else "missing"
    match = _S1_PRODUCT_TIMES.match(product) if product != "missing" else None
    if match:
        start = _iso_from_s1_token(match.group(1))
        end = _iso_from_s1_token(match.group(2))
    else:
        start = _ee_millis_to_iso(row.get("time_start")) or "missing"
        end = _ee_millis_to_iso(row.get("time_end")) or "missing"
    return S1Scene(
        scene_id=product,
        orbit_pass=_text_or_missing(row.get("orbit_pass")),
        start=start,
        end=end,
        relative_orbit=_optional_int(row.get("relative_orbit")),
    )


def _blank_lvsc(
    date: str,
    granule_ids: tuple[str, ...],
    n_open_water: int,
    n_valid: int,
    status: str,
    detail: str,
    scenes: tuple[S1Scene, ...] = (),
    n_with_s1: int | None = None,
    n_s1_missing_on_water: int | None = None,
) -> LvscDateResult:
    return LvscDateResult(
        date=date,
        nisar_granule_ids=granule_ids,
        n_open_water=n_open_water,
        n_valid=n_valid,
        n_with_s1=n_with_s1,
        n_s1_missing_on_water=n_s1_missing_on_water,
        n_s1_also_water=None,
        n_missed=None,
        median_vv_open_water_db=None,
        scenes=scenes,
        status=status,
        detail=detail,
    )


def lvsc_result_for_date(
    date: str,
    nisar_granule_ids: tuple[str, ...],
    n_open_water: int,
    n_valid: int,
    scenes: tuple[S1Scene, ...],
    comparison: S1Comparison | None,
    error: str | None = None,
) -> LvscDateResult:
    """Turn one date's mask and S1 composite into a report row.

    Zero open water and an empty scene list stay non-numeric. They are not
    recorded as zero misses.
    """
    if n_open_water < 0 or n_valid < 0:
        raise ValueError("counts must be non-negative")
    if n_open_water == 0:
        return _blank_lvsc(
            date,
            nisar_granule_ids,
            0,
            n_valid,
            "no_open_water",
            "no NISAR open water (denominator 0)",
        )
    if error:
        return _blank_lvsc(
            date,
            nisar_granule_ids,
            n_open_water,
            n_valid,
            "missing",
            error,
            scenes=scenes,
        )
    if not scenes:
        return _blank_lvsc(
            date,
            nisar_granule_ids,
            n_open_water,
            n_valid,
            "no_s1",
            "no S1 within window",
        )
    if comparison is None:
        return _blank_lvsc(
            date,
            nisar_granule_ids,
            n_open_water,
            n_valid,
            "missing",
            "comparison was not computed",
            scenes=scenes,
        )
    if comparison.n_positive != n_open_water:
        return _blank_lvsc(
            date,
            nisar_granule_ids,
            n_open_water,
            n_valid,
            "missing",
            (f"open-water count {n_open_water} != comparison positive {comparison.n_positive}"),
            scenes=scenes,
        )
    if comparison.n_positive_with_s1 == 0:
        return _blank_lvsc(
            date,
            nisar_granule_ids,
            n_open_water,
            n_valid,
            "not_measurable",
            "no finite S1 on the NISAR open-water pixels",
            scenes=scenes,
            n_with_s1=0,
            n_s1_missing_on_water=comparison.n_positive_s1_missing,
        )
    n_also = comparison.n_positive_with_s1 - comparison.n_missed
    if n_also < 0:
        return _blank_lvsc(
            date,
            nisar_granule_ids,
            n_open_water,
            n_valid,
            "missing",
            "S1 miss count exceeds the finite-S1 denominator",
            scenes=scenes,
        )
    # Raises if the counts are inconsistent. A raised error is a programming
    # fault, not a missing scene.
    miss_fraction(comparison.n_missed, comparison.n_positive_with_s1)
    return LvscDateResult(
        date=date,
        nisar_granule_ids=nisar_granule_ids,
        n_open_water=n_open_water,
        n_valid=n_valid,
        n_with_s1=comparison.n_positive_with_s1,
        n_s1_missing_on_water=comparison.n_positive_s1_missing,
        n_s1_also_water=n_also,
        n_missed=comparison.n_missed,
        median_vv_open_water_db=comparison.median_vv_positive,
        scenes=scenes,
        status="measured",
        detail="measured",
    )


def _fraction_tie_text(rows: list[LvscDateResult]) -> str:
    return ", ".join(f"{item.miss_fraction_text} on {item.date}" for item in rows)


def summarize_miss_fractions(
    results: tuple[LvscDateResult, ...] | list[LvscDateResult],
) -> MissFractionSummary | None:
    """Median and range over dates whose miss fraction is measurable.

    An even count uses the mean of the two central fractions. Dates with no
    S1, no open water, or a failed fetch are left out of the median.
    """
    measured = [
        item for item in results if item.status == "measured" and item.miss_fraction is not None
    ]
    if not measured:
        return None
    ranked = sorted(
        measured,
        key=lambda item: (item.miss_fraction if item.miss_fraction is not None else 0, item.date),
    )
    n_dates = len(ranked)
    even = n_dates % 2 == 0
    if even:
        left = ranked[n_dates // 2 - 1]
        right = ranked[n_dates // 2]
        left_fraction = left.miss_fraction
        right_fraction = right.miss_fraction
        if left_fraction is None or right_fraction is None:
            return None
        median = (left_fraction + right_fraction) / 2
        median_text = (
            f"({left.miss_fraction_text} + {right.miss_fraction_text}) / 2 "
            f"= {median.numerator}/{median.denominator}"
        )
    else:
        middle = ranked[n_dates // 2]
        median = middle.miss_fraction
        if median is None:
            return None
        median_text = f"{middle.miss_fraction_text}"
    minimum = ranked[0].miss_fraction
    maximum = ranked[-1].miss_fraction
    if minimum is None or maximum is None:
        return None
    return MissFractionSummary(
        n_dates=n_dates,
        median=median,
        median_text=median_text,
        minimum_text=_fraction_tie_text([item for item in ranked if item.miss_fraction == minimum]),
        maximum_text=_fraction_tie_text([item for item in ranked if item.miss_fraction == maximum]),
        sorted_text=", ".join(f"{item.date} {item.miss_fraction_text}" for item in ranked),
        even_count_averaged=even,
    )


def duplicate_scene_note(results: tuple[LvscDateResult, ...] | list[LvscDateResult]) -> str | None:
    """Scene IDs that share a start and end. Both stay in the median."""
    parts: list[str] = []
    for item in results:
        groups: dict[tuple[str, str], list[str]] = {}
        for scene in item.scenes:
            groups.setdefault((scene.start, scene.end), []).append(scene.scene_id)
        for ids in groups.values():
            if len(ids) > 1:
                parts.append(f"{item.date}: {', '.join(ids)}")
    if not parts:
        return None
    return (
        "These scene IDs share a start and end. The collection returned each of "
        "them, and the median kept them all: " + "; ".join(parts) + "."
    )


def _md_cell(value: object) -> str:
    return str(value).replace("|", "/").replace("\n", " ")


def _lvsc_numeric_cells(item: LvscDateResult) -> tuple[str, str, str, str, str]:
    """Finite denominator, also-water, missed, fraction, scene-id cell."""
    if item.status == "no_open_water":
        return (
            "no NISAR open water (denominator 0)",
            "not measurable",
            "not measurable",
            "not measurable",
            "not compared",
        )
    if item.status == "no_s1":
        return (
            "no S1 within window",
            "not measurable",
            "not measurable",
            "not measurable",
            "no S1 within window",
        )
    if item.status == "not_measurable":
        missing = item.n_s1_missing_on_water
        finite = "0" if item.n_with_s1 == 0 else "not measurable"
        detail = item.detail if missing is None else f"{item.detail}; S1 missing {missing}"
        return (finite, "not measurable", "not measurable", "not measurable", _md_cell(detail))
    if item.status != "measured" or item.miss_fraction_text is None:
        return (
            "not measurable",
            "not measurable",
            "not measurable",
            "not measurable",
            _md_cell(item.detail),
        )
    scene_ids = ", ".join(scene.scene_id for scene in item.scenes) or "missing"
    return (
        str(item.n_with_s1),
        str(item.n_s1_also_water),
        str(item.n_missed),
        item.miss_fraction_text,
        scene_ids,
    )


def render_lvsc_report(
    results: tuple[LvscDateResult, ...] | list[LvscDateResult],
    *,
    command: str,
    generated_utc: str,
    config_path: str,
    config_sha256: str,
    threshold_db: float,
    bbox: tuple[float, float, float, float],
    bbox_source: str,
    provenance_generated_utc: str,
    provenance_config_sha256: str,
    grid_text: str,
    prior_note: str | None = None,
) -> str:
    """Markdown for the all-dates L-band vs C-band comparison."""
    summary = summarize_miss_fractions(results)
    lines = [
        "# L-band vs C-band open water, all La Mojana dates",
        "",
        "NISAR L2 GCOV products in this window are **PROVISIONAL** (processing type `PR`).",
        "The open-water cut is **uncalibrated**. Sentinel-1 uses that same frozen number.",
        "It is not an S1 calibration.",
        "",
        "Seasonal water and breach water are not separated. "
        "This is not a map of the May 2024 breach.",
        "Change classes were not recomputed. They remain degenerate under the frozen "
        "reference-date rule (issue #26).",
        "",
        "## Reproduce",
        "",
        f"- Command: `{command}`",
        f"- Generated (UTC): {generated_utc}",
        f"- Config: `{config_path}`",
        f"- Config sha256: `{config_sha256}`",
        (
            f"- Open-water cut: VV < {threshold_db:g} dB "
            "(`flood.open_water_abs_hh_db`, read from the config above)"
        ),
        "- Sentinel-1: `COPERNICUS/S1_GRD`, IW, VV and VH, median of every scene in the window",
        (
            f"- Window: ±{S1_HALF_WINDOW_DAYS} days. `filterDate` start is inclusive and end "
            "is exclusive, so the last included calendar day is the NISAR date plus "
            f"{S1_HALF_WINDOW_DAYS} days."
        ),
        "- Sampling: `ee.data.computePixels` onto the cached analysis grid. "
        'No `.resample("nearest")`.',
        (
            "- NISAR open water: cached `water_extent_<date>.tif` value 1, checked against "
            f"`local_cache/mojana/provenance.json` (generated {provenance_generated_utc}, "
            f"config sha256 `{provenance_config_sha256}`). "
            "This command did not write that file or the cube bands."
        ),
        f"- AOI [W, S, E, N]: [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}]",
        f"- AOI source: {bbox_source}",
        f"- Grid: {grid_text}",
        "",
        "A NISAR open-water pixel is missed when its Sentinel-1 VV is finite and is not "
        f"below {threshold_db:g} dB. Pixels with missing Sentinel-1 stay missing and are not "
        "counted as misses. The miss denominator is the number of NISAR open-water pixels "
        "with finite Sentinel-1 VV. A date with no IW scene in the window is `no S1 within "
        "window` and is not given a zero miss.",
        "",
    ]
    if prior_note:
        lines.append(prior_note)
        lines.append("")
    lines.extend(["## Summary", ""])
    if summary is None:
        lines.append("No measurable miss fraction. The median and the range are not reported.")
    else:
        even_clause = ""
        if summary.even_count_averaged:
            even_clause = (
                f", the mean of the two central fractions because {summary.n_dates} is even"
            )
        lines.append(
            f"Measurable dates: {summary.n_dates} "
            "(NISAR open water with finite Sentinel-1 on those pixels)."
        )
        lines.append(
            f"Median miss fraction: {summary.median_text} "
            f"({float(summary.median):.6f}){even_clause} *(measured, PROVISIONAL, uncalibrated)*."
        )
        lines.append(
            f"Range: minimum {summary.minimum_text}; maximum {summary.maximum_text} "
            "*(measured, PROVISIONAL, uncalibrated)*."
        )
        lines.append(f"Fractions used, sorted by value then date: {summary.sorted_text}.")
    held_out = [item for item in results if item.status != "measured"]
    if held_out:
        held = "; ".join(f"{item.date} {item.detail}" for item in held_out)
        lines.append(f"Not in the median: {held}.")
    lines.extend(
        [
            "",
            "## Per-date comparison",
            "",
            "The miss fraction is S1 missed / finite S1 on NISAR open-water pixels. "
            "Every count below is *(measured, PROVISIONAL, uncalibrated)* unless the cell "
            "says the fraction is not measurable.",
            "",
            "| Date | NISAR open-water px | Finite S1 denominator | "
            "S1 also water | S1 missed | Miss fraction | S1 scene IDs |",
            "|---|---:|---|---:|---:|---|---|",
        ]
    )
    for item in results:
        finite, also, missed, fraction, scenes = _lvsc_numeric_cells(item)
        lines.append(
            f"| {item.date} | {item.n_open_water} | {_md_cell(finite)} | "
            f"{_md_cell(also)} | {_md_cell(missed)} | {_md_cell(fraction)} | "
            f"{_md_cell(scenes)} |"
        )
    unequal = [
        item
        for item in results
        if item.status == "measured" and item.n_with_s1 != item.n_open_water
    ]
    lines.append("")
    if unequal:
        listed = ", ".join(
            f"{item.date} ({item.n_with_s1}/{item.n_open_water} finite)" for item in unequal
        )
        lines.append(
            "On these dates the finite-S1 denominator is smaller than the NISAR "
            f"open-water count, because some open-water pixels have no S1: {listed}."
        )
    else:
        measured_rows = [item for item in results if item.status == "measured"]
        if measured_rows:
            lines.append(
                "On every measurable date the finite-S1 denominator equals the "
                "NISAR open-water count."
            )
    lines.extend(["", "## Scenes", ""])
    for item in results:
        lines.append(f"### {item.date}")
        lines.append("")
        granules = ", ".join(item.nisar_granule_ids) or "missing"
        lines.append(f"NISAR granules: {granules}.")
        if item.status == "measured":
            start, end = s1_window_bounds(item.date)
            lines.append(
                f"Sentinel-1 window {start} inclusive to {end} exclusive "
                f"(±{S1_HALF_WINDOW_DAYS} days). Scenes in the median: {len(item.scenes)}."
            )
            if item.median_vv_open_water_db is None:
                lines.append("Median S1 VV on NISAR open-water pixels: missing.")
            else:
                lines.append(
                    "Median S1 VV on NISAR open-water pixels with finite S1: "
                    f"{item.median_vv_open_water_db:.3f} dB, "
                    f"denominator {item.n_with_s1} *(measured)*."
                )
            lines.append("")
            lines.append("| Scene ID | Pass | Start | End | Relative orbit |")
            lines.append("|---|---|---|---|---|")
            for scene in item.scenes:
                orbit = "missing" if scene.relative_orbit is None else str(scene.relative_orbit)
                lines.append(
                    f"| {_md_cell(scene.scene_id)} | {_md_cell(scene.orbit_pass)} | "
                    f"{_md_cell(scene.start)} | {_md_cell(scene.end)} | {orbit} |"
                )
        else:
            lines.append(item.detail)
        lines.append("")
    notes = [
        "## Notes",
        "",
        "- The composite is the median of every IW GRD scene in the ±"
        f"{S1_HALF_WINDOW_DAYS} day window, the same construction as the "
        "2026-07-11 comparison in `reports/mojana.md`.",
        "- A date with no matching scene stays `no S1 within window`. It is not zero-filled.",
        "- Thresholds were read from the frozen config and were not edited.",
    ]
    duplicate_note = duplicate_scene_note(results)
    if duplicate_note:
        notes.append(f"- {duplicate_note}")
    notes.append("")
    lines.extend(notes)
    return "\n".join(lines)


def _db_pair(cube: DateCube) -> tuple[np.ndarray, np.ndarray]:
    return power_to_db(cube.hh_linear), power_to_db(cube.hv_linear)


def _sensitivity_rows(
    hh_db: np.ndarray,
    hv_db: np.ndarray,
    hh_ref: np.ndarray | None,
    hv_ref: np.ndarray | None,
    hand_m: np.ndarray,
    thresholds: FloodThresholds,
    with_classes: bool,
) -> tuple[SensitivityCount, ...]:
    rows: list[SensitivityCount] = []
    for name, scenario in iter_sensitivity(thresholds):
        n_water, n_valid = absolute_water_counts(hh_db, hand_m, scenario)
        if with_classes and hh_ref is not None and hv_ref is not None:
            counts = change_class_counts(hh_db, hv_db, hh_ref, hv_ref, hand_m, scenario)
            rows.append(
                SensitivityCount(
                    name=name,
                    n_water=n_water,
                    n_valid_water=n_valid,
                    n_class1=counts.n_class1,
                    n_valid_class1=counts.n_valid_class1,
                    n_class2=counts.n_class2,
                    n_valid_class2=counts.n_valid_class2,
                )
            )
        else:
            rows.append(
                SensitivityCount(
                    name=name,
                    n_water=n_water,
                    n_valid_water=n_valid,
                    n_class1=None,
                    n_valid_class1=None,
                    n_class2=None,
                    n_valid_class2=None,
                )
            )
    return tuple(rows)


def classify_stack(
    dates: list[DateCube],
    hand_m: np.ndarray,
    thresholds: FloodThresholds,
    pixel_area_m2: float,
) -> Analysis:
    """Run the dry-baseline rule and, when it passes, both change classes."""
    prepared = [(cube, *_db_pair(cube)) for cube in dates]
    stats = []
    for cube, hh_db, _hv_db in prepared:
        n_water, n_valid = absolute_water_counts(hh_db, hand_m, thresholds)
        stats.append(DateStats(cube.date, cube.granule_ids, n_water, n_valid))
    decision = choose_baseline(stats, thresholds.no_baseline_relative_gap)
    by_date = {cube.date: (cube, hh_db, hv_db) for cube, hh_db, hv_db in prepared}
    ref_arrays = by_date.get(decision.reference_date) if decision.reference_date else None

    results: list[DateResult] = []
    for cube, hh_db, hv_db in prepared:
        n_water, n_valid = absolute_water_counts(hh_db, hand_m, thresholds)
        water = water_raster(hh_db, hand_m, thresholds)
        n_class1 = n_valid1 = n_class2 = n_valid2 = None
        classes = None
        with_classes = False
        hh_ref = hv_ref = None
        if decision.accepted and ref_arrays is not None and cube.date != decision.reference_date:
            _ref_cube, hh_ref, hv_ref = ref_arrays
            counts = change_class_counts(hh_db, hv_db, hh_ref, hv_ref, hand_m, thresholds)
            n_class1 = counts.n_class1
            n_valid1 = counts.n_valid_class1
            n_class2 = counts.n_class2
            n_valid2 = counts.n_valid_class2
            classes = class_raster_from_db(hh_db, hv_db, hh_ref, hv_ref, hand_m, thresholds)
            with_classes = True
        results.append(
            DateResult(
                date=cube.date,
                granule_ids=cube.granule_ids,
                n_water=n_water,
                n_valid=n_valid,
                n_class1=n_class1,
                n_valid_class1=n_valid1,
                n_class2=n_class2,
                n_valid_class2=n_valid2,
                water_raster=water,
                class_raster=classes,
                sensitivity=_sensitivity_rows(
                    hh_db, hv_db, hh_ref, hv_ref, hand_m, thresholds, with_classes
                ),
            )
        )
    return Analysis(
        thresholds=thresholds,
        baseline=decision,
        dates=tuple(results),
        pixel_area_m2=pixel_area_m2,
    )


def pole_token(scene_name: str) -> str | None:
    stem = Path(scene_name).name
    if stem.endswith(".h5"):
        stem = stem[:-3]
    for token in stem.split("_"):
        if len(token) == 4 and token[:2] in _POL_CODES and token[2:] in _POL_CODES:
            return token
    return None


def parse_scene_name(scene_name: str) -> dict[str, str | int]:
    """Parse the NISAR GCOV name. Positions follow the L2 naming convention."""
    stem = Path(scene_name).name
    if stem.endswith(".h5"):
        stem = stem[:-3]
    parts = stem.split("_")
    info: dict[str, str | int] = {}
    if len(parts) > 9 and parts[0] == "NISAR" and parts[3] == "GCOV":
        info["processing_type"] = parts[2]
        info["track"] = int(parts[5])
        info["direction"] = parts[6]
        info["frame"] = int(parts[7])
        info["pole"] = parts[9]
    for token in parts:
        if len(token) == 15 and "T" in token and token[:8].isdigit():
            info["start_token"] = token
            break
    for token in parts:
        if len(token) == 6 and token[0].isalpha() and token[1:].isdigit():
            info["crid"] = token
            break
    return info


def _date_from_text(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) >= 10 and value[4] == "-" and value[7] == "-":
        return value[:10]
    if len(value) >= 8 and value[:8].isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return None


def granule_from_properties(props: dict) -> GranuleRef | None:
    scene = str(props.get("sceneName") or props.get("fileID") or "")
    if not scene:
        return None
    parsed = parse_scene_name(scene)
    pole = str(parsed.get("pole") or pole_token(scene) or props.get("polarization") or "")
    primary = pole[:2] if len(pole) >= 2 else str(props.get("polarization") or "")
    direction = str(parsed.get("direction") or "")
    if not direction:
        flight = str(props.get("flightDirection") or "").upper()
        if flight.startswith("ASC"):
            direction = "A"
        elif flight.startswith("DESC"):
            direction = "D"
        else:
            direction = flight[:1]
    track = parsed.get("track")
    if track is None and props.get("pathNumber") is not None:
        track = int(props["pathNumber"])
    frame = parsed.get("frame")
    if frame is None and props.get("frameNumber") is not None:
        frame = int(props["frameNumber"])
    if track is None or frame is None or not direction:
        return None
    date = _date_from_text(str(props.get("startTime") or "")) or _date_from_text(
        str(parsed.get("start_token") or "")
    )
    if date is None:
        return None
    processing = str(parsed.get("processing_type") or "")
    return GranuleRef(
        scene_name=scene,
        date=date,
        track=int(track),
        frame=int(frame),
        direction=direction,
        pole=pole,
        primary_pol=primary,
        url=str(props.get("url") or ""),
        provisional=processing == "PR",
        crid=str(parsed.get("crid") or ""),
    )


def select_stack(granules: list[GranuleRef]) -> StackChoice:
    """Longest same-track HH/HV series. Change detection does not mix tracks."""
    excluded: list[tuple[str, str]] = []
    groups: dict[tuple[int, int, str], list[GranuleRef]] = defaultdict(list)
    for granule in granules:
        if granule.has_hh_hv:
            groups[(granule.track, granule.frame, granule.direction)].append(granule)
        else:
            excluded.append(
                (
                    granule.scene_name,
                    f"primary pol {granule.primary_pol or granule.pole} has no HH and HV",
                )
            )
    if not groups:
        return StackChoice(None, (), "no dual-pol HH/HV GCOV in the search", tuple(excluded))

    def rank(item: tuple[tuple[int, int, str], list[GranuleRef]]):
        key, items = item
        n_dates = len({g.date for g in items})
        return (-n_dates, -len(items), key[0], key[1], key[2])

    ranked = sorted(groups.items(), key=rank)
    best_key, best_items = ranked[0]
    for key, items in ranked[1:]:
        for granule in items:
            excluded.append(
                (
                    granule.scene_name,
                    f"other stack track {key[0]} frame {key[1]} {key[2]}",
                )
            )
    n_dates = len({g.date for g in best_items})
    reason = (
        f"most acquisition dates ({n_dates}) with HH and HV on "
        f"track {best_key[0]} frame {best_key[1]} direction {best_key[2]}"
    )
    ordered = tuple(sorted(best_items, key=lambda g: (g.date, g.scene_name)))
    return StackChoice(best_key, ordered, reason, tuple(excluded))


def headline_date(analysis: Analysis) -> str | None:
    """Latest date among those tied for the highest open-water fraction."""
    if not analysis.baseline.wet_dates:
        return None
    return analysis.baseline.wet_dates[-1]


def build_grid(
    bbox: tuple[float, float, float, float],
    cell_m: float = ANALYSIS_CELL_M,
    crs: str = ANALYSIS_CRS,
) -> AnalysisGrid:
    from rasterio.warp import transform_bounds

    west, south, east, north = bbox
    left, bottom, right, top = transform_bounds(
        "EPSG:4326", crs, west, south, east, north, densify_pts=21
    )
    left_s = math.floor(left / cell_m) * cell_m
    bottom_s = math.floor(bottom / cell_m) * cell_m
    right_s = math.ceil(right / cell_m) * cell_m
    top_s = math.ceil(top / cell_m) * cell_m
    width = int(round((right_s - left_s) / cell_m))
    height = int(round((top_s - bottom_s) / cell_m))
    # North-up: row 0 is the northern edge.
    transform = (cell_m, 0.0, left_s, 0.0, -cell_m, top_s)
    return AnalysisGrid(crs=crs, transform=transform, width=width, height=height, cell_m=cell_m)


def resample_power_mean(
    source: np.ndarray,
    x_centers: np.ndarray,
    y_centers: np.ndarray,
    src_crs: str,
    grid: AnalysisGrid,
) -> np.ndarray:
    """Mean of finite linear-power samples whose centers fall in each grid cell.

    Non-finite samples are skipped. A destination cell with no sample stays NaN.
    ``x_centers`` and ``y_centers`` are pixel centers, one per column and row.
    """
    values = np.asarray(source, dtype=np.float64)
    x_centers = np.asarray(x_centers, dtype=np.float64).reshape(-1)
    y_centers = np.asarray(y_centers, dtype=np.float64).reshape(-1)
    if values.shape != (y_centers.size, x_centers.size):
        if values.shape == (x_centers.size, y_centers.size):
            values = values.T
        else:
            raise ValueError(
                f"power array shape {values.shape} does not match "
                f"coordinates {(y_centers.size, x_centers.size)}"
            )
    acc = np.zeros((grid.height, grid.width), dtype=np.float64)
    count = np.zeros((grid.height, grid.width), dtype=np.int32)
    inverse = ~grid.affine()
    row_block = 512
    for row0 in range(0, values.shape[0], row_block):
        row1 = min(values.shape[0], row0 + row_block)
        block = values[row0:row1]
        y_block = y_centers[row0:row1]
        x_dest, y_dest = _centers_in_grid_crs(x_centers, y_block, src_crs, grid.crs)
        # Broadcast centers to the block.
        x_grid = np.broadcast_to(x_dest, block.shape)
        y_grid = np.broadcast_to(y_dest, block.shape)
        cols = np.floor(inverse.a * x_grid + inverse.b * y_grid + inverse.c).astype(np.int32)
        rows = np.floor(inverse.d * x_grid + inverse.e * y_grid + inverse.f).astype(np.int32)
        valid = np.isfinite(block) & (block >= 0)
        inside = valid & (rows >= 0) & (rows < grid.height) & (cols >= 0) & (cols < grid.width)
        if not np.any(inside):
            continue
        np.add.at(acc, (rows[inside], cols[inside]), block[inside])
        np.add.at(count, (rows[inside], cols[inside]), 1)
    out = np.full((grid.height, grid.width), np.nan, dtype=np.float64)
    good = count > 0
    out[good] = acc[good] / count[good]
    return out


def _centers_in_grid_crs(
    x_centers: np.ndarray,
    y_centers: np.ndarray,
    src_crs: str,
    dst_crs: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Return X (1, n) and Y (m, 1) center coordinates in the destination CRS."""
    if src_crs == dst_crs:
        return x_centers.reshape(1, -1), y_centers.reshape(-1, 1)
    from rasterio.warp import transform as warp_transform

    # Transform the two axes by pairing each with the opposite axis median,
    # then the full block is the outer sum only if the axes are separable.
    # UTM/geographic are not separable that way, so transform the full mesh
    # for the (small) row block the caller passes.
    x_mesh = np.broadcast_to(x_centers.reshape(1, -1), (y_centers.size, x_centers.size))
    y_mesh = np.broadcast_to(y_centers.reshape(-1, 1), (y_centers.size, x_centers.size))
    tx, ty = warp_transform(src_crs, dst_crs, x_mesh.ravel(), y_mesh.ravel())
    x_dest = np.asarray(tx, dtype=np.float64).reshape(x_mesh.shape)
    y_dest = np.asarray(ty, dtype=np.float64).reshape(y_mesh.shape)
    return x_dest, y_dest


def write_class_geotiff(
    path: Path,
    array: np.ndarray,
    grid: AnalysisGrid,
    description: str,
) -> None:
    """Write an int16 class raster. Nodata is -1 (missing). Values are never filled with 0."""
    import rasterio

    path.parent.mkdir(parents=True, exist_ok=True)
    profile: dict = {
        "driver": "GTiff",
        "height": int(array.shape[0]),
        "width": int(array.shape[1]),
        "count": 1,
        "dtype": "int16",
        "crs": grid.crs,
        "transform": grid.affine(),
        "nodata": CLASS_NODATA,
        "compress": "deflate",
    }
    if array.shape[0] >= 256 and array.shape[1] >= 256:
        profile["tiled"] = True
        profile["blockxsize"] = 256
        profile["blockysize"] = 256
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.asarray(array, dtype=np.int16), 1)
        dst.set_band_description(1, description[:1000])


def write_rasters(analysis: Analysis, grid: AnalysisGrid, cache_dir: Path) -> list[Path]:
    written: list[Path] = []
    for result in analysis.dates:
        if result.n_valid == 0 and (result.class_raster is None):
            continue
        water_path = cache_dir / f"water_extent_{result.date}.tif"
        write_class_geotiff(
            water_path,
            result.water_raster,
            grid,
            "absolute water: 1 water, 0 valid not water, -1 missing; uncalibrated",
        )
        written.append(water_path)
        if result.class_raster is not None:
            class_path = cache_dir / f"change_class_{result.date}.tif"
            write_class_geotiff(
                class_path,
                result.class_raster,
                grid,
                "change class: 1 open water, 2 flooded vegetation, "
                "0 neither, -1 missing; uncalibrated",
            )
            written.append(class_path)
    return written


def _fmt_ha(n_pixels: int, pixel_area_m2: float) -> str:
    return f"{n_pixels} pixels, {hectares(n_pixels, pixel_area_m2):.2f} ha, "


def _range_text(rows: tuple[SensitivityCount, ...], attr: str, pixel_area_m2: float) -> str:
    pairs = [(row.name, getattr(row, attr)) for row in rows if getattr(row, attr) is not None]
    if not pairs:
        return "null"
    lo = min(pairs, key=lambda item: item[1])
    hi = max(pairs, key=lambda item: item[1])
    return (
        f"{hectares(lo[1], pixel_area_m2):.2f} to {hectares(hi[1], pixel_area_m2):.2f} ha "
        f"(pixel counts {lo[1]} at {lo[0]} to {hi[1]} at {hi[0]}) *(measured)*"
    )


def render_report(analysis: Analysis | None, context: ReportContext) -> str:
    lines: list[str] = [
        "# La Mojana dual-pol flood classes",
        "",
        "NISAR L2 GCOV products in this window are **PROVISIONAL** (processing type `PR`).",
        "Thresholds below are **uncalibrated**. They were read from "
        f"`{context.config_path}` and were not fitted to this scene.",
        "",
        CLAIM,
        "",
        "## Reproduce",
        "",
        f"- Command: `{context.command}`",
        f"- Generated (UTC): {context.generated_utc}",
        f"- Config sha256: `{context.config_sha256}`",
        f"- Search window: {context.window[0]} to {context.window[1]} (inclusive)",
        f"- AOI [W, S, E, N]: {list(context.bbox)}",
        f"- AOI source: {context.bbox_source}",
        f"- Granules returned by the search: {context.search_count} *(measured)*",
        "",
    ]
    if context.blocked:
        lines.extend(
            [
                "## Blocked",
                "",
                context.blocked,
                "",
                "Hectares were not computed. No class raster was written from a failed input.",
                "Class 2 = null.",
                "",
            ]
        )
    lines.extend(["## Granules", ""])
    if not context.granules:
        lines.append("No GCOV granules were returned.")
    else:
        lines.append(
            "| Scene | Date | Track | Frame | Dir | Pole | CRID | Provisional | URL present |"
        )
        lines.append("|---|---|---:|---:|---|---|---|---|---|")
        for granule in context.granules:
            present = "yes" if granule.url else "no"
            provisional = "yes" if granule.provisional else "no"
            crid = granule.crid or "missing"
            lines.append(
                f"| {granule.scene_name} | {granule.date} | {granule.track} | "
                f"{granule.frame} | {granule.direction} | {granule.pole} | "
                f"{crid} | {provisional} | {present} |"
            )
    lines.append("")
    if context.stack is not None:
        lines.extend(["## Stack", "", context.stack.reason, ""])
        if context.stack.key is None:
            lines.append("No HH/HV stack was selected.")
        else:
            track, frame, direction = context.stack.key
            lines.append(
                f"Selected track {track}, frame {frame}, direction {direction}, "
                f"{len(context.stack.granules)} granules."
            )
        if context.stack.excluded:
            lines.extend(["", "Not used:", ""])
            for name, reason in context.stack.excluded:
                lines.append(f"- `{name}`: {reason}")
        lines.append("")
    if context.read_failures:
        lines.extend(
            [
                "## Read failures",
                "",
                "These granules stayed missing. They were not filled.",
                "",
            ]
        )
        for name, reason in context.read_failures:
            lines.append(f"- `{name}`: {reason}")
        lines.append("")
    if context.gcov_units:
        lines.extend(["## GCOV units attribute", ""])
        for name, units in context.gcov_units:
            lines.append(f"- `{name}`: {units}")
        lines.append("")
    lines.extend(
        [
            "## Grid and HAND",
            "",
            context.grid_text,
            "",
            f"HAND: {context.hand_source}",
            "",
        ]
    )
    if analysis is None:
        lines.extend(_readme_rows(True))
        lines.extend(_notes(context))
        return "\n".join(lines).rstrip() + "\n"

    thr = analysis.thresholds
    lines.extend(
        [
            "## Thresholds (read from config, uncalibrated)",
            "",
            (
                f"- Open water: HH γ0 < {thr.open_water_abs_hh_db:g} dB "
                f"and HAND < {thr.hand_max_m:g} m"
            ),
            f"- Class 1 (open-water change): ΔHH < {thr.class1_delta_hh_db_max:g} dB",
            "- Class 2 (flooded vegetation): "
            f"ΔHH > {thr.class2_delta_hh_db_min:g} dB and "
            f"|Δ(HV/HH)| < {thr.class2_delta_hv_hh_db_abs_max:g} dB",
            "- No baseline when f_wet = 0 (ratio undefined) or "
            f"(f_wet − f_dry) / f_wet < {thr.no_baseline_relative_gap:g}",
            (
                f"- Sensitivity step: ±{thr.db_step:g} dB; "
                f"HAND values {list(thr.hand_sensitivity_m)} m"
            ),
            "- Uncalibrated keys: "
            + (", ".join(thr.uncalibrated) if thr.uncalibrated else "not listed"),
            "- HV/HH in dB is HV_dB − HH_dB. Δ is the date minus the reference date.",
            "- Pixel area is one analysis-grid cell. "
            f"Hectares = pixel count × {analysis.pixel_area_m2:g} m² / 10000.",
            "",
            "## Open-water fraction by date",
            "",
            "f is the share of valid pixels (finite HH γ0 and finite HAND below the gate) "
            "whose HH γ0 is below the absolute threshold. "
            "The driest date is the minimum f. Ties take the earliest date.",
            "",
            "| Date | Granules | n_water | n_valid | f | Water extent |",
            "|---|---|---:|---:|---|---|",
        ]
    )
    for result in analysis.dates:
        fraction = "undefined" if result.n_valid == 0 else f"{result.n_water}/{result.n_valid}"
        if result.n_valid == 0:
            extent = "missing (denominator 0)"
        else:
            extent = (
                f"{_fmt_ha(result.n_water, analysis.pixel_area_m2)}"
                f"denominator {result.n_valid} valid pixels *(measured)*"
            )
        lines.append(
            f"| {result.date} | {', '.join(result.granule_ids)} | {result.n_water} | "
            f"{result.n_valid} | {fraction} | {extent} |"
        )
    lines.extend(["", "## Baseline", ""])
    lines.extend(_baseline_lines(analysis))
    lines.extend(["", "## Classes", ""])
    if not analysis.baseline.accepted:
        lines.extend(
            [
                "Class 2 = null.",
                "No change class was computed. "
                "The water figures above are absolute water extent on each date, "
                "with no change attribution.",
                "",
            ]
        )
    else:
        lines.append(
            f"Reference date (driest): {analysis.baseline.reference_date}. "
            "Change classes are relative to that date and are gated by HAND."
        )
        lines.append("")
        lines.append(
            "| Date | Class 1 pixels | Class 1 denominator | Class 1 ha | "
            "Class 2 pixels | Class 2 denominator | Class 2 ha |"
        )
        lines.append("|---|---:|---:|---|---:|---:|---|")
        for result in analysis.dates:
            if result.class_raster is None:
                continue
            class1_ha = _class_ha(result.n_class1, result.n_valid_class1, analysis.pixel_area_m2)
            class2_ha = _class_ha(result.n_class2, result.n_valid_class2, analysis.pixel_area_m2)
            lines.append(
                f"| {result.date} | {result.n_class1} | {result.n_valid_class1} | "
                f"{class1_ha} | {result.n_class2} | {result.n_valid_class2} | {class2_ha} |"
            )
        lines.append("")
    lines.extend(_sensitivity_lines(analysis))
    lines.extend(_chirps_lines(context))
    lines.extend(_s1_lines(context, analysis))
    lines.extend(_readme_rows(context.blocked is not None))
    lines.extend(_notes(context))
    return "\n".join(lines).rstrip() + "\n"


def _class_ha(n_class: int | None, n_valid: int | None, pixel_area_m2: float) -> str:
    if n_class is None or n_valid is None:
        return "null"
    if n_valid == 0:
        return "not measurable (denominator 0)"
    return (
        f"{hectares(n_class, pixel_area_m2):.2f} ha, "
        f"denominator {n_valid} valid pixels *(measured)*"
    )


def _baseline_lines(analysis: Analysis) -> list[str]:
    decision = analysis.baseline
    lines = [
        f"- Rule result: {decision.reason}",
        f"- f_wet = {decision.f_wet if decision.f_wet is not None else 'undefined'} "
        f"on {', '.join(decision.wet_dates) if decision.wet_dates else 'no date'}",
        f"- f_dry = {decision.f_dry if decision.f_dry is not None else 'undefined'} "
        f"on {', '.join(decision.dry_dates) if decision.dry_dates else 'no date'}",
    ]
    if decision.reason == "f_wet_zero":
        lines.append(
            "- (f_wet − f_dry) / f_wet is undefined because f_wet = 0. "
            "No detectable open water in the window. No dry baseline was selected."
        )
    elif decision.gap is None:
        lines.append("- The relative gap was not computed.")
    else:
        relation = "below" if not decision.accepted else "not below"
        lines.append(
            f"- (f_wet − f_dry) / f_wet = {decision.gap} "
            f"({decision.gap_float:.6f} as a float). "
            f"The limit is {decision.gap_limit:g}. The gap is {relation} the limit."
        )
    if decision.accepted:
        lines.append(
            f"- Reference date: {decision.reference_date} (earliest date tied for the minimum f)."
        )
    else:
        lines.append("- Reference date: none. Class 2 = null.")
    return lines


def _sensitivity_lines(analysis: Analysis) -> list[str]:
    lines = [
        "## Sensitivity",
        "",
        "Each row changes one configured dB threshold by ± the configured step, "
        "or sets HAND to one of the configured values, and leaves the other cuts at nominal. "
        "`minus` subtracts the step from the configured number; `plus` adds it.",
        "",
    ]
    focus = headline_date(analysis)
    for result in analysis.dates:
        lines.append(f"### {result.date}")
        lines.append("")
        lines.append(
            "Absolute water range: "
            + _range_text(result.sensitivity, "n_water", analysis.pixel_area_m2)
        )
        if result.n_class1 is None:
            lines.append("Class 1 change range: null (no baseline, or this is the reference date).")
            lines.append("Class 2 range: null.")
        else:
            lines.append(
                "Class 1 range: "
                + _range_text(result.sensitivity, "n_class1", analysis.pixel_area_m2)
            )
            lines.append(
                "Class 2 range: "
                + _range_text(result.sensitivity, "n_class2", analysis.pixel_area_m2)
            )
        if result.date == focus or (focus is None):
            lines.extend(
                [
                    "",
                    "| Scenario | n_water | n_valid water | n_class1 | "
                    "n_valid class1 | n_class2 | n_valid class2 |",
                    "|---|---:|---:|---:|---:|---:|---:|",
                ]
            )
            for row in result.sensitivity:
                lines.append(
                    f"| {row.name} | {row.n_water} | {row.n_valid_water} | "
                    f"{_cell(row.n_class1)} | {_cell(row.n_valid_class1)} | "
                    f"{_cell(row.n_class2)} | {_cell(row.n_valid_class2)} |"
                )
        lines.append("")
    return lines


def _cell(value: int | None) -> str:
    return "null" if value is None else str(value)


def _chirps_lines(context: ReportContext) -> list[str]:
    lines = [
        "## CHIRPS 15-day precipitation",
        "",
        "Mean of the daily CHIRPS sum over the AOI at 5 km, "
        f"for the {CHIRPS_DAYS} days ending on the acquisition date. "
        "This is context. It does not choose the reference date.",
        "",
    ]
    if not context.chirps_mm:
        lines.append("CHIRPS was not computed (missing).")
        lines.append("")
        return lines
    for date in sorted(context.chirps_mm):
        value = context.chirps_mm[date]
        if value is None:
            lines.append(f"- {date}: missing")
        else:
            lines.append(
                f"- {date}: {value:.3f} mm *(measured)*, "
                "GEE `UCSB-CHG/CHIRPS/DAILY`, mean of the 15-day sum, scale 5000 m"
            )
    lines.append("")
    return lines


def _s1_lines(context: ReportContext, analysis: Analysis) -> list[str]:
    thr = analysis.thresholds.open_water_abs_hh_db
    lines = [
        "## Sentinel-1 comparison",
        "",
        "Sentinel-1 IW GRD VV and VH are median composites in dB "
        f"(collection `COPERNICUS/S1_GRD`) within ±{S1_HALF_WINDOW_DAYS} days of the NISAR date, "
        "nearest-neighbor sampled onto the analysis grid "
        "(one median pixel per cell, not an area fraction). "
        f"The water mask uses the same uncalibrated cut as L-band HH: VV < {thr:g} dB. "
        "That cut is not an S1 calibration. "
        "A positive pixel is missed when its S1 VV is finite and is not below the cut. "
        "Pixels with missing S1 stay missing and are not counted as misses.",
        "",
    ]
    if not analysis.baseline.accepted:
        lines.append(
            "Class 2 = null, so the Class 2 miss is null. "
            "The comparison below is absolute NISAR water extent against the S1 mask."
        )
        lines.append("")
    if not context.s1:
        lines.append("Sentinel-1 was not computed (missing).")
        lines.append("")
        return lines
    for item in context.s1:
        lines.append(f"### {item.date} — {item.kind}")
        lines.append("")
        lines.append(f"- S1 scenes in the window: {item.s1_scene_count}")
        lines.append(
            f"- Positive pixels: {item.n_positive}; "
            f"with finite S1 VV: {item.n_positive_with_s1}; "
            f"S1 missing: {item.n_positive_s1_missing}"
        )
        if item.n_positive_with_s1 == 0:
            lines.append("- Misses: not measurable (denominator 0)")
        else:
            lines.append(
                f"- Missed by the S1 mask: {item.n_missed} pixels, "
                f"denominator {item.n_positive_with_s1} positive pixels with finite S1 VV "
                f"*(measured)*"
            )
        lines.append(
            f"- S1 water pixels inside the HAND domain: {item.n_s1_water}, "
            f"of which {item.n_s1_water_not_positive} are not in this positive class; "
            f"domain denominator {item.n_domain}"
        )
        lines.append(f"- Median S1 VV on positive pixels: {_db(item.median_vv_positive)}")
        lines.append(f"- Median S1 VH on positive pixels: {_db(item.median_vh_positive)}")
        lines.append(f"- Median S1 VV on the HAND domain: {_db(item.median_vv_domain)}")
        lines.append("")
    return lines


def _db(value: float | None) -> str:
    if value is None:
        return "missing"
    return f"{value:.3f} dB *(measured)*"


def _notes(context: ReportContext) -> list[str]:
    lines = ["## Notes", ""]
    if context.notes:
        lines.extend(f"- {note}" for note in context.notes)
    else:
        lines.append("- None.")
    lines.append("")
    return lines


def _readme_rows(blocked: bool) -> list[str]:
    """One README status row. The orchestrator copies it; this branch does not edit README.md."""
    state = "not cached" if blocked else "live"
    return [
        "## README rows",
        "",
        "Status row for the README table (component, state, issue, report).",
        "",
        "| Component | State | Issue | Report |",
        "|---|---|---|---|",
        f"| La Mojana dual-pol flood classes | {state} | #34 | reports/mojana.md |",
        "",
    ]


def safe_error(exc: BaseException) -> str:
    """Short error text with secrets and request URLs removed."""
    text = f"{type(exc).__name__}: {exc}"
    text = re.sub(r"https?://\S+", "<url>", text)
    for key, value in os.environ.items():
        if not value or len(value) < 8:
            continue
        if key.endswith(("_TOKEN", "_PASSWORD", "_KEY", "_SECRET", "_CREDENTIALS")):
            text = text.replace(value, "<redacted>")
    return text[:500]


def search_gcov(
    bbox: tuple[float, float, float, float],
    start: str,
    end: str,
) -> list[GranuleRef]:
    import asf_search as asf

    west, south, east, north = bbox
    wkt = (
        f"POLYGON(({west} {south}, {east} {south}, {east} {north}, {west} {north}, {west} {south}))"
    )
    # end is inclusive: ASF `end` is an instant, so use the end of that UTC day.
    results = asf.geo_search(
        platform=asf.PLATFORM.NISAR,
        processingLevel=["GCOV"],
        intersectsWith=wkt,
        start=f"{start}T00:00:00Z",
        end=f"{end}T23:59:59Z",
        maxResults=500,
    )
    granules: list[GranuleRef] = []
    for result in results:
        granule = granule_from_properties(dict(result.properties))
        if granule is not None and start <= granule.date <= end:
            granules.append(granule)
    return granules


def _attr_scalar(attrs, name: str):
    if name not in attrs:
        return None
    value = attrs[name]
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, np.ndarray):
        if value.shape == ():
            value = value.item()
        else:
            return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _crs_from_projection(value) -> str:
    if isinstance(value, np.ndarray):
        value = value.item() if value.shape == () else value.reshape(-1)[0]
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    if isinstance(value, int | np.integer):
        return f"EPSG:{int(value)}"
    text = str(value).strip()
    if text.isdigit():
        return f"EPSG:{text}"
    return text


def _clean_stored(values: np.ndarray, attrs) -> tuple[np.ndarray, str]:
    """Apply fill, valid range and scale. Returns linear power, or dB converted to linear."""
    out = np.asarray(values, dtype=np.float64)
    units = str(_attr_scalar(attrs, "units") or "units attribute missing; assumed linear power")
    fill = _attr_scalar(attrs, "_FillValue")
    valid_min = _attr_scalar(attrs, "valid_min")
    valid_max = _attr_scalar(attrs, "valid_max")
    mask = ~np.isfinite(out)
    if isinstance(fill, int | float | np.floating | np.integer):
        mask = mask | (out == float(fill))
    if isinstance(valid_min, int | float | np.floating | np.integer):
        mask = mask | (out < float(valid_min))
    if isinstance(valid_max, int | float | np.floating | np.integer):
        mask = mask | (out > float(valid_max))
    cleaned = out.copy()
    cleaned[mask] = np.nan
    scale = _attr_scalar(attrs, "scale_factor")
    offset = _attr_scalar(attrs, "add_offset")
    if isinstance(scale, int | float | np.floating | np.integer):
        cleaned = np.where(np.isfinite(cleaned), cleaned * float(scale), np.nan)
    if isinstance(offset, int | float | np.floating | np.integer):
        cleaned = np.where(np.isfinite(cleaned), cleaned + float(offset), np.nan)
    if "db" in units.lower():
        cleaned = db_to_power(cleaned)
        units = f"{units} (converted from dB to linear power before averaging)"
    return cleaned, units


def _monotonic_window(coords: np.ndarray, low: float, high: float) -> slice | None:
    diffs = np.diff(coords)
    if coords.size < 2 or not (np.all(diffs > 0) or np.all(diffs < 0)):
        raise ValueError("coordinate axis is not strictly monotonic")
    inside = np.nonzero((coords >= low) & (coords <= high))[0]
    if inside.size == 0:
        return None
    start = max(0, int(inside[0]) - 1)
    stop = min(int(coords.size), int(inside[-1]) + 2)
    return slice(start, stop)


def invalid_gcov_pixels(
    shape: tuple[int, ...],
    looks: np.ndarray | None,
    mask: np.ndarray | None,
    exception: np.ndarray | None,
) -> tuple[np.ndarray, str]:
    """Pixels the GCOV product itself marks unusable.

    From the ``mask`` description stored on the granule: 0 means a sample
    built from a partially focused or invalid radar sample, and 255 is outside
    the acquisition. ``inputDataExceptionMask`` is 0 when there is no anomaly.
    ``numberOfLooks <= 0`` has no average. These are product flags, not flood
    thresholds.
    """
    invalid = np.zeros(shape, dtype=bool)
    notes: list[str] = []
    if looks is not None:
        looks = np.asarray(looks)
        if looks.shape != shape:
            raise ValueError(f"numberOfLooks shape {looks.shape} != power shape {shape}")
        invalid |= ~np.isfinite(looks) | (looks <= 0)
        notes.append("numberOfLooks <= 0 set to missing")
    if mask is not None:
        mask = np.asarray(mask)
        if mask.shape != shape:
            raise ValueError(f"mask shape {mask.shape} != power shape {shape}")
        invalid |= (mask == 0) | (mask == 255)
        notes.append("mask values 0 and 255 set to missing")
    if exception is not None:
        exception = np.asarray(exception)
        if exception.shape != shape:
            raise ValueError(
                f"inputDataExceptionMask shape {exception.shape} != power shape {shape}"
            )
        invalid |= exception != 0
        notes.append("nonzero inputDataExceptionMask set to missing")
    return invalid, "; ".join(notes)


def analysis_stride(spacing_m: float, cell_m: float = ANALYSIS_CELL_M) -> int:
    """Source-pixel step whose spacing is nearest the analysis cell.

    Half-up, not banker's round: 20 m spacing and a 90 m cell is stride 5
    (100 m), not 4 (80 m).
    """
    if not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError(f"source spacing must be positive, got {spacing_m}")
    return max(1, int(math.floor(cell_m / spacing_m + 0.5)))


def few_dates_block(n_dates: int) -> str | None:
    """Block classification when 3 or fewer dates survived the reads."""
    if n_dates >= MIN_USABLE_DATES:
        return None
    return (
        f"BLOCKED: {n_dates} usable date(s) after granule reads "
        "(need more than 3). Missing granules were not filled. "
        "Classes were not computed."
    )


def _axis_spacing_m(coords: np.ndarray) -> float:
    if coords.size < 2:
        raise ValueError("coordinate axis has fewer than 2 samples")
    spacing = float(np.median(np.abs(np.diff(np.asarray(coords, dtype=np.float64)))))
    if not math.isfinite(spacing) or spacing <= 0:
        raise ValueError(f"source spacing must be positive, got {spacing}")
    return spacing


class ByteCountFile:
    """Count bytes h5py pulls through an fsspec file. No network of its own."""

    def __init__(self, raw) -> None:
        self._raw = raw
        self.bytes_read = 0
        self._closed = False

    def read(self, size: int = -1):
        data = self._raw.read(-1 if size is None else size)
        if data:
            self.bytes_read += len(data)
        return data

    def seek(self, offset: int, whence: int = os.SEEK_SET):
        return self._raw.seek(offset, whence)

    def tell(self) -> int:
        return int(self._raw.tell())

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        close = getattr(self._raw, "close", None)
        if close is not None:
            close()

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        self.close()
        return False

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False


def new_granule_filesystem():
    """One authenticated HTTPS filesystem. Not the cached earthaccess session.

    ``get_fsspec_https_session`` is memoized and has no read timeout. A stalled
    socket on that shared client is what hung the previous run.
    """
    import aiohttp
    import earthaccess
    import fsspec

    auth = earthaccess.login(strategy="environment", persist=False)
    if not getattr(auth, "authenticated", False):
        auth = earthaccess.login(strategy="netrc", persist=False)
    if not getattr(auth, "authenticated", False):
        raise RuntimeError("Earthdata login failed")
    token = auth.token["access_token"]
    return fsspec.filesystem(
        "https",
        client_kwargs={
            "headers": {"Authorization": f"Bearer {token}"},
            "trust_env": False,
            "timeout": aiohttp.ClientTimeout(sock_connect=SOCK_CONNECT_S, sock_read=SOCK_READ_S),
        },
    )


def open_granule_file(filesystem, url: str) -> ByteCountFile:
    """Block-cached open. 32 MB blocks, nearest-style strided reads happen later."""
    raw = filesystem.open(
        url,
        "rb",
        cache_type="blockcache",
        block_size=FSSPEC_BLOCK_SIZE,
    )
    return ByteCountFile(raw)


def _read_layer(group, name: str, y_idx: slice, x_idx: slice, handle: ByteCountFile, t0: float):
    print(f"  reading {name}", flush=True)
    values = np.asarray(group[name][y_idx, x_idx])
    elapsed = time.perf_counter() - t0
    print(f"  {name}: {handle.bytes_read} bytes in {elapsed:.1f}s", flush=True)
    return values


def _read_granule_once(
    granule: GranuleRef,
    bbox: tuple[float, float, float, float],
    grid: AnalysisGrid,
    session_factory,
) -> GranuleRead:
    """One attempt. The caller opens a new session and applies retries."""
    import h5py
    from rasterio.warp import transform_bounds

    if not granule.url:
        raise RuntimeError("granule has no HTTPS url")
    t0 = time.perf_counter()
    handle: ByteCountFile | None = None
    try:
        filesystem = session_factory()
        handle = open_granule_file(filesystem, granule.url)
        with h5py.File(handle, "r") as h5:
            if FREQ_A not in h5:
                raise RuntimeError(f"{FREQ_A} is not in the file; keys={list(h5.keys())}")
            group = h5[FREQ_A]
            if "HHHH" not in group or "HVHV" not in group:
                raise RuntimeError(
                    f"HHHH and HVHV are required; frequencyA keys={sorted(group.keys())}"
                )
            projection = group["projection"][()]
            src_crs = _crs_from_projection(projection)
            x_all = np.asarray(group["xCoordinates"][()]).reshape(-1)
            y_all = np.asarray(group["yCoordinates"][()]).reshape(-1)
            left, bottom, right, top = transform_bounds(
                "EPSG:4326", src_crs, bbox[0], bbox[1], bbox[2], bbox[3], densify_pts=21
            )
            x_slice = _monotonic_window(x_all, min(left, right), max(left, right))
            y_slice = _monotonic_window(y_all, min(bottom, top), max(bottom, top))
            if x_slice is None or y_slice is None:
                raise RuntimeError("granule grid does not intersect the AOI")
            spacing_x = _axis_spacing_m(x_all)
            spacing_y = _axis_spacing_m(y_all)
            stride_x = analysis_stride(spacing_x, grid.cell_m)
            stride_y = analysis_stride(spacing_y, grid.cell_m)
            y_idx = slice(y_slice.start, y_slice.stop, stride_y)
            x_idx = slice(x_slice.start, x_slice.stop, stride_x)
            print(
                f"  stride {stride_y} by {stride_x} source pixels "
                f"({spacing_y:.1f} m by {spacing_x:.1f} m; "
                f"analysis cell {grid.cell_m:g} m)",
                flush=True,
            )
            hh_raw = _read_layer(group, "HHHH", y_idx, x_idx, handle, t0)
            hh, units = _clean_stored(hh_raw, group["HHHH"].attrs)
            del hh_raw
            hv_raw = _read_layer(group, "HVHV", y_idx, x_idx, handle, t0)
            hv, hv_units = _clean_stored(hv_raw, group["HVHV"].attrs)
            del hv_raw
            looks = (
                _read_layer(group, "numberOfLooks", y_idx, x_idx, handle, t0)
                if "numberOfLooks" in group
                else None
            )
            mask = _read_layer(group, "mask", y_idx, x_idx, handle, t0) if "mask" in group else None
            exception = (
                _read_layer(group, "inputDataExceptionMask", y_idx, x_idx, handle, t0)
                if "inputDataExceptionMask" in group
                else None
            )
            invalid, validity_note = invalid_gcov_pixels(hh.shape, looks, mask, exception)
            del looks, mask, exception
            hh[invalid] = np.nan
            hv[invalid] = np.nan
            del invalid
            x_win = x_all[x_idx]
            y_win = y_all[y_idx]
        hh_grid = resample_power_mean(hh, x_win, y_win, src_crs, grid)
        hv_grid = resample_power_mean(hv, x_win, y_win, src_crs, grid)
        seconds = time.perf_counter() - t0
        print(
            f"  {granule.scene_name}: {handle.bytes_read} bytes in {seconds:.1f}s",
            flush=True,
        )
        return GranuleRead(
            hh=hh_grid,
            hv=hv_grid,
            units=(
                f"HHHH {units}; HVHV {hv_units}; crs {src_crs}; {validity_note}; "
                f"read stride {stride_y} by {stride_x} source pixels "
                f"(spacing {spacing_y:.1f} m by {spacing_x:.1f} m; "
                f"analysis cell {grid.cell_m:g} m)"
            ),
            bytes_read=handle.bytes_read,
            seconds=seconds,
            stride_row=stride_y,
            stride_col=stride_x,
            spacing_y_m=spacing_y,
            spacing_x_m=spacing_x,
        )
    except Exception:
        nbytes = 0 if handle is None else handle.bytes_read
        elapsed = time.perf_counter() - t0
        print(f"  {granule.scene_name}: {nbytes} bytes in {elapsed:.1f}s", flush=True)
        raise
    finally:
        if handle is not None:
            handle.close()


def read_granule_power(
    granule: GranuleRef,
    bbox: tuple[float, float, float, float],
    grid: AnalysisGrid,
    *,
    session_factory=None,
    sleeper=None,
    attempts: int = GRANULE_ATTEMPTS,
) -> GranuleRead:
    """Read one granule. A new filesystem each attempt, then two retries.

    A granule that still fails raises. The caller records it as missing.
    ``session_factory`` and ``sleeper`` exist so tests can pass a fake
    filesystem and skip the backoff sleep. They are not flood thresholds.
    """
    factory = new_granule_filesystem if session_factory is None else session_factory
    pause = time.sleep if sleeper is None else sleeper
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            return _read_granule_once(granule, bbox, grid, factory)
        except Exception as exc:
            last = exc
            if attempt >= attempts - 1:
                break
            delay = GRANULE_BACKOFF_S[min(attempt, len(GRANULE_BACKOFF_S) - 1)]
            print(
                f"  retry {attempt + 1} in {delay:.0f}s after {safe_error(exc)}",
                flush=True,
            )
            pause(delay)
    assert last is not None
    raise last


def run_bounded_process(argv: list[str], timeout_s: float) -> int | None:
    """Run argv. Return the exit code, or None if it had to be killed.

    The child is its own process group so a stalled reader and its HTTP
    client die together. None means the granule is missing.
    """
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(argv, start_new_session=True, env=env)
    try:
        return proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        try:
            if hasattr(os, "killpg"):  # POSIX: kill the whole group (reader + HTTP client)
                os.killpg(proc.pid, signal.SIGKILL)
            else:  # Windows has no process groups via os.killpg
                proc.kill()
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        return None


def read_granule_bounded(
    granule: GranuleRef,
    bbox: tuple[float, float, float, float],
    *,
    limit_s: float = GRANULE_LIMIT_S,
) -> GranuleRead | str:
    """Subprocess read. A stall becomes an error string, not a hung parent."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="mojana-granule-") as tmp:
        tmp_path = Path(tmp)
        out = tmp_path / "power.npz"
        meta_path = tmp_path / "meta.json"
        job = tmp_path / "job.json"
        job.write_text(
            json.dumps(
                {
                    "granule": {
                        "scene_name": granule.scene_name,
                        "date": granule.date,
                        "track": granule.track,
                        "frame": granule.frame,
                        "direction": granule.direction,
                        "pole": granule.pole,
                        "primary_pol": granule.primary_pol,
                        "url": granule.url,
                        "provisional": granule.provisional,
                        "crid": granule.crid,
                    },
                    "bbox": list(bbox),
                    "out": str(out),
                    "meta": str(meta_path),
                }
            ),
            encoding="utf-8",
        )
        code = run_bounded_process(
            [sys.executable, "-m", "gee_math.flood_polarimetric_math", "--worker-job", str(job)],
            limit_s,
        )
        if code is None:
            return f"exceeded {limit_s:.0f}s with no finished read; missing"
        if not meta_path.is_file():
            return f"reader exited {code} without a result; missing"
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        if not payload.get("ok"):
            return str(payload.get("error") or "missing")
        if code != 0 or not out.is_file():
            return str(payload.get("error") or f"reader exited {code}; missing")
        with np.load(out) as data:
            hh = np.array(data["hh"])
            hv = np.array(data["hv"])
        return GranuleRead(
            hh=hh,
            hv=hv,
            units=str(payload["units"]),
            bytes_read=int(payload["bytes"]),
            seconds=float(payload["seconds"]),
            stride_row=int(payload["stride_row"]),
            stride_col=int(payload["stride_col"]),
            spacing_y_m=float(payload["spacing_y_m"]),
            spacing_x_m=float(payload["spacing_x_m"]),
        )


def worker_entry(job_path: Path) -> int:
    """Child process: one granule, then exit. The parent enforces the time limit."""
    job = json.loads(job_path.read_text(encoding="utf-8"))
    fields = job["granule"]
    granule = GranuleRef(
        scene_name=str(fields["scene_name"]),
        date=str(fields["date"]),
        track=int(fields["track"]),
        frame=int(fields["frame"]),
        direction=str(fields["direction"]),
        pole=str(fields["pole"]),
        primary_pol=str(fields["primary_pol"]),
        url=str(fields["url"]),
        provisional=bool(fields["provisional"]),
        crid=str(fields["crid"]),
    )
    bbox = tuple(float(value) for value in job["bbox"])
    meta_path = Path(job["meta"])
    try:
        result = read_granule_power(granule, bbox, build_grid(bbox))
        np.savez(job["out"], hh=result.hh, hv=result.hv)
        payload = {
            "ok": True,
            "units": result.units,
            "bytes": result.bytes_read,
            "seconds": result.seconds,
            "stride_row": result.stride_row,
            "stride_col": result.stride_col,
            "spacing_y_m": result.spacing_y_m,
            "spacing_x_m": result.spacing_x_m,
        }
        code = 0
    except Exception as exc:
        payload = {"ok": False, "error": safe_error(exc)}
        code = 1
    meta_path.write_text(json.dumps(payload), encoding="utf-8")
    return code


def _npy_bands(raw: bytes) -> dict[str, np.ndarray]:
    structured = np.load(io.BytesIO(raw))
    if getattr(structured.dtype, "names", None):
        return {name: np.asarray(structured[name]) for name in structured.dtype.names}
    return {"band": np.asarray(structured)}


def sample_ee_image(image, grid: AnalysisGrid) -> dict[str, np.ndarray]:
    """Pull an image onto the analysis grid. Masked pixels stay non-finite. No unmask(0)."""
    import ee

    transform = grid.affine()
    params = {
        "expression": image,
        "fileFormat": "NPY",
        "grid": {
            "dimensions": {"width": grid.width, "height": grid.height},
            "affineTransform": {
                "scaleX": transform.a,
                "shearX": transform.b,
                "translateX": transform.c,
                "shearY": transform.d,
                "scaleY": transform.e,
                "translateY": transform.f,
            },
            "crsCode": grid.crs,
        },
    }
    raw = ee.data.computePixels(params)
    bands = _npy_bands(raw)
    cleaned = {}
    for name, values in bands.items():
        out = np.asarray(values, dtype=np.float64)
        # Earth Engine's NPY mask uses a separate field when present; a non-finite
        # value is already missing. Do not replace missing with 0.
        out[~np.isfinite(out)] = np.nan
        cleaned[name] = out
    return cleaned


def _pick_band(bands: dict[str, np.ndarray], prefer: str) -> np.ndarray:
    for name, values in bands.items():
        if prefer.lower() in name.lower():
            return values
    if len(bands) == 1:
        return next(iter(bands.values()))
    raise RuntimeError(f"computePixels fields {sorted(bands)} do not include {prefer}")


def fetch_hand(grid: AnalysisGrid) -> np.ndarray:
    import ee

    from gee_math.ee_session import init_ee

    init_ee()
    # computePixels samples with nearest neighbor unless resample() requested
    # bilinear or bicubic. "nearest" is not a legal resample() mode.
    image = ee.Image("MERIT/Hydro/v1_0_1").select("hnd")
    bands = sample_ee_image(image, grid)
    return _pick_band(bands, "hnd")


def fetch_chirps_15d_mm(bbox: tuple[float, float, float, float], date: str) -> float | None:
    import ee

    day = datetime.strptime(date, "%Y-%m-%d").date()
    start = (day - timedelta(days=CHIRPS_DAYS - 1)).isoformat()
    end = (day + timedelta(days=1)).isoformat()
    collection = (
        ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate(start, end).select("precipitation")
    )
    count = int(collection.size().getInfo())
    if count == 0:
        return None
    image = collection.sum()
    region = ee.Geometry.Rectangle([bbox[0], bbox[1], bbox[2], bbox[3]])
    value = (
        image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=5000,
            maxPixels=1_000_000_000,
        )
        .get("precipitation")
        .getInfo()
    )
    if value is None:
        return None
    return float(value)


def s1_iw_collection(bbox: tuple[float, float, float, float], date: str):
    """IW GRD scenes with VV and VH inside the ±N day window. N is ``S1_HALF_WINDOW_DAYS``."""
    import ee

    start, end = s1_window_bounds(date)
    region = ee.Geometry.Rectangle([bbox[0], bbox[1], bbox[2], bbox[3]])
    return (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
    )


def fetch_s1(
    grid: AnalysisGrid,
    bbox: tuple[float, float, float, float],
    date: str,
) -> tuple[np.ndarray, np.ndarray, int] | None:
    """Median S1 VV and VH in dB. Returns None when the window has no IW scene."""
    collection = s1_iw_collection(bbox, date)
    count = int(collection.size().getInfo())
    if count == 0:
        return None
    vv, vh = fetch_s1_median_bands(collection, grid)
    return vv, vh, count


def fetch_s1_median_bands(collection, grid: AnalysisGrid) -> tuple[np.ndarray, np.ndarray]:
    """Median VV and VH in dB on the analysis grid. Missing samples stay NaN."""
    median = collection.select(["VV", "VH"]).median()
    bands = sample_ee_image(median, grid)
    return _pick_band(bands, "VV"), _pick_band(bands, "VH")


def list_s1_scenes(collection) -> tuple[S1Scene, ...]:
    """Scene id, pass and date bounds. Raises if the list is shorter than the collection."""
    import ee

    def pack(image):
        img = ee.Image(image)
        return ee.Dictionary(
            {
                "scene_id": img.id(),
                "orbit_pass": img.get("orbitProperties_pass"),
                "time_start": img.get("system:time_start"),
                "time_end": img.get("system:time_end"),
                "relative_orbit": img.get("relativeOrbitNumber_start"),
            }
        )

    payload = ee.Dictionary(
        {
            "count": collection.size(),
            "rows": ee.List(collection.toList(collection.size()).map(pack)),
        }
    ).getInfo()
    count = int(payload["count"])
    rows = payload.get("rows") or []
    if len(rows) != count:
        raise RuntimeError(f"S1 scene list length {len(rows)} != collection size {count}")
    scenes = tuple(
        sorted(
            (scene_from_ee_row(row) for row in rows),
            key=lambda scene: (scene.start, scene.scene_id),
        )
    )
    return scenes


def _call_with_alarm(fn, timeout_s: float):
    """Run ``fn`` on the main thread. A stall becomes ``TimeoutError``."""

    def handler(signum, frame):
        raise TimeoutError(f"timed out after {timeout_s:.0f}s")

    previous = signal.signal(signal.SIGALRM, handler)
    signal.alarm(int(timeout_s))
    try:
        return fn()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def inspect_water_mask(array: np.ndarray) -> tuple[int, int, int]:
    """Return (value==1, value>=0, values other than -1/0/1)."""
    values = np.asarray(array)
    n_water = int(np.count_nonzero(values == 1))
    n_valid = int(np.count_nonzero(values >= 0))
    n_other = int(np.count_nonzero((values != -1) & (values != 0) & (values != 1)))
    return n_water, n_valid, n_other


def read_water_mask(path: Path) -> tuple[AnalysisGrid, np.ndarray]:
    """Read a cached water raster. The file is opened read-only."""
    import rasterio

    with rasterio.open(path) as src:
        array = src.read(1)
        transform = src.transform
        crs = src.crs.to_string() if src.crs is not None else ""
        grid = AnalysisGrid(
            crs=crs,
            transform=(
                transform.a,
                transform.b,
                transform.c,
                transform.d,
                transform.e,
                transform.f,
            ),
            width=int(src.width),
            height=int(src.height),
            cell_m=abs(float(transform.a)),
        )
    return grid, array


def load_provenance_dates(path: Path) -> tuple[str, str, tuple[ProvenanceDate, ...]]:
    """Read open-water counts. The file is opened read-only."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    generated = str(payload.get("generated_utc") or "missing")
    config_sha = str(payload.get("config_sha256") or "missing")
    rows: list[ProvenanceDate] = []
    for item in payload["dates"]:
        rows.append(
            ProvenanceDate(
                date=str(item["date"]),
                granule_ids=tuple(str(value) for value in item["granule_ids"]),
                n_water=int(item["n_water"]),
                n_valid=int(item["n_valid"]),
            )
        )
    return generated, config_sha, tuple(rows)


def _refuse_protected_write(path: Path) -> None:
    name = path.name
    if name == "provenance.json" or name.endswith((".tif", ".zarr")) or "sar_cube" in name:
        raise RuntimeError(f"refusing to write {name}")


@dataclass
class _LvscJob:
    provenance: ProvenanceDate
    grid: AnalysisGrid
    water: np.ndarray


def _prepare_lvsc_dates(
    cache_dir: Path,
    dates: tuple[ProvenanceDate, ...],
) -> tuple[list[LvscDateResult | _LvscJob], str]:
    """Check each cached mask against provenance. Mismatches never become a fraction."""
    prepared: list[LvscDateResult | _LvscJob] = []
    grid_text = "missing"
    reference: AnalysisGrid | None = None
    for item in dates:
        raster_path = cache_dir / f"water_extent_{item.date}.tif"
        if not raster_path.is_file():
            prepared.append(
                _blank_lvsc(
                    item.date,
                    item.granule_ids,
                    item.n_water,
                    item.n_valid,
                    "missing",
                    f"cached water mask missing: {raster_path.name}",
                )
            )
            continue
        grid, array = read_water_mask(raster_path)
        if reference is None:
            reference = grid
            grid_text = (
                f"{grid.crs} grid, {grid.cell_m:g} m cells, "
                f"{grid.width} columns by {grid.height} rows"
            )
        elif (
            grid.crs != reference.crs
            or grid.transform != reference.transform
            or grid.width != reference.width
            or grid.height != reference.height
        ):
            prepared.append(
                _blank_lvsc(
                    item.date,
                    item.granule_ids,
                    item.n_water,
                    item.n_valid,
                    "missing",
                    "water mask grid does not match the other dates",
                )
            )
            continue
        n_water, n_valid, n_other = inspect_water_mask(array)
        if n_other:
            prepared.append(
                _blank_lvsc(
                    item.date,
                    item.granule_ids,
                    item.n_water,
                    item.n_valid,
                    "missing",
                    f"water mask has {n_other} values other than -1, 0, 1",
                )
            )
            continue
        if n_water != item.n_water or n_valid != item.n_valid:
            prepared.append(
                _blank_lvsc(
                    item.date,
                    item.granule_ids,
                    item.n_water,
                    item.n_valid,
                    "missing",
                    (
                        f"water mask count {n_water}/{n_valid} != provenance "
                        f"{item.n_water}/{item.n_valid}"
                    ),
                )
            )
            continue
        if item.n_water == 0:
            prepared.append(
                lvsc_result_for_date(
                    item.date,
                    item.granule_ids,
                    0,
                    item.n_valid,
                    (),
                    None,
                )
            )
            continue
        prepared.append(_LvscJob(provenance=item, grid=grid, water=array))
    return prepared, grid_text


def _fetch_lvsc_job(
    job: _LvscJob,
    bbox: tuple[float, float, float, float],
    threshold_db: float,
) -> LvscDateResult:
    date = job.provenance.date
    print(
        f"lvsc {date}: Sentinel-1 IW GRD within ±{S1_HALF_WINDOW_DAYS} days",
        flush=True,
    )

    def work():
        collection = s1_iw_collection(bbox, date)
        scenes = list_s1_scenes(collection)
        if not scenes:
            return scenes, None
        print(f"lvsc {date}: {len(scenes)} scenes, median VV/VH", flush=True)
        return scenes, fetch_s1_median_bands(collection, job.grid)

    last_error: BaseException | None = None
    for attempt in (1, 2):
        try:
            scenes, bands = _call_with_alarm(work, S1_DATE_LIMIT_S)
            break
        except TimeoutError as exc:
            print(f"lvsc {date}: {safe_error(exc)}", flush=True)
            return lvsc_result_for_date(
                date,
                job.provenance.granule_ids,
                job.provenance.n_water,
                job.provenance.n_valid,
                (),
                None,
                error=safe_error(exc),
            )
        except Exception as exc:
            last_error = exc
            print(f"lvsc {date}: attempt {attempt} failed: {safe_error(exc)}", flush=True)
            if attempt == 1:
                time.sleep(GRANULE_BACKOFF_S[0])
                continue
            return lvsc_result_for_date(
                date,
                job.provenance.granule_ids,
                job.provenance.n_water,
                job.provenance.n_valid,
                (),
                None,
                error=safe_error(exc),
            )
    else:
        return lvsc_result_for_date(
            date,
            job.provenance.granule_ids,
            job.provenance.n_water,
            job.provenance.n_valid,
            (),
            None,
            error=safe_error(last_error or RuntimeError("S1 fetch failed")),
        )

    if not scenes:
        print(f"lvsc {date}: no S1 within window", flush=True)
        return lvsc_result_for_date(
            date,
            job.provenance.granule_ids,
            job.provenance.n_water,
            job.provenance.n_valid,
            (),
            None,
        )
    if bands is None:
        return lvsc_result_for_date(
            date,
            job.provenance.granule_ids,
            job.provenance.n_water,
            job.provenance.n_valid,
            scenes,
            None,
            error="S1 median was not returned",
        )
    vv, vh = bands
    if vv.shape != job.water.shape or vh.shape != job.water.shape:
        return lvsc_result_for_date(
            date,
            job.provenance.granule_ids,
            job.provenance.n_water,
            job.provenance.n_valid,
            scenes,
            None,
            error=(f"S1 grid shape VV {vv.shape} VH {vh.shape} != water mask {job.water.shape}"),
        )
    comparison = compare_s1(
        job.water == 1,
        job.water >= 0,
        vv,
        vh,
        threshold_db,
        date,
        "absolute_water",
        len(scenes),
    )
    result = lvsc_result_for_date(
        date,
        job.provenance.granule_ids,
        job.provenance.n_water,
        job.provenance.n_valid,
        scenes,
        comparison,
    )
    print(
        f"lvsc {date}: status {result.status} fraction {result.miss_fraction_text}",
        flush=True,
    )
    return result


def _july_prior_note(results: list[LvscDateResult]) -> str | None:
    """Cite the published 2026-07-11 row. This run's row is computed separately."""
    july = next((item for item in results if item.date == "2026-07-11"), None)
    if july is None or july.status != "measured":
        return None
    prior = (
        "`reports/mojana.md` recorded 3351 Sentinel-1 misses out of 4946 NISAR "
        "open-water pixels on 2026-07-11, from 14 IW GRD scenes in this same window "
        "*(measured, that report)*."
    )
    if july.n_missed == 3351 and july.n_with_s1 == 4946 and len(july.scenes) == 14:
        return prior + " This command reproduces that row."
    return (
        prior
        + f" This command measured {july.miss_fraction_text} "
        + f"with {len(july.scenes)} scenes on that date."
    )


def _write_lvsc_outputs(
    report_path: Path,
    json_path: Path,
    text: str,
    payload: dict,
) -> None:
    _refuse_protected_write(report_path)
    _refuse_protected_write(json_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(text, encoding="utf-8")


def _lvsc_json_row(item: LvscDateResult) -> dict:
    return {
        "date": item.date,
        "status": item.status,
        "detail": item.detail,
        "nisar_granule_ids": list(item.nisar_granule_ids),
        "n_open_water": item.n_open_water,
        "n_valid": item.n_valid,
        "n_with_s1": item.n_with_s1,
        "n_s1_missing_on_water": item.n_s1_missing_on_water,
        "n_s1_also_water": item.n_s1_also_water,
        "n_missed": item.n_missed,
        "miss_fraction": item.miss_fraction_text,
        "median_vv_open_water_db": item.median_vv_open_water_db,
        "scenes": [
            {
                "scene_id": scene.scene_id,
                "orbit_pass": scene.orbit_pass,
                "start": scene.start,
                "end": scene.end,
                "relative_orbit": scene.relative_orbit,
            }
            for scene in item.scenes
        ],
    }


def run_lvsc(
    *,
    thresholds: FloodThresholds,
    bbox: tuple[float, float, float, float],
    bbox_source: str,
    config_path: Path,
    cache_dir: Path,
    report_path: Path,
    json_path: Path,
    command: str,
    root: Path,
) -> int:
    """Compare cached NISAR open water with Sentinel-1 on every provenance date.

    Reads ``provenance.json`` and ``water_extent_*.tif``. Does not write them,
    and does not open the cube.
    """
    provenance_path = cache_dir / "provenance.json"
    if not provenance_path.is_file():
        print(f"missing provenance: {provenance_path}", file=sys.stderr)
        return 1
    generated_provenance, provenance_sha, dates = load_provenance_dates(provenance_path)
    prepared, grid_text = _prepare_lvsc_dates(cache_dir, dates)
    needs_s1 = any(isinstance(item, _LvscJob) for item in prepared)
    ee_error: str | None = None
    if needs_s1:
        try:
            from gee_math.ee_session import init_ee

            init_ee()
        except Exception as exc:
            ee_error = safe_error(exc)
            print(f"lvsc Earth Engine init failed: {ee_error}", file=sys.stderr)
    results: list[LvscDateResult] = []
    for item in prepared:
        if isinstance(item, LvscDateResult):
            results.append(item)
            continue
        if ee_error:
            results.append(
                lvsc_result_for_date(
                    item.provenance.date,
                    item.provenance.granule_ids,
                    item.provenance.n_water,
                    item.provenance.n_valid,
                    (),
                    None,
                    error=ee_error,
                )
            )
            continue
        results.append(_fetch_lvsc_job(item, bbox, thresholds.open_water_abs_hh_db))
    generated = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    config_rel = (
        str(config_path.relative_to(root)) if config_path.is_relative_to(root) else str(config_path)
    )
    prior_note = _july_prior_note(results)
    text = render_lvsc_report(
        results,
        command=command,
        generated_utc=generated,
        config_path=config_rel,
        config_sha256=file_sha256(config_path),
        threshold_db=thresholds.open_water_abs_hh_db,
        bbox=bbox,
        bbox_source=bbox_source,
        provenance_generated_utc=generated_provenance,
        provenance_config_sha256=provenance_sha,
        grid_text=grid_text,
        prior_note=prior_note,
    )
    summary = summarize_miss_fractions(results)
    payload = {
        "command": command,
        "generated_utc": generated,
        "config_path": config_rel,
        "config_sha256": file_sha256(config_path),
        "threshold_db": thresholds.open_water_abs_hh_db,
        "half_window_days": S1_HALF_WINDOW_DAYS,
        "collection": "COPERNICUS/S1_GRD",
        "bbox": list(bbox),
        "bbox_source": bbox_source,
        "provenance_generated_utc": generated_provenance,
        "provenance_config_sha256": provenance_sha,
        "grid": grid_text,
        "dates": [_lvsc_json_row(item) for item in results],
        "summary": None
        if summary is None
        else {
            "n_dates": summary.n_dates,
            "median": f"{summary.median.numerator}/{summary.median.denominator}",
            "median_text": summary.median_text,
            "minimum": summary.minimum_text,
            "maximum": summary.maximum_text,
            "sorted": summary.sorted_text,
            "even_count_averaged": summary.even_count_averaged,
        },
    }
    _write_lvsc_outputs(report_path, json_path, text, payload)
    print(f"wrote {report_path}", flush=True)
    print(f"wrote {json_path}", flush=True)
    if any(item.status == "missing" for item in results):
        return 1
    return 0


def login_earthdata() -> None:
    import earthaccess

    auth = earthaccess.login(strategy="environment", persist=False)
    if not getattr(auth, "authenticated", False):
        auth = earthaccess.login(strategy="netrc", persist=False)
    if not getattr(auth, "authenticated", False):
        raise RuntimeError("Earthdata login failed")


def _s1_comparisons(
    analysis: Analysis,
    s1_by_date: dict[str, tuple[np.ndarray, np.ndarray, int] | None],
) -> tuple[S1Comparison, ...]:
    threshold = analysis.thresholds.open_water_abs_hh_db
    comparisons: list[S1Comparison] = []
    focus = headline_date(analysis)
    dates = [focus] if focus else [item.date for item in analysis.dates]
    for date in dates:
        if date is None:
            continue
        result = next(item for item in analysis.dates if item.date == date)
        fetched = s1_by_date.get(date)
        if fetched is None:
            continue
        vv, vh, count = fetched
        domain = result.water_raster >= 0
        if analysis.baseline.accepted and result.class_raster is not None:
            comparisons.append(
                compare_s1(
                    result.class_raster == 2,
                    domain,
                    vv,
                    vh,
                    threshold,
                    date,
                    "class2",
                    count,
                )
            )
            comparisons.append(
                compare_s1(
                    result.class_raster == 1,
                    domain,
                    vv,
                    vh,
                    threshold,
                    date,
                    "class1",
                    count,
                )
            )
        comparisons.append(
            compare_s1(
                result.water_raster == 1,
                domain,
                vv,
                vh,
                threshold,
                date,
                "absolute_water",
                count,
            )
        )
    return tuple(comparisons)


def _write_provenance(path: Path, analysis: Analysis, context: ReportContext) -> None:
    payload = {
        "command": context.command,
        "generated_utc": context.generated_utc,
        "config_sha256": context.config_sha256,
        "bbox": list(context.bbox),
        "baseline": {
            "accepted": analysis.baseline.accepted,
            "reason": analysis.baseline.reason,
            "reference_date": analysis.baseline.reference_date,
            "f_wet": analysis.baseline.f_wet,
            "f_dry": analysis.baseline.f_dry,
            "gap": analysis.baseline.gap,
        },
        "dates": [
            {
                "date": item.date,
                "granule_ids": list(item.granule_ids),
                "n_water": item.n_water,
                "n_valid": item.n_valid,
                "n_class1": item.n_class1,
                "n_valid_class1": item.n_valid_class1,
                "n_class2": item.n_class2,
                "n_valid_class2": item.n_valid_class2,
            }
            for item in analysis.dates
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="La Mojana dual-pol flood classes from NISAR GCOV")
    parser.add_argument("--config", default="config/preregistered.yaml")
    parser.add_argument("--ops-config", default="config/bailasar.yaml")
    parser.add_argument("--start", default="2026-06-17")
    parser.add_argument("--end", default="2026-11-14")
    parser.add_argument("--cache-dir", default="local_cache/mojana")
    parser.add_argument("--report", default="reports/mojana.md")
    parser.add_argument(
        "--lvsc",
        action="store_true",
        help=(
            "Compare cached NISAR open water with Sentinel-1 on every date. "
            "Does not write provenance.json or cube bands."
        ),
    )
    parser.add_argument("--lvsc-report", default="reports/mojana_lvsc.md")
    parser.add_argument(
        "--lvsc-json",
        default="local_cache/mojana/lvsc_comparison.json",
    )
    parser.add_argument("--worker-job", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    load_env()
    if args.worker_job:
        return worker_entry(Path(args.worker_job))
    root = repo_root()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    ops_path = Path(args.ops_config)
    if not ops_path.is_absolute():
        ops_path = root / ops_path
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = root / report_path
    cache_dir = Path(args.cache_dir)
    if not cache_dir.is_absolute():
        cache_dir = root / cache_dir

    thresholds = load_flood_thresholds(config_path)
    bbox, bbox_source = resolve_bbox(ops_path)
    command = "uv run python -m gee_math.flood_polarimetric_math " + " ".join(argv or sys.argv[1:])
    if args.lvsc:
        lvsc_report = Path(args.lvsc_report)
        if not lvsc_report.is_absolute():
            lvsc_report = root / lvsc_report
        lvsc_json = Path(args.lvsc_json)
        if not lvsc_json.is_absolute():
            lvsc_json = root / lvsc_json
        return run_lvsc(
            thresholds=thresholds,
            bbox=bbox,
            bbox_source=bbox_source,
            config_path=config_path,
            cache_dir=cache_dir,
            report_path=lvsc_report,
            json_path=lvsc_json,
            command=command.strip(),
            root=root,
        )
    generated = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    grid = build_grid(bbox)
    base_context = dict(
        command=command.strip(),
        generated_utc=generated,
        bbox=bbox,
        bbox_source=bbox_source,
        window=(args.start, args.end),
        config_path=(
            str(config_path.relative_to(root))
            if config_path.is_relative_to(root)
            else str(config_path)
        ),
        config_sha256=file_sha256(config_path),
        granules=(),
        stack=None,
        grid_text=(
            f"{grid.crs} grid, {grid.cell_m:g} m cells, "
            f"{grid.width} columns by {grid.height} rows, "
            f"pixel area {grid.pixel_area_m2:g} m². "
            "GCOV linear power is averaged into the cell that contains each source-pixel center. "
            "A cell with no finite source sample stays missing."
        ),
        hand_source="not fetched",
        gcov_units=(),
        chirps_mm={},
        s1=(),
        read_failures=(),
        notes=(
            "Overlap of same-day granules is the mean of linear power.",
            "Class rasters use -1 for missing. They are not zero-filled.",
            "Product flags, not flood thresholds: mask values 0 and 255, "
            "a nonzero inputDataExceptionMask, and numberOfLooks <= 0 stay missing.",
        ),
        blocked=None,
        search_count=0,
    )

    def emit(context: ReportContext, analysis: Analysis | None) -> None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_report(analysis, context), encoding="utf-8")

    try:
        login_earthdata()
        granules = search_gcov(bbox, args.start, args.end)
    except Exception as exc:
        context = ReportContext(
            **{
                **base_context,
                "blocked": f"ASF search or Earthdata login failed. {safe_error(exc)}",
            }
        )
        emit(context, None)
        print(context.blocked, file=sys.stderr)
        return 1

    stack = select_stack(granules)
    print(f"search count {len(granules)}; {stack.reason}", flush=True)
    try:
        hand = fetch_hand(grid)
    except Exception as exc:
        context = ReportContext(
            **{
                **base_context,
                "granules": tuple(granules),
                "stack": stack,
                "search_count": len(granules),
                "blocked": f"MERIT Hydro HAND fetch failed. {safe_error(exc)}",
                "hand_source": "missing",
            }
        )
        emit(context, None)
        print(context.blocked, file=sys.stderr)
        return 1

    finite_hand = int(np.count_nonzero(np.isfinite(hand)))
    hand_source = (
        "GEE MERIT/Hydro/v1_0_1 band hnd, nearest-neighbor sample onto the analysis grid "
        f"via ee.data.computePixels (no unmask). Finite HAND pixels: {finite_hand} "
        f"of {hand.size} *(measured)*."
    )
    if finite_hand == 0:
        context = ReportContext(
            **{
                **base_context,
                "granules": tuple(granules),
                "stack": stack,
                "search_count": len(granules),
                "hand_source": hand_source,
                "blocked": "HAND array has no finite pixels. Classes were not computed.",
            }
        )
        emit(context, None)
        print(context.blocked, file=sys.stderr)
        return 1

    cubes_by_date: dict[str, list[tuple[str, np.ndarray, np.ndarray]]] = defaultdict(list)
    units: list[tuple[str, str]] = []
    failures: list[tuple[str, str]] = []
    stride_lines: list[str] = []
    for granule in stack.granules:
        print(f"reading {granule.scene_name}", flush=True)
        outcome = read_granule_bounded(granule, bbox)
        if isinstance(outcome, str):
            failures.append((granule.scene_name, outcome))
            print(f"  missing: {outcome}", flush=True)
            continue
        if outcome.hh.shape != (grid.height, grid.width):
            failures.append(
                (
                    granule.scene_name,
                    f"grid shape {outcome.hh.shape} != {(grid.height, grid.width)}; missing",
                )
            )
            print(f"  missing: grid shape {outcome.hh.shape}", flush=True)
            continue
        finite = int(np.count_nonzero(np.isfinite(outcome.hh)))
        stride_lines.append(
            f"{granule.scene_name}: stride {outcome.stride_row} by {outcome.stride_col} "
            f"source pixels ({outcome.spacing_y_m:.1f} m by {outcome.spacing_x_m:.1f} m)"
        )
        if finite == 0:
            failures.append((granule.scene_name, "no finite HH pixels after resample"))
            print("  missing: no finite HH pixels after resample", flush=True)
            continue
        units.append((granule.scene_name, outcome.units))
        cubes_by_date[granule.date].append((granule.scene_name, outcome.hh, outcome.hv))
        print(
            f"  {outcome.bytes_read} bytes in {outcome.seconds:.1f}s; finite HH pixels {finite}",
            flush=True,
        )

    dates: list[DateCube] = []
    for date in sorted(cubes_by_date):
        items = cubes_by_date[date]
        dates.append(
            DateCube(
                date=date,
                granule_ids=tuple(name for name, _hh, _hv in items),
                hh_linear=mosaic_linear([hh for _name, hh, _hv in items]),
                hv_linear=mosaic_linear([hv for _name, _hh, hv in items]),
            )
        )
    notes = list(base_context["notes"])
    if stride_lines:
        notes.append(
            "GCOV first pass is a strided read at the analysis grid, "
            "not the full native window. " + " ".join(stride_lines)
        )
    else:
        notes.append("GCOV stride was not measured (no granule opened far enough).")
    block = few_dates_block(len(dates))
    if block is not None:
        context = ReportContext(
            **{
                **base_context,
                "granules": tuple(granules),
                "stack": stack,
                "search_count": len(granules),
                "hand_source": hand_source,
                "gcov_units": tuple(units),
                "read_failures": tuple(failures),
                "notes": tuple(notes),
                "blocked": block,
            }
        )
        emit(context, None)
        print(block, file=sys.stderr)
        return 1

    analysis = classify_stack(dates, hand, thresholds, grid.pixel_area_m2)

    chirps: dict[str, float | None] = {}
    s1_by_date: dict[str, tuple[np.ndarray, np.ndarray, int] | None] = {}
    selected_dates = sorted({granule.date for granule in stack.granules})
    for earlier, later in zip(selected_dates, selected_dates[1:], strict=False):
        span_days = (
            datetime.strptime(later, "%Y-%m-%d") - datetime.strptime(earlier, "%Y-%m-%d")
        ).days
        if span_days > 13:
            notes.append(
                f"Selected stack: {span_days} days between {earlier} and {later} "
                "(no granule on the 12-day repeat in between)."
            )
    focus_dates = []
    if analysis.baseline.reference_date:
        focus_dates.append(analysis.baseline.reference_date)
    headline = headline_date(analysis)
    if headline and headline not in focus_dates:
        focus_dates.append(headline)
    if not focus_dates:
        focus_dates = [item.date for item in analysis.dates]
    for date in focus_dates:
        try:
            chirps[date] = fetch_chirps_15d_mm(bbox, date)
        except Exception as exc:
            chirps[date] = None
            notes.append(f"CHIRPS {date} missing: {safe_error(exc)}")
        try:
            s1_by_date[date] = fetch_s1(grid, bbox, date)
            if s1_by_date[date] is None:
                notes.append(
                    f"Sentinel-1 {date}: no IW VV/VH scene in the ±{S1_HALF_WINDOW_DAYS} day window"
                )
        except Exception as exc:
            s1_by_date[date] = None
            notes.append(f"Sentinel-1 {date} missing: {safe_error(exc)}")

    context = ReportContext(
        **{
            **base_context,
            "granules": tuple(granules),
            "stack": stack,
            "search_count": len(granules),
            "hand_source": hand_source,
            "gcov_units": tuple(units),
            "chirps_mm": chirps,
            "s1": _s1_comparisons(analysis, s1_by_date),
            "read_failures": tuple(failures),
            "notes": tuple(notes),
        }
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    written = write_rasters(analysis, grid, cache_dir)
    _write_provenance(cache_dir / "provenance.json", analysis, context)
    emit(context, analysis)
    print(f"wrote {report_path}", flush=True)
    print(f"rasters {len(written)}", flush=True)
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
