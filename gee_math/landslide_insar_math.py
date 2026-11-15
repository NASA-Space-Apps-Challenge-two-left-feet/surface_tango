"""Aburrá landslide InSAR: ionosphere, stratified troposphere, LOS, downslope, noise floor.

Pure functions take numpy arrays and are covered by known-answer tests. The CLI reads
real NISAR GUNW granules and FABDEM and writes ``local_cache/aburra/`` plus
``reports/aburra.md``. ``compute_landslide_insar_kinematics`` stays so the GEE caller
in ``mcp_servers/gee_fusion_mcp.py`` keeps its entrypoint.
"""

from __future__ import annotations

import math
import re
import warnings
from dataclasses import dataclass
from pathlib import Path

import ee
import numpy as np

# Design doc Hazard 1 and this branch's brief fix the conversion wavelength.
# The GUNW product stores centerFrequency (D-102272 §5.3); the CLI records that
# value and still converts with this wavelength.
WAVELENGTH_M = 0.24
# Analysis definition of "valley floor" for the troposphere fit. Read from
# config/preregistered.yaml key landslide.valley_floor_max_slope_deg when that
# block exists. It is not a detection threshold; the detection test is the
# residual RMS.
VALLEY_FLOOR_MAX_SLOPE_DEG = 5.0
# Pixels whose downslope direction is this close to perpendicular to the LOS
# are left missing. Dividing by a smaller cosine would amplify the noise.
MIN_ABS_COS_XI = 0.2
# Mean Gregorian year, used only to express a pair displacement as mm/yr.
DAYS_PER_YEAR = 365.25
# D-102272 §5.3: connectedComponents _FillValue.
COMPONENT_FILL = 65535
# ISCE/NISAR connected components use 0 for "not in a component".
COMPONENT_NONE = 0
SPEED_OF_LIGHT_M_S = 299_792_458.0
# config/bailasar.yaml aois key. The bbox itself is read from that file.
ABURRA_AOI_PREFIX = "1_aburra"
# Same name grammar as scripts/discover_nisar_colombia.py NAME_RE.
GRANULE_NAME_RE = re.compile(
    r"NISAR_L2_(?P<stream>[A-Z]{2})_(?P<product>[A-Z]{4})_.*?_(?P<pol>[A-Z]{2,4})_(?:[A-Z]_)?"
    r"(?P<t1>\d{8})T\d{6}_\d{8}T\d{6}(?:_(?P<t2>\d{8})T\d{6}_\d{8}T\d{6})?"
)


def format_mm(value: float) -> str:
    """Format millimetres for the verdict sentence."""
    return f"{value:.3f}".rstrip("0").rstrip(".")


def null_motion_sentence(noise_floor_mm: float, n_pairs: int) -> str:
    """Exact failure sentence required by the brief.

    ``n_pairs`` is the number of pairs that produced a finite residual RMS.
    """
    if noise_floor_mm is None or not math.isfinite(noise_floor_mm):
        shown = "missing"
    else:
        shown = format_mm(noise_floor_mm)
    return f"no motion detected above {shown} mm ({n_pairs} pairs)"


def subtract_ionosphere(unwrapped_rad: np.ndarray, ionosphere_rad: np.ndarray) -> np.ndarray:
    """Subtract the provided ionosphere screen. A missing input stays NaN.

    D-102272 and the ASF GUNW guide: the ionosphere phase screen is included
    and is not applied to the phase layers. Both layers are in radians, so
    applying the screen is this subtraction (design doc Hazard 1).
    """
    unw = np.asarray(unwrapped_rad, dtype=np.float64)
    iono = np.asarray(ionosphere_rad, dtype=np.float64)
    return unw - iono


def los_displacement_mm(phase_rad: np.ndarray, wavelength_m: float = WAVELENGTH_M) -> np.ndarray:
    """Line-of-sight displacement in millimetres, d_LOS = −λ Δφ / 4π.

    Positive d_LOS is motion toward the sensor, along the product LOS unit
    vector (target → sensor).

    Checked against the product spec: JPL D-102272 Rev E (8 Nov 2024) §5.3
    defines ``unwrappedPhase`` in radians and does not state the sign.
    §4.4.3 and §5.6 define ``losUnitVectorX/Y`` as the east/north components
    of the unit vector from the target to the sensor, with the up component
    the positive square root of ``1 - east² - north²``. ISCE's carrier phase
    is φ = −4π r/λ, and the interferogram φ_reference − φ_secondary is
    positive when the secondary range is larger (motion away from the
    sensor): isce-framework/isce2 discussion 523, Staniewicz, 2022-07-28.
    The leading minus sign converts that phase into toward-sensor
    displacement. λ is 0.24 m as fixed by the brief and Hazard 1.
    """
    phase = np.asarray(phase_rad, dtype=np.float64)
    return -float(wavelength_m) * phase / (4.0 * math.pi) * 1000.0


def fit_los_elevation(
    los_mm: np.ndarray, elevation_m: np.ndarray, stable: np.ndarray
) -> tuple[float, float, float, int]:
    """OLS ``los_mm = offset + scale * elevation`` on stable pixels.

    Returns ``(offset_mm, scale_mm_per_m, residual_rms_mm, n_stable)``.
    Fewer than two finite stable pixels returns NaN coefficients and NaN RMS.
    The residual RMS is the pair noise floor, in millimetres of LOS.
    """
    los = np.asarray(los_mm, dtype=np.float64)
    elev = np.asarray(elevation_m, dtype=np.float64)
    mask = np.asarray(stable, dtype=bool) & np.isfinite(los) & np.isfinite(elev)
    n_stable = int(np.count_nonzero(mask))
    if n_stable < 2:
        return (math.nan, math.nan, math.nan, n_stable)
    z = elev[mask]
    y = los[mask]
    design = np.column_stack((np.ones(n_stable), z))
    coef, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    offset = float(coef[0])
    scale = float(coef[1])
    residual = y - (offset + scale * z)
    rms = float(np.sqrt(np.mean(residual**2)))
    return (offset, scale, rms, n_stable)


def remove_stratified_troposphere(
    los_mm: np.ndarray, elevation_m: np.ndarray, offset_mm: float, scale_mm_per_m: float
) -> np.ndarray:
    """Subtract the elevation line. A failed fit, or a missing input, stays NaN."""
    los = np.asarray(los_mm, dtype=np.float64)
    elev = np.asarray(elevation_m, dtype=np.float64)
    if not math.isfinite(offset_mm) or not math.isfinite(scale_mm_per_m):
        return np.full(los.shape, np.nan, dtype=np.float64)
    corrected = los - (offset_mm + scale_mm_per_m * elev)
    corrected[~np.isfinite(los) | ~np.isfinite(elev)] = np.nan
    return corrected


def reference_component_id(components: np.ndarray) -> int | None:
    """Largest valid connected component.

    D-102272 §5.3 sets the fill value to 65535 and describes the layer as
    "Connected components" without naming a reference id. Component 0 is the
    ISCE "not unwrapped together" label. The reference component kept here is
    the remaining label with the most pixels. Ties go to the smaller label
    because ``np.unique`` returns sorted values and ``argmax`` returns the
    first maximum.
    """
    raw = np.asarray(components)
    finite = np.isfinite(raw) if np.issubdtype(raw.dtype, np.floating) else np.ones(raw.shape, bool)
    labels = np.zeros(raw.shape, dtype=np.int64)
    labels[finite] = raw[finite].astype(np.int64)
    valid = finite & (labels != COMPONENT_NONE) & (labels != COMPONENT_FILL)
    if not np.any(valid):
        return None
    values, counts = np.unique(labels[valid], return_counts=True)
    return int(values[int(np.argmax(counts))])


def mask_to_reference_component(
    values: np.ndarray, components: np.ndarray
) -> tuple[np.ndarray, int | None]:
    """Set every pixel outside the reference component to NaN."""
    out = np.array(values, dtype=np.float64, copy=True)
    ref = reference_component_id(components)
    if ref is None:
        out[:] = np.nan
        return out, None
    labels = np.asarray(components)
    out[labels != ref] = np.nan
    return out, ref


def range_slope_deg(
    slope_deg: np.ndarray, aspect_deg: np.ndarray, look_azimuth_deg: float
) -> np.ndarray:
    """Terrain slope in the ground-range direction, in degrees.

    Positive when downhill points along the look (increasing range): a
    backslope. Negative when the slope faces the radar: a foreslope.
    ``aspect_deg`` is the downhill azimuth, degrees clockwise from north,
    which is the FABDEM / ``ee.Terrain.aspect`` convention.
    """
    slope = np.radians(np.asarray(slope_deg, dtype=np.float64))
    delta = np.radians(np.asarray(aspect_deg, dtype=np.float64) - float(look_azimuth_deg))
    return np.degrees(np.arctan(np.tan(slope) * np.cos(delta)))


def layover_or_shadow(
    slope_deg: np.ndarray,
    aspect_deg: np.ndarray,
    incidence_deg: float,
    look_azimuth_deg: float,
) -> np.ndarray:
    """True on layover (foreshortened past the incidence angle) or shadow.

    Non-finite slope or incidence is False here; the caller treats a missing
    slope as missing data rather than as a geometric mask hit.
    """
    if not math.isfinite(incidence_deg) or not math.isfinite(look_azimuth_deg):
        return np.zeros(np.shape(slope_deg), dtype=bool)
    alpha = range_slope_deg(slope_deg, aspect_deg, look_azimuth_deg)
    incidence = float(incidence_deg)
    finite = np.isfinite(alpha)
    layover = finite & (alpha < -incidence)
    shadow = finite & (alpha > (90.0 - incidence))
    return layover | shadow


def look_azimuth_deg(los_east: float, los_north: float) -> float:
    """Azimuth, clockwise from north, of increasing ground range.

    The product LOS vector points from the target toward the sensor, so
    increasing range is the opposite horizontal direction.
    """
    if math.hypot(los_east, los_north) < 1e-6:
        return math.nan
    return math.degrees(math.atan2(-los_east, -los_north)) % 360.0


def los_up_from_horizontal(los_east: float, los_north: float) -> float:
    """Positive up component of a unit LOS vector (D-102272 §4.4.3)."""
    remaining = 1.0 - los_east**2 - los_north**2
    if remaining < 0.0 and remaining > -1e-6:
        remaining = 0.0
    if remaining < 0.0:
        return math.nan
    return math.sqrt(remaining)


def downslope_displacement_mm(
    d_los_mm: np.ndarray,
    slope_deg: np.ndarray,
    aspect_deg: np.ndarray,
    los_east: float,
    los_north: float,
    los_up: float,
    min_abs_cos: float = MIN_ABS_COS_XI,
) -> np.ndarray:
    """Project LOS displacement onto the steepest downslope direction.

    Positive output is motion in the downhill direction. With positive
    ``d_los_mm`` toward the sensor,

        d_down = d_LOS / (u_down · u_LOS).

    Pixels with ``|u_down · u_LOS| < min_abs_cos`` stay NaN. The cosine is
    not clamped, and the sign is kept.
    """
    beta = np.radians(np.asarray(slope_deg, dtype=np.float64))
    psi = np.radians(np.asarray(aspect_deg, dtype=np.float64))
    slope_east = np.cos(beta) * np.sin(psi)
    slope_north = np.cos(beta) * np.cos(psi)
    slope_up = -np.sin(beta)
    los = np.array([los_east, los_north, los_up], dtype=np.float64)
    norm = float(np.linalg.norm(los))
    out = np.full(np.shape(d_los_mm), np.nan, dtype=np.float64)
    if not math.isfinite(norm) or norm == 0.0:
        return out
    los = los / norm
    cosine = slope_east * los[0] + slope_north * los[1] + slope_up * los[2]
    d_los = np.asarray(d_los_mm, dtype=np.float64)
    ok = np.isfinite(d_los) & np.isfinite(cosine) & (np.abs(cosine) >= min_abs_cos)
    out[ok] = d_los[ok] / cosine[ok]
    return out


def annual_rate_mm_per_yr(displacement_mm: np.ndarray, temporal_baseline_days: float) -> np.ndarray:
    """Scale a pair displacement to mm/yr. An unknown baseline stays NaN."""
    disp = np.asarray(displacement_mm, dtype=np.float64)
    if not math.isfinite(temporal_baseline_days) or temporal_baseline_days <= 0.0:
        return np.full(disp.shape, np.nan, dtype=np.float64)
    return disp * (DAYS_PER_YEAR / float(temporal_baseline_days))


def slice_bounds(coords: np.ndarray, low: float, high: float) -> tuple[int, int] | None:
    """Inclusive coordinate window as a slice ``[start, stop)``.

    ``coords`` must be monotonic. The slice covers every sample that falls
    inside ``[min(low, high), max(low, high)]``.
    """
    cmin = min(low, high)
    cmax = max(low, high)
    inside = np.flatnonzero((coords >= cmin) & (coords <= cmax))
    if inside.size == 0:
        return None
    return int(inside[0]), int(inside[-1]) + 1


@dataclass
class NoiseFloorResult:
    kept_rate_mm_per_yr: np.ndarray
    noise_floor_mm: float
    n_pairs: int
    n_pixels_kept: int
    n_pixels_positive: int
    n_pixels_negative: int
    verdict: str


def _independent(dates_a: frozenset[str], dates_b: frozenset[str]) -> bool:
    """Two pairs are independent when both dates are known and disjoint."""
    if not dates_a or not dates_b:
        return False
    return dates_a.isdisjoint(dates_b)


def check_noise_floor_rule(landslide_block: dict | None) -> str:
    """Verify the pre-registered keep-rule keys match the rule `noise_floor` implements.

    `config/preregistered.yaml` → `landslide.noise_floor` must say
    `min_pairs: 2` and `require_sign_agreement: true` (the design doc's rule).
    Any other value is a pre-registration the code does not implement, so it
    raises instead of silently running a different rule. Returns a short note
    for the report.
    """
    block = (
        (landslide_block or {}).get("noise_floor") if isinstance(landslide_block, dict) else None
    )
    if not isinstance(block, dict):
        raise ValueError("config/preregistered.yaml has no landslide.noise_floor block")
    min_pairs = block.get("min_pairs")
    agree = block.get("require_sign_agreement")
    if min_pairs != 2 or agree is not True:
        raise ValueError(
            "landslide.noise_floor is "
            f"{{min_pairs: {min_pairs}, require_sign_agreement: {agree}}}; "
            "noise_floor() implements min_pairs 2 with sign agreement only"
        )
    return "landslide.noise_floor {min_pairs: 2, require_sign_agreement: true} read and matched"


def noise_floor(
    los_mm: list[np.ndarray],
    downslope_mm: list[np.ndarray],
    rate_mm_per_yr: list[np.ndarray],
    residual_rms_mm: list[float],
    acquisition_dates: list[frozenset[str]],
) -> NoiseFloorResult:
    """Keep a downslope rate only when it beats the pair noise and the sign agrees.

    A pair contributes a detection where ``|LOS|`` exceeds that pair's
    stable-pixel residual RMS (same units, millimetres) and the downslope
    rate is finite. The pixel is kept when two such detections have the same
    downslope sign and the pairs do not share an acquisition date. Opposite
    signs with independent support cancel the pixel. The published noise
    floor is the median of the finite per-pair RMS values. Pairs must already
    sit on one grid; this function does not resample.
    """
    if len(los_mm) == 0:
        empty = np.zeros((0, 0), dtype=np.float64)
        return NoiseFloorResult(empty, math.nan, 0, 0, 0, 0, null_motion_sentence(math.nan, 0))
    los_arrays = [np.asarray(item, dtype=np.float64) for item in los_mm]
    shape = los_arrays[0].shape
    n_pairs_in = len(los_arrays)
    if not (
        len(downslope_mm) == n_pairs_in
        and len(rate_mm_per_yr) == n_pairs_in
        and len(residual_rms_mm) == n_pairs_in
        and len(acquisition_dates) == n_pairs_in
    ):
        raise ValueError("noise-floor inputs must be the same length")
    for los in los_arrays:
        if los.shape != shape:
            raise ValueError("pairs on different grids cannot share a noise-floor test")

    detect = np.zeros((n_pairs_in, *shape), dtype=np.int8)
    rates = np.full((n_pairs_in, *shape), np.nan, dtype=np.float64)
    finite_rms: list[float] = []
    for index, los in enumerate(los_arrays):
        down = np.asarray(downslope_mm[index], dtype=np.float64)
        rate = np.asarray(rate_mm_per_yr[index], dtype=np.float64)
        if down.shape != shape or rate.shape != shape:
            raise ValueError("pairs on different grids cannot share a noise-floor test")
        rms = float(residual_rms_mm[index])
        if not math.isfinite(rms):
            continue
        finite_rms.append(rms)
        hit = (
            np.isfinite(los)
            & np.isfinite(down)
            & np.isfinite(rate)
            & (np.abs(los) > rms)
            & (down != 0.0)
        )
        detect[index][hit] = np.where(down[hit] > 0.0, np.int8(1), np.int8(-1))
        rates[index][hit] = rate[hit]

    n_pairs = len(finite_rms)
    floor_mm = (
        float(np.median(np.asarray(finite_rms, dtype=np.float64))) if finite_rms else math.nan
    )
    positive = np.zeros(shape, dtype=bool)
    negative = np.zeros(shape, dtype=bool)
    use = np.zeros((n_pairs_in, *shape), dtype=bool)
    for i in range(n_pairs_in):
        for j in range(i + 1, n_pairs_in):
            if not _independent(acquisition_dates[i], acquisition_dates[j]):
                continue
            both_pos = (detect[i] == 1) & (detect[j] == 1)
            both_neg = (detect[i] == -1) & (detect[j] == -1)
            positive |= both_pos
            negative |= both_neg
            agreed = both_pos | both_neg
            use[i] |= agreed
            use[j] |= agreed

    conflict = positive & negative
    kept_pos = positive & ~conflict
    kept_neg = negative & ~conflict
    sign_map = np.zeros(shape, dtype=np.int8)
    sign_map[kept_pos] = 1
    sign_map[kept_neg] = -1
    out = np.full(shape, np.nan, dtype=np.float64)
    if np.any(sign_map != 0):
        selected = np.where(use & (detect == sign_map[np.newaxis, ...]), rates, np.nan)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            median = np.nanmedian(selected, axis=0)
        good = np.isfinite(median) & (sign_map != 0)
        out[good] = median[good]
        kept_pos &= good
        kept_neg &= good
    n_pos = int(np.count_nonzero(kept_pos))
    n_neg = int(np.count_nonzero(kept_neg))
    n_kept = n_pos + n_neg
    if n_kept == 0:
        verdict = null_motion_sentence(floor_mm, n_pairs)
    else:
        shown = format_mm(floor_mm) if math.isfinite(floor_mm) else "missing"
        verdict = (
            f"kept downslope rates on {n_kept} pixels; noise floor {shown} mm ({n_pairs} pairs)"
        )
    return NoiseFloorResult(out, floor_mm, n_pairs, n_kept, n_pos, n_neg, verdict)


def _kept_fraction(result: NoiseFloorResult, eligible: np.ndarray) -> float:
    n_eligible = int(np.count_nonzero(eligible))
    if n_eligible == 0:
        return math.nan
    kept = np.isfinite(result.kept_rate_mm_per_yr) & eligible
    return int(np.count_nonzero(kept)) / n_eligible


@dataclass(frozen=True)
class KeepRuleCalibration:
    """The keep-rule's observed kept fraction against its sign-flip null."""

    n_eligible: int
    observed_fraction: float
    null_mean: float
    null_p95: float
    draws: int
    seed: int
    exceeds_null: bool


def calibrate_keep_rule(
    los_mm: list[np.ndarray],
    downslope_mm: list[np.ndarray],
    rate_mm_per_yr: list[np.ndarray],
    residual_rms_mm: list[float],
    acquisition_dates: list[frozenset[str]],
    *,
    draws: int,
    seed: int,
) -> KeepRuleCalibration:
    """Compare the kept fraction with the same rule on sign-flipped pairs.

    Each draw multiplies every pair's downslope field (and rate) by one
    seeded ±1, which keeps each pair's noise and spatial structure but breaks
    any sign consistency real motion would have across pairs. Under pure noise
    the observed fraction sits inside the null; consistent motion puts it
    above the null's 95th percentile. Eligible pixels are those with a finite
    downslope value in at least one pair (the hillslope domain; valley-floor
    stable pixels are already excluded upstream). The flips reorder real
    measurements; no value is generated.
    """
    import random

    if draws < 1:
        raise ValueError("draws must be at least 1")
    downs = [np.asarray(d, dtype=np.float64) for d in downslope_mm]
    rates = [np.asarray(r, dtype=np.float64) for r in rate_mm_per_yr]
    eligible = np.zeros(downs[0].shape, dtype=bool) if downs else np.zeros((0, 0), dtype=bool)
    for down in downs:
        eligible |= np.isfinite(down)
    observed = _kept_fraction(
        noise_floor(los_mm, downs, rates, residual_rms_mm, acquisition_dates), eligible
    )
    rng = random.Random(seed)
    null = []
    for _ in range(draws):
        signs = [1.0 if rng.getrandbits(1) else -1.0 for _ in downs]
        flipped = noise_floor(
            los_mm,
            [d * s for d, s in zip(downs, signs, strict=True)],
            [r * s for r, s in zip(rates, signs, strict=True)],
            residual_rms_mm,
            acquisition_dates,
        )
        null.append(_kept_fraction(flipped, eligible))
    null_arr = np.asarray(null, dtype=np.float64)
    finite = null_arr[np.isfinite(null_arr)]
    null_mean = float(finite.mean()) if finite.size else math.nan
    null_p95 = float(np.quantile(finite, 0.95)) if finite.size else math.nan
    exceeds = bool(math.isfinite(observed) and math.isfinite(null_p95) and observed > null_p95)
    return KeepRuleCalibration(
        int(np.count_nonzero(eligible)), observed, null_mean, null_p95, draws, seed, exceeds
    )


@dataclass(frozen=True)
class StableFalsePositive:
    """Keep-rule false-positive rate on the stable valley-floor sample."""

    n_stable: int
    n_kept: int
    kept_fraction: float


def stable_pixel_false_positive(
    los_mm: list[np.ndarray],
    downslope_mm: list[np.ndarray],
    rate_mm_per_yr: list[np.ndarray],
    residual_rms_mm: list[float],
    acquisition_dates: list[frozenset[str]],
) -> StableFalsePositive:
    """Apply ``noise_floor`` to stable-pixel downslope fields.

    Each downslope and rate array is finite only on that pair's tropo sample
    (valley floor, inside the reference component, outside layover and shadow)
    and NaN elsewhere. The denominator is the number of pixels with a finite
    stable downslope in at least one pair. The numerator is how many of those
    the keep-rule retains. The inputs are measurements; nothing is generated.
    """
    downs = [np.asarray(item, dtype=np.float64) for item in downslope_mm]
    if not downs:
        return StableFalsePositive(0, 0, math.nan)
    eligible = np.zeros(downs[0].shape, dtype=bool)
    for down in downs:
        if down.shape != eligible.shape:
            raise ValueError("stable-pixel inputs must share one grid")
        eligible |= np.isfinite(down)
    result = noise_floor(los_mm, downs, rate_mm_per_yr, residual_rms_mm, acquisition_dates)
    kept = np.isfinite(result.kept_rate_mm_per_yr) & eligible
    return StableFalsePositive(
        int(np.count_nonzero(eligible)),
        int(np.count_nonzero(kept)),
        _kept_fraction(result, eligible),
    )


def exceeds_stable_rate(hillslope_fraction: float, stable_fraction: float) -> bool:
    """True when the hillslope kept fraction is above the stable-pixel rate.

    No extra margin is pre-registered. A missing fraction does not exceed.
    """
    return bool(
        math.isfinite(hillslope_fraction)
        and math.isfinite(stable_fraction)
        and hillslope_fraction > stable_fraction
    )


def _join_stacks(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _row_fraction(row: dict, key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return math.nan
    return float(value)


def stable_comparison_sentence(rows: list[dict]) -> str:
    """One line on the hillslope kept fraction against the stable-pixel rate.

    A higher hillslope fraction is a candidate only when it also exceeds the
    sign-flip 95th percentile. Below that null, the null holds. The wording
    does not call either case a detection.
    """
    if not rows:
        return "No stack produced a stable-pixel false-positive rate."
    missing = []
    above_stable = []
    above_both = []
    for row in rows:
        name = str(row.get("stack", "missing"))
        hill = _row_fraction(row, "observed_kept_fraction")
        stable = _row_fraction(row, "stable_kept_fraction")
        null_p95 = _row_fraction(row, "null_p95")
        if not math.isfinite(hill) or not math.isfinite(stable):
            missing.append(name)
            continue
        if hill > stable:
            above_stable.append(name)
            if math.isfinite(null_p95) and hill > null_p95:
                above_both.append(name)
    if above_both:
        return (
            "The hillslope kept fraction exceeds the stable-pixel false-positive "
            f"rate and the sign-flip null on {_join_stacks(above_both)}; "
            "candidate, PROVISIONAL."
        )
    if above_stable:
        return (
            "The hillslope kept fraction is above the stable-pixel false-positive "
            f"rate on {_join_stacks(above_stable)}, and below the sign-flip null, "
            "so the null holds."
        )
    if missing:
        return f"The stable-pixel false-positive rate is missing on {_join_stacks(missing)}."
    return (
        "The hillslope kept fraction is consistent with the stable-pixel "
        "false-positive rate, so the null holds."
    )


def calibration_headline(noise_floor_mm: float, n_pairs: int, rows: list[dict]) -> str:
    """Null sentence, unless a track exceeds both the stable-pixel rate and the sign-flip null.

    The candidate wording does not call that exceedance a detection.
    """
    sentence = stable_comparison_sentence(rows)
    if "candidate, PROVISIONAL" in sentence:
        floor = format_mm(noise_floor_mm) if math.isfinite(noise_floor_mm) else "missing"
        return f"{sentence} Noise floor {floor} mm ({n_pairs} pairs)."
    return null_motion_sentence(noise_floor_mm, n_pairs)


def _calibration_row(
    stack: str,
    n_pairs: int,
    cal: KeepRuleCalibration,
    stable: StableFalsePositive,
) -> dict:
    """Sign-flip null fields plus the stable-pixel false-positive rate."""
    return {
        "stack": stack,
        "n_pairs": n_pairs,
        "n_eligible": cal.n_eligible,
        "observed_kept_fraction": _json_float(cal.observed_fraction),
        "null_mean": _json_float(cal.null_mean),
        "null_p95": _json_float(cal.null_p95),
        "draws": cal.draws,
        "seed": cal.seed,
        "exceeds_null": cal.exceeds_null,
        "n_stable": stable.n_stable,
        "stable_n_kept": stable.n_kept,
        "stable_kept_fraction": _json_float(stable.kept_fraction),
        "exceeds_stable": exceeds_stable_rate(cal.observed_fraction, stable.kept_fraction),
    }


def correct_pair(
    unwrapped_rad: np.ndarray,
    ionosphere_rad: np.ndarray,
    components: np.ndarray,
    elevation_m: np.ndarray,
    slope_deg: np.ndarray,
    aspect_deg: np.ndarray,
    *,
    los_east: float,
    los_north: float,
    los_up: float,
    incidence_deg: float,
    temporal_baseline_days: float,
    wavelength_m: float = WAVELENGTH_M,
    valley_floor_max_slope_deg: float = VALLEY_FLOOR_MAX_SLOPE_DEG,
    min_abs_cos: float = MIN_ABS_COS_XI,
    extra_valid: np.ndarray | None = None,
) -> dict:
    """Run one GUNW pair from phase arrays to LOS, downslope, and the pair RMS.

    Valley-floor pixels define the troposphere line and the residual RMS.
    They are removed from ``d_downslope_mm`` so the hillslope test does not
    score the calibration sample. ``d_downslope_stable_mm`` keeps only that
    sample, for the same keep-rule's false-positive rate. Layover and shadow
    are masked. Pixels outside the reference connected component stay NaN.
    """
    phase = subtract_ionosphere(unwrapped_rad, ionosphere_rad)
    los_raw = los_displacement_mm(phase, wavelength_m)
    los_ref, ref_id = mask_to_reference_component(los_raw, components)
    elev_ref, _ = mask_to_reference_component(elevation_m, components)
    slope_ref, _ = mask_to_reference_component(slope_deg, components)
    aspect_ref, _ = mask_to_reference_component(aspect_deg, components)
    look = look_azimuth_deg(los_east, los_north)
    layover = layover_or_shadow(slope_ref, aspect_ref, incidence_deg, look)
    valid = np.isfinite(los_ref) & ~layover
    if extra_valid is not None:
        valid &= np.asarray(extra_valid, dtype=bool)
    stable = (
        valid
        & np.isfinite(elev_ref)
        & np.isfinite(slope_ref)
        & (slope_ref <= valley_floor_max_slope_deg)
    )
    offset, scale, rms, n_stable = fit_los_elevation(los_ref, elev_ref, stable)
    corrected = remove_stratified_troposphere(los_ref, elev_ref, offset, scale)
    corrected[~valid | ~np.isfinite(elev_ref)] = np.nan
    down_full = downslope_displacement_mm(
        corrected, slope_ref, aspect_ref, los_east, los_north, los_up, min_abs_cos
    )
    down = down_full.copy()
    down[stable | layover | ~np.isfinite(slope_ref)] = np.nan
    rate = annual_rate_mm_per_yr(down, temporal_baseline_days)
    down_stable = down_full.copy()
    down_stable[~stable] = np.nan
    rate_stable = annual_rate_mm_per_yr(down_stable, temporal_baseline_days)
    return {
        "d_los_mm": corrected,
        "d_downslope_mm": down,
        "rate_mm_per_yr": rate,
        "d_downslope_stable_mm": down_stable,
        "rate_stable_mm_per_yr": rate_stable,
        "residual_rms_mm": rms,
        "tropo_offset_mm": offset,
        "tropo_scale_mm_per_m": scale,
        "n_stable": n_stable,
        "reference_component_id": ref_id,
        "n_layover_shadow": int(np.count_nonzero(layover & np.isfinite(slope_ref))),
        "n_valid": int(np.count_nonzero(valid)),
        "n_eligible": int(np.count_nonzero(np.isfinite(down))),
        "look_azimuth_deg": look,
        "stable": stable,
    }


def product_valid_land(mask: np.ndarray) -> np.ndarray:
    """Land pixels with a valid subswath in both acquisitions (D-102272 §5.3).

    The spec type is UByte. The code is three digits: hundreds are the
    reference water flag (1 = water), tens the reference subswath, ones the
    secondary subswath. A 0 subswath digit is an invalid sample. Fill is 255.
    Provisional P05023 stores that byte in the low 8 bits of a uint32
    (measured on the first Aburrá granule: 16777228 → 12, 16777340 → 124).
    """
    raw = np.asarray(mask)
    if np.issubdtype(raw.dtype, np.floating):
        finite = np.isfinite(raw) & (raw >= 0)
    else:
        finite = np.ones(raw.shape, dtype=bool)
        if np.issubdtype(raw.dtype, np.signedinteger):
            finite = raw >= 0
    codes = np.zeros(raw.shape, dtype=np.int16)
    if np.any(finite):
        codes[finite] = np.asarray(raw[finite], dtype=np.uint32) & np.uint32(0xFF)
    water = codes // 100
    ref_swath = (codes // 10) % 10
    sec_swath = codes % 10
    return finite & (codes != 255) & (water == 0) & (ref_swath != 0) & (sec_swath != 0)


def compute_landslide_insar_kinematics(
    gunw_unw_gcs: str,
    gunw_iono_gcs: str,
    gunw_coh_gcs: str,
    gunw_conncomp_gcs: str,
    aoi: ee.Geometry,
    rain_start_date: str = "2026-10-29",
    rain_end_date: str = "2026-11-13",
    temporal_baseline_days: float = 12.0,
    inc_angle_deg: float = 37.5,
    sat_heading_deg: float = -12.0,  # Ascending NISAR orbit over Colombia (~348 deg)
) -> ee.Image:
    """GEE entrypoint retained for ``mcp_servers/gee_fusion_mcp.py``.

    The Aburrá noise-floor pipeline is the numpy functions above. This graph
    keeps the band names that caller already selects.
    """
    phi_unw = ee.Image.loadGeoTIFF(gunw_unw_gcs).rename("phi_unw")
    phi_iono = ee.Image.loadGeoTIFF(gunw_iono_gcs).rename("phi_iono")
    coh = ee.Image.loadGeoTIFF(gunw_coh_gcs).rename("coherence")
    conn_comp = ee.Image.loadGeoTIFF(gunw_conncomp_gcs).rename("conn_comp")

    fabdem = (
        ee.ImageCollection("projects/sat-io/open-datasets/FABDEM")
        .filterBounds(aoi)
        .mosaic()
        .clip(aoi)
        .rename("elev_m")
    )
    terrain = ee.Terrain.products(fabdem)
    slope_deg = terrain.select("slope")
    aspect_deg = terrain.select("aspect")

    valid_insar_mask = coh.gte(0.35).And(conn_comp.gt(0))
    phi_iono_corr = phi_unw.subtract(phi_iono).updateMask(valid_insar_mask)

    stable_mask = slope_deg.lt(8.0).And(valid_insar_mask)
    tropo_fit = (
        ee.Image.cat([fabdem, phi_iono_corr])
        .updateMask(stable_mask)
        .reduceRegion(
            reducer=ee.Reducer.linearFit(),
            geometry=aoi,
            scale=90,
            maxPixels=1e8,
            bestEffort=True,
        )
    )
    k_tropo = ee.Number(ee.Dictionary(tropo_fit).get("scale", 0.0))
    c_tropo = ee.Number(ee.Dictionary(tropo_fit).get("offset", 0.0))
    phi_tropo = fabdem.multiply(k_tropo).add(c_tropo)

    lambda_mm = 240.0
    d_los_mm = (
        phi_iono_corr.subtract(phi_tropo).multiply(-lambda_mm / (4.0 * math.pi)).rename("d_los_mm")
    )

    deg2rad = math.pi / 180.0
    projection_img = (
        ee.Image.cat([d_los_mm, slope_deg, aspect_deg])
        .expression(
            """
            var theta = inc_deg * deg2rad;
            var alpha = heading_deg * deg2rad;
            var los_e = -sin(theta) * cos(alpha);
            var los_n =  sin(theta) * sin(alpha);
            var los_u =  cos(theta);
            var beta = b('slope') * deg2rad;
            var psi  = b('aspect') * deg2rad;
            var slp_e =  cos(beta) * sin(psi);
            var slp_n =  cos(beta) * cos(psi);
            var slp_u = -sin(beta);
            var cos_xi = (los_e * slp_e) + (los_n * slp_n) + (los_u * slp_u);
            var reg_cos_xi = abs(cos_xi) < 0.20 ? (cos_xi >= 0 ? 0.20 : -0.20) : cos_xi;
            var d_downslope_mm = abs(b('d_los_mm') / reg_cos_xi);
            var v_downslope_mm_yr = d_downslope_mm * (365.25 / dt_days);
            v_downslope_mm_yr
            """,
            {
                "inc_deg": inc_angle_deg,
                "heading_deg": sat_heading_deg,
                "dt_days": temporal_baseline_days,
                "deg2rad": deg2rad,
            },
        )
        .updateMask(slope_deg.gte(15.0))
        .rename("v_downslope_mm_yr")
    )

    chirps_15d = (
        ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
        .filterBounds(aoi)
        .filterDate(rain_start_date, rain_end_date)
        .sum()
        .clip(aoi)
        .rename("rain_15d_mm")
    )
    hklsi = (
        ee.Image.cat([projection_img, slope_deg, chirps_15d])
        .expression(
            """
            var v_norm = clamp(b('v_downslope_mm_yr') / 120.0, 0.0, 1.0);
            var s_norm = clamp((b('slope') - 15.0) / 30.0, 0.0, 1.0);
            var r_norm = clamp(b('rain_15d_mm') / 200.0, 0.0, 1.0);
            (0.50 * v_norm) + (0.25 * s_norm) + (0.25 * r_norm)
            """
        )
        .rename("landslide_hazard_index")
    )
    return ee.Image.cat([d_los_mm, projection_img, slope_deg, chirps_15d, coh, hklsi])


def _load_env(env_file) -> None:
    """Load KEY=VALUE lines without overriding the process environment or printing values."""
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        import os

        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _json_float(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def render_report(summary: dict) -> str:
    """Render the Aburrá report from measured summary fields."""
    lines = [
        "# Aburrá landslide InSAR — noise-floor result",
        "",
        "**Label: PROVISIONAL.** Granules below are ASF provisional (`PR`) GUNW products.",
        "Granizal (2025-06-24) predates the NISAR record and is not a detection here.",
        "HKLSI is not computed.",
        "",
    ]
    lines.extend(_verdict_lines(summary))
    lines.extend(
        [
            "## Reproduce",
            "",
            "```",
            summary["command"],
            "```",
            "",
            (
                f"Measured {summary['measured_at_bogota']} Bogotá (UTC−5); "
                f"log time {summary['measured_at_utc']}."
            ),
            "Search: `asf.geo_search`, platform NISAR, processingLevel GUNW,",
            (
                f"bbox [W, S, E, N] = {summary['bbox']} from `{summary['aoi_key']}`, "
                f"start {summary['search_start']}, end {summary['search_end']}."
            ),
            "",
            "## Method",
            "",
            "- Ionosphere screen subtracted from `unwrappedPhase` (the screen ships unapplied).",
            "- Stratified troposphere: LOS-vs-elevation least squares on valley-floor pixels",
            f"  (FABDEM slope ≤ {summary['valley_floor_max_slope_deg']}°), inside the reference",
            "  connected component, outside layover and shadow. Those pixels are the noise",
            "  sample and are excluded from detection.",
            "- Reference component: largest label other than 0 and fill 65535.",
            "- d_LOS = −λ Δφ / 4π with λ = 0.24 m. Positive LOS points toward the sensor.",
            "  The product spec states radians and the LOS unit vector; it does not state",
            "  the phase sign. The sign used here is the ISCE convention cited in",
            "  `los_displacement_mm`.",
            "- Downslope projection uses FABDEM slope and aspect and the granule LOS unit",
            f"  vector. |cos ξ| < {summary['min_abs_cos']} stays missing.",
            "- A rate is kept only where |LOS| exceeds that pair's residual RMS and the",
            "  downslope sign agrees on two pairs that do not share an acquisition date,",
            "  on the same native grid. Ascending and descending grids are not resampled",
            "  onto each other.",
            "- The same keep-rule is applied to the stable valley-floor pixels. Their kept",
            "  fraction is the empirical false-positive rate. Those pixels stay excluded",
            "  from the hillslope count.",
            f"- `config/preregistered.yaml` landslide block: {summary['preregistered_landslide']}.",
            (f"- AOI `{summary['aoi_key']}` read from `config/bailasar.yaml`: {summary['bbox']}."),
            "",
            "## Pairs",
            "",
            "| Granule | Track | Ref → sec | Δt days | n stable | RMS mm | n eligible | n |LOS|>RMS |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for pair in summary["pairs"]:
        lines.append(
            (
                "| {scene} | {track} {direction} fr {frame} | {ref} → {sec} | {dt} | "
                "{n_stable} | {rms} | {n_eligible} | {n_exceed} |"
            ).format(
                scene=pair["scene_name"],
                track=pair.get("track", "missing"),
                direction=pair.get("direction", "missing"),
                frame=pair.get("frame", "missing"),
                ref=pair.get("reference_date") or "missing",
                sec=pair.get("secondary_date") or "missing",
                dt=pair.get("dt_days_text", "missing"),
                n_stable=pair.get("n_stable", "missing"),
                rms=pair.get("rms_text", "missing"),
                n_eligible=pair.get("n_eligible", "missing"),
                n_exceed=pair.get("n_exceed_rms", "missing"),
            )
        )
    lines.extend(["", "## Notes on the pairs", ""])
    lines.extend(summary["notes"])
    lines.extend(["", "## Stacks", ""])
    if not summary["stacks"]:
        lines.append("No stack produced a noise-floor test.")
    for stack in summary["stacks"]:
        lines.append(
            f"- {stack['key']}: {stack['n_pairs']} pairs on one grid, "
            f"{stack['n_pixels_kept']} of {stack.get('n_grid', 'missing')} pixels kept "
            f"(grid {stack.get('grid_text', 'missing')}; positive = downhill: "
            f"{stack.get('n_pixels_positive', 'missing')} positive and "
            f"{stack.get('n_pixels_negative', 'missing')} negative), "
            f"stack median RMS {stack['rms_text']} mm *(measured)*."
        )
    lines.extend(["", "## FABDEM", ""])
    lines.append(summary["fabdem_note"])
    lines.extend(["", "## Open limitations", ""])
    lines.extend(f"- {item}" for item in summary["limitations"])
    lines.append("")
    return "\n".join(lines)


def _repo_root():
    from pathlib import Path

    return Path(__file__).resolve().parents[1]


def _read_yaml(file_path):
    import yaml

    if not file_path.exists():
        return None
    return yaml.safe_load(file_path.read_text(encoding="utf-8"))


def _as_text(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.bytes_):
        return value.decode("utf-8")
    if isinstance(value, np.ndarray):
        if value.shape == ():
            return _as_text(value[()])
        if value.dtype.kind in {"S", "O"}:
            parts = [_as_text(item) for item in value.reshape(-1)]
            return ",".join(parts)
    return str(value)


def _dataset(h5, candidates: list[str]):
    for name in candidates:
        if name in h5:
            return h5[name], name
    return None, None


def _require(h5, candidates: list[str]):
    dataset, name = _dataset(h5, candidates)
    if dataset is None:
        raise KeyError("missing dataset; tried " + ", ".join(candidates))
    return dataset, name


def _window_or_none(coords: np.ndarray, low: float, high: float):
    if coords.size < 2:
        return None
    return slice_bounds(coords, low, high)


def _sample_grid(grid_lon, grid_lat, grid_values, lon, lat, max_dist_m: float = 120.0):
    """Nearest sample of a regular lon/lat raster. Far pixels stay NaN."""
    lon = np.asarray(lon, dtype=np.float64)
    lat = np.asarray(lat, dtype=np.float64)
    dlon = float(grid_lon[1] - grid_lon[0])
    dlat = float(grid_lat[1] - grid_lat[0])
    col = np.rint((lon - float(grid_lon[0])) / dlon).astype(np.int64)
    row = np.rint((lat - float(grid_lat[0])) / dlat).astype(np.int64)
    height, width = grid_values.shape
    inside = (row >= 0) & (row < height) & (col >= 0) & (col < width)
    out = np.full(lon.shape, np.nan, dtype=np.float64)
    if not np.any(inside):
        return out
    rows = row[inside]
    cols = col[inside]
    src_lon = grid_lon[cols]
    src_lat = grid_lat[rows]
    meters_lat = (lat[inside] - src_lat) * 110_540.0
    meters_lon = (lon[inside] - src_lon) * 111_320.0 * np.cos(np.radians(lat[inside]))
    near = np.hypot(meters_lat, meters_lon) <= max_dist_m
    flat = np.full(rows.shape, np.nan, dtype=np.float64)
    flat[near] = grid_values[rows[near], cols[near]]
    out[inside] = flat
    return out


def parse_granule_name(scene_name: str) -> dict:
    """Stream, product, polarization and the two acquisition dates.

    The pattern matches ``scripts/discover_nisar_colombia.py``.
    """
    match = GRANULE_NAME_RE.search(scene_name or "")
    if not match:
        return {
            "stream": None,
            "product": None,
            "polarization": None,
            "date_1": None,
            "date_2": None,
        }
    found = match.groupdict()

    def _iso(token: str | None) -> str | None:
        if not token:
            return None
        return f"{token[:4]}-{token[4:6]}-{token[6:8]}"

    return {
        "stream": found["stream"],
        "product": found["product"],
        "polarization": found["pol"],
        "date_1": _iso(found["t1"]),
        "date_2": _iso(found["t2"]),
    }


def aburra_bbox_from_config(ops: dict | None) -> tuple[tuple[float, float, float, float], str]:
    """Return the Aburrá ``[W, S, E, N]`` box stored in ``config/bailasar.yaml``."""
    if not isinstance(ops, dict):
        raise RuntimeError("config/bailasar.yaml did not load")
    aois = ops.get("aois") or {}
    matches = [str(key) for key in aois if str(key).startswith(ABURRA_AOI_PREFIX)]
    if len(matches) != 1:
        raise RuntimeError(
            "expected one Aburrá AOI whose key starts with "
            f"{ABURRA_AOI_PREFIX} in config/bailasar.yaml, found {matches}"
        )
    key = matches[0]
    raw = aois[key]
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        raise RuntimeError(f"AOI {key} is missing a [W, S, E, N] bbox")
    return tuple(float(item) for item in raw), key


def _search_gunw(
    bbox: tuple[float, float, float, float], search_start: str, search_end: str
) -> list[dict]:
    import asf_search as asf

    west, south, east, north = bbox
    wkt = (
        f"POLYGON(({west} {south}, {east} {south}, {east} {north}, {west} {north}, {west} {south}))"
    )
    results = asf.geo_search(
        platform=[asf.PLATFORM.NISAR],
        processingLevel=["GUNW"],
        intersectsWith=wkt,
        start=search_start,
        end=search_end,
        maxResults=200,
    )
    found = []
    for item in results:
        props = item.properties
        scene = props.get("sceneName") or props.get("fileID") or ""
        parsed = parse_granule_name(scene)
        found.append(
            {
                "scene_name": scene,
                "url": props.get("url"),
                "track": props.get("pathNumber"),
                "frame": props.get("frameNumber"),
                "direction": props.get("flightDirection"),
                "crid": props.get("crid"),
                "stream": parsed["stream"],
                "polarization": parsed["polarization"],
                "filename_reference_date": parsed["date_1"],
                "filename_secondary_date": parsed["date_2"],
                "start": props.get("startTime"),
                "stop": props.get("stopTime"),
                "single_pol_hh": parsed["polarization"] == "SH",
            }
        )
    found.sort(key=lambda row: row["scene_name"])
    return found


def _prefer_provisional(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """Drop an urgent-response copy when the same dates already have a PR granule.

    The UR product is the same acquisition pair, so it is not an independent
    pair. It is listed and not hidden.
    """
    provisional = {
        (
            row["track"],
            row["frame"],
            row["filename_reference_date"],
            row["filename_secondary_date"],
        )
        for row in rows
        if row.get("stream") == "PR"
    }
    kept = []
    skipped = []
    for row in rows:
        key = (
            row["track"],
            row["frame"],
            row["filename_reference_date"],
            row["filename_secondary_date"],
        )
        if row.get("stream") == "UR" and key in provisional:
            skipped.append(row["scene_name"])
            continue
        kept.append(row)
    return kept, skipped


def _read_geometry(h5, bbox, elevation_hint_m: float | None) -> dict:
    """LOS and incidence at the radar-grid cell nearest the AOI center."""
    from pyproj import Transformer

    base = "/science/LSAR/GUNW/metadata/radarGrid"
    x_ds, _ = _require(h5, [f"{base}/xCoordinates"])
    y_ds, _ = _require(h5, [f"{base}/yCoordinates"])
    z_ds, _ = _dataset(h5, [f"{base}/heightAboveEllipsoid"])
    proj_ds, _ = _dataset(
        h5,
        [
            f"{base}/projection",
            "/science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/projection",
        ],
    )
    x = np.array(x_ds[()], dtype=np.float64)
    y = np.array(y_ds[()], dtype=np.float64)
    epsg = int(np.array(proj_ds[()]).reshape(-1)[0]) if proj_ds is not None else 0
    west, south, east, north = bbox
    if epsg in (0, 4326):
        cx, cy = (west + east) / 2.0, (south + north) / 2.0
    else:
        to_grid = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
        cx, cy = to_grid.transform((west + east) / 2.0, (south + north) / 2.0)
    ix = int(np.argmin(np.abs(x - cx)))
    iy = int(np.argmin(np.abs(y - cy)))
    if z_ds is None:
        iz = 0
        z_values = np.array([math.nan])
    else:
        z_values = np.array(z_ds[()], dtype=np.float64).reshape(-1)
        if elevation_hint_m is None or not np.isfinite(z_values).any():
            iz = int(len(z_values) // 2)
        else:
            iz = int(np.argmin(np.abs(z_values - elevation_hint_m)))
    los_x_ds, _ = _require(h5, [f"{base}/losUnitVectorX"])
    los_y_ds, _ = _require(h5, [f"{base}/losUnitVectorY"])
    inc_ds, _ = _dataset(h5, [f"{base}/incidenceAngle"])

    def _voxel(dataset):
        data = np.array(dataset)
        if data.ndim == 3:
            return float(data[iz, iy, ix])
        if data.ndim == 2:
            return float(data[iy, ix])
        return float(np.array(data).reshape(-1)[0])

    los_e = _voxel(los_x_ds)
    los_n = _voxel(los_y_ds)
    los_u = los_up_from_horizontal(los_e, los_n)
    if inc_ds is None:
        incidence = (
            math.degrees(math.acos(min(1.0, max(-1.0, los_u))))
            if math.isfinite(los_u)
            else math.nan
        )
        incidence_source = "derived from los unit vector"
    else:
        incidence = _voxel(inc_ds)
        incidence_source = "radarGrid/incidenceAngle"
    return {
        "los_east": los_e,
        "los_north": los_n,
        "los_up": los_u,
        "incidence_deg": incidence,
        "incidence_source": incidence_source,
        "epsg": epsg,
        "radar_ix": ix,
        "radar_iy": iy,
        "radar_iz": iz,
        "radar_height_m": float(z_values[iz]) if iz < len(z_values) else math.nan,
    }


def _read_pair_arrays(h5, bbox) -> dict:
    """Hyperslab the 80 m HH layers on the native grid over the bbox."""
    from datetime import datetime

    from pyproj import Transformer

    grid = "/science/LSAR/GUNW/grids/frequencyA"
    unw_group = f"{grid}/unwrappedInterferogram"
    phase_ds, phase_name = _require(
        h5, [f"{unw_group}/HH/unwrappedPhase", f"{unw_group}/VV/unwrappedPhase"]
    )
    pol = "HH" if "/HH/" in phase_name else "VV"
    iono_ds, _ = _require(
        h5,
        [
            f"{unw_group}/{pol}/ionospherePhaseScreen",
            f"{unw_group}/{pol}/ionosphericPhaseScreen",
        ],
    )
    comp_ds, _ = _require(h5, [f"{unw_group}/{pol}/connectedComponents"])
    coh_ds, _ = _dataset(h5, [f"{unw_group}/{pol}/coherenceMagnitude"])
    mask_ds, _ = _dataset(h5, [f"{unw_group}/mask"])
    x_ds, _ = _require(h5, [f"{unw_group}/xCoordinates"])
    y_ds, _ = _require(h5, [f"{unw_group}/yCoordinates"])
    proj_ds, _ = _require(h5, [f"{unw_group}/projection", f"{unw_group}/{pol}/projection"])
    freq_ds, _ = _dataset(h5, [f"{grid}/centerFrequency"])
    x_all = np.array(x_ds[()], dtype=np.float64)
    y_all = np.array(y_ds[()], dtype=np.float64)
    epsg = int(np.array(proj_ds[()]).reshape(-1)[0])
    west, south, east, north = bbox
    if epsg in (0, 4326):
        xmin, ymin, xmax, ymax = west, south, east, north
        to_lonlat = None
    else:
        to_grid = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
        corners = [
            to_grid.transform(lon, lat)
            for lon, lat in ((west, south), (east, south), (east, north), (west, north))
        ]
        xs, ys = zip(*corners, strict=True)
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        to_lonlat = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    x_win = _window_or_none(x_all, xmin, xmax)
    y_win = _window_or_none(y_all, ymin, ymax)
    if x_win is None or y_win is None:
        raise RuntimeError("AOI falls outside this granule grid")
    c0, c1 = x_win
    r0, r1 = y_win
    phase = np.array(phase_ds[r0:r1, c0:c1], dtype=np.float64)
    iono = np.array(iono_ds[r0:r1, c0:c1], dtype=np.float64)
    components = np.array(comp_ds[r0:r1, c0:c1])
    phase[~np.isfinite(phase)] = np.nan
    iono[~np.isfinite(iono)] = np.nan
    x = x_all[c0:c1]
    y = y_all[r0:r1]
    if phase.shape != (y.size, x.size):
        raise RuntimeError(
            f"phase shape {phase.shape} does not match coordinates {(y.size, x.size)}"
        )
    xx, yy = np.meshgrid(x, y)
    if to_lonlat is None:
        lon, lat = xx, yy
    else:
        lon, lat = to_lonlat.transform(xx, yy)
    ref_raw = _as_text(h5["/science/LSAR/identification/referenceZeroDopplerStartTime"][()])
    sec_raw = _as_text(h5["/science/LSAR/identification/secondaryZeroDopplerStartTime"][()])
    ref_dt = datetime.fromisoformat(ref_raw.replace("Z", "")[:19])
    sec_dt = datetime.fromisoformat(sec_raw.replace("Z", "")[:19])
    dt_days = (sec_dt - ref_dt).total_seconds() / 86400.0
    frequency = float(np.array(freq_ds[()]).reshape(-1)[0]) if freq_ds is not None else math.nan
    coherence = None
    if coh_ds is not None:
        coherence = np.array(coh_ds[r0:r1, c0:c1], dtype=np.float64)
        coherence[~np.isfinite(coherence)] = np.nan
    land = None
    if mask_ds is not None:
        land = product_valid_land(np.array(mask_ds[r0:r1, c0:c1]))
    return {
        "phase": phase,
        "iono": iono,
        "components": components,
        "coherence": coherence,
        "land": land,
        "x": x,
        "y": y,
        "lon": lon,
        "lat": lat,
        "epsg": epsg,
        "reference_time": ref_raw,
        "secondary_time": sec_raw,
        "reference_date": ref_dt.date().isoformat(),
        "secondary_date": sec_dt.date().isoformat(),
        "dt_days": dt_days,
        "center_frequency_hz": frequency,
        "polarization": pol,
        "n_phase": int(np.count_nonzero(np.isfinite(phase))),
        "n_iono": int(np.count_nonzero(np.isfinite(iono))),
    }


def _fetch_fabdem(bbox: tuple[float, float, float, float]) -> dict:
    """Sample FABDEM elevation, slope, and aspect on an 80 m geographic grid.

    ``ee.Terrain.slope`` is masked on the geographic mosaic. The collection's
    native posting is 1 arc-second; the gradient is taken after a reprojection
    to EPSG:3857 at 30 m. Masked GEE pixels are requested as the transport
    sentinel -9999 and converted back to NaN. That sentinel is not written as data.
    """
    import io

    from gee_math.ee_session import init_ee

    init_ee()
    west, south, east, north = bbox
    mid_lat = (south + north) / 2.0
    width = max(2, round((east - west) * 111_320.0 * math.cos(math.radians(mid_lat)) / 80.0))
    height = max(2, round((north - south) * 110_540.0 / 80.0))
    aoi = ee.Geometry.Rectangle([west, south, east, north])
    collection = ee.ImageCollection("projects/sat-io/open-datasets/FABDEM").filterBounds(aoi)
    fabdem = (
        collection.mosaic().setDefaultProjection(collection.first().projection()).rename("elev_m")
    )
    metric = fabdem.reproject(crs="EPSG:3857", scale=30)
    terrain = ee.Terrain.products(metric)
    image = ee.Image.cat(
        [
            metric.rename("elev_m"),
            terrain.select("slope").rename("slope_deg"),
            terrain.select("aspect").rename("aspect_deg"),
        ]
    ).unmask(-9999)
    scale_x = (east - west) / width
    scale_y = -(north - south) / height
    raw = ee.data.computePixels(
        {
            "expression": image.clip(aoi),
            "fileFormat": "NPY",
            "grid": {
                "dimensions": {"width": width, "height": height},
                "affineTransform": {
                    "scaleX": scale_x,
                    "shearX": 0,
                    "translateX": west,
                    "shearY": 0,
                    "scaleY": scale_y,
                    "translateY": north,
                },
                "crsCode": "EPSG:4326",
            },
        }
    )
    structured = np.load(io.BytesIO(raw))
    elev = structured["elev_m"].astype(np.float64)
    slope = structured["slope_deg"].astype(np.float64)
    aspect = structured["aspect_deg"].astype(np.float64)
    for band in (elev, slope, aspect):
        band[band == -9999] = np.nan
        band[~np.isfinite(band)] = np.nan
    lon = west + (np.arange(width) + 0.5) * scale_x
    lat = north + (np.arange(height) + 0.5) * scale_y
    finite = elev[np.isfinite(elev)]
    median_elev = float(np.median(finite)) if finite.size else math.nan
    center = ee.Geometry.Point([(west + east) / 2.0, (south + north) / 2.0])
    point = fabdem.reduceRegion(ee.Reducer.first(), center, 30).getInfo()
    point_elev = point.get("elev_m") if isinstance(point, dict) else None
    return {
        "elev_m": elev,
        "slope_deg": slope,
        "aspect_deg": aspect,
        "lon": lon,
        "lat": lat,
        "width": width,
        "height": height,
        "median_elev_m": median_elev,
        "n_finite": int(finite.size),
        "n_pixels": int(elev.size),
        "point_elev_m": None if point_elev is None else float(point_elev),
        "source": (
            "GEE projects/sat-io/open-datasets/FABDEM; ee.Terrain.products after EPSG:3857 at 30 m"
        ),
    }


def _exceed_count(los_mm: np.ndarray, down_mm: np.ndarray, rms: float) -> int:
    if not math.isfinite(rms):
        return 0
    hit = np.isfinite(los_mm) & np.isfinite(down_mm) & (np.abs(los_mm) > rms)
    return int(np.count_nonzero(hit))


def _stack_pairs(processed: list[dict]) -> list[list[dict]]:
    """Group pairs that share a native grid to 1 m."""
    groups: list[list[dict]] = []
    for pair in processed:
        placed = False
        for group in groups:
            ref = group[0]
            if pair["track"] != ref["track"] or pair["frame"] != ref["frame"]:
                continue
            if pair["x"].shape != ref["x"].shape or pair["y"].shape != ref["y"].shape:
                continue
            if np.max(np.abs(pair["x"] - ref["x"])) > 1.0:
                continue
            if np.max(np.abs(pair["y"] - ref["y"])) > 1.0:
                continue
            group.append(pair)
            placed = True
            break
        if not placed:
            groups.append([pair])
    return groups


def _fmt_num(value, digits: int = 3) -> str:
    number = _json_float(value)
    if number is None:
        return "missing"
    return f"{number:.{digits}f}"


def _fmt_frac(value, digits: int = 4) -> str:
    return _fmt_num(value, digits)


def _fmt_int(value) -> str:
    if isinstance(value, bool) or value is None:
        return "missing"
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "missing"
    return f"{number:,}"


def _fmt_bool(value) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "missing"


def _verdict_lines(summary: dict) -> list[str]:
    """Headline, calibration table, then the raw keep-rule counts."""
    lines = ["## Verdict", ""]
    calibration = summary.get("calibration") or []
    if calibration:
        headline = str(summary["verdict"]).strip()
        if headline[:1].islower():
            headline = headline[0].upper() + headline[1:]
        if not headline.endswith("."):
            headline += "."
        lines.append(f"**{headline}** *(measured, PROVISIONAL)*")
        lines.append("")
        lines.append(
            "The keep-rule below passes noise, so its raw kept count is not a detection. "
            "The hillslope kept fraction is shown beside the stable-pixel false-positive "
            "rate and the sign-flip null. All of these fractions are *(measured, PROVISIONAL)*."
        )
        lines.append("")
        lines.append(
            "| Stack | Pairs | Hillslope px | Hillslope kept fraction | Stable px | "
            "Stable kept fraction | Sign-flip null mean | Null 95th pct | "
            "Exceeds sign-flip null | Exceeds stable |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---|---|")
        for row in calibration:
            lines.append(
                "| {stack} | {pairs} | {eligible} | {observed} | {n_stable} | {stable} | "
                "{null_mean} | {null_p95} | {exceeds_null} | {exceeds_stable} |".format(
                    stack=row.get("stack", "missing"),
                    pairs=row.get("n_pairs", "missing"),
                    eligible=_fmt_int(row.get("n_eligible")),
                    observed=_fmt_frac(row.get("observed_kept_fraction")),
                    n_stable=_fmt_int(row.get("n_stable")),
                    stable=_fmt_frac(row.get("stable_kept_fraction")),
                    null_mean=_fmt_frac(row.get("null_mean")),
                    null_p95=_fmt_frac(row.get("null_p95")),
                    exceeds_null=_fmt_bool(row.get("exceeds_null")),
                    exceeds_stable=_fmt_bool(row.get("exceeds_stable")),
                )
            )
        lines.append("")
        lines.append(f"{summary.get('stable_comparison', 'missing')} *(measured, PROVISIONAL)*")
        lines.append("")
        slope = summary.get("valley_floor_max_slope_deg", "missing")
        lines.append(
            "- Hillslope px: finite downslope in at least one pair of the stack "
            "(valley-floor stable pixels excluded upstream)."
        )
        lines.append(
            "- Stable px: finite downslope on the valley-floor sample in at least one "
            f"pair (FABDEM slope ≤ {slope}°, inside the reference component, outside "
            "layover and shadow). The stable kept fraction is the keep-rule's empirical "
            "false-positive rate on those pixels."
        )
        lines.append(
            "- Sign-flip null: each draw multiplies every pair's downslope field by one "
            f"seeded ±1 ({summary.get('calibration_draws', 'missing')} draws, "
            f"seed {summary.get('calibration_seed', 'missing')}). That keeps each pair's "
            "noise and spatial structure and breaks the sign consistency real motion "
            "would show across pairs. No value is generated."
        )
        lines.append(
            "- Exceeds stable: the hillslope kept fraction is greater than the stable-pixel "
            "kept fraction. No extra margin is pre-registered. That comparison becomes a "
            "candidate only when the hillslope fraction also exceeds the sign-flip 95th "
            "percentile. Below that null, the headline stays the null sentence."
        )
        lines.append(f"- Command: `{summary['command']}`.")
        lines.append("")
        lines.append("Raw keep-rule output, kept for the record, **not a detection**:")
        lines.append("")
        raw = summary.get("raw_keep_verdict")
        if raw:
            lines.append(f"{raw}.")
            lines.append("")
    else:
        lines.append(str(summary["verdict"]))
        lines.append("")
    lines.extend(
        [
            f"Noise floor: {summary['noise_floor_text']} *(measured)*.",
            (
                f"Denominator: {summary['n_pairs_with_rms']} pairs with a finite "
                "stable-pixel residual RMS,"
            ),
            (f"out of {summary['n_granules_sh']} single-pol HH granules returned by the search"),
            (
                f"({summary['n_granules_searched']} GUNW hits before the SH filter; "
                f"{summary['n_ur_copies_skipped']} UR copies of a PR pair were not reprocessed)."
            ),
            f"Pixels with a kept downslope rate: {summary['n_pixels_kept']}.",
            (
                "That count is the sum of the per-track native grids. "
                "The grids are not resampled onto each other."
            ),
            "",
        ]
    )
    return lines


def _gate_window(root) -> tuple[str, str]:
    """Search window recorded in the hour-2 gate catalog."""
    import json

    catalog = json.loads((root / "nisar_colombia_granules_2026.json").read_text(encoding="utf-8"))
    start, end = catalog["window"]
    if isinstance(start, str) and len(start) == 10:
        start = start + "T00:00:00Z"
    return str(start), str(end)


def run_aburra(
    bbox: tuple[float, float, float, float] | None = None,
    *,
    draws: int = 200,
    seed: int = 20261115,
) -> dict:
    """Search, correct, and score every single-pol HH Aburrá GUNW in the window.

    ``draws`` and ``seed`` size the sign-flip null. They are not a detection
    threshold. The stable-pixel false-positive rate uses the same keep-rule
    and no draws.
    """
    import json
    import os
    from datetime import datetime
    from zoneinfo import ZoneInfo

    import earthaccess

    root = _repo_root()
    _load_env(root / ".env")
    os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
    prereg = _read_yaml(root / "config" / "preregistered.yaml")
    ops = _read_yaml(root / "config" / "bailasar.yaml")
    landslide_block = None if not isinstance(prereg, dict) else prereg.get("landslide")
    rule_note = check_noise_floor_rule(landslide_block)
    if isinstance(landslide_block, dict) and "valley_floor_max_slope_deg" in landslide_block:
        valley = float(landslide_block["valley_floor_max_slope_deg"])
        prereg_text = f"{rule_note}; valley_floor_max_slope_deg read from the file"
    else:
        valley = VALLEY_FLOOR_MAX_SLOPE_DEG
        prereg_text = (
            f"{rule_note}; valley_floor_max_slope_deg not pre-registered, "
            f"code constant {VALLEY_FLOOR_MAX_SLOPE_DEG} used"
        )
    config_bbox, aoi_key = aburra_bbox_from_config(ops if isinstance(ops, dict) else None)
    if bbox is None:
        bbox = config_bbox
    search_start, search_end = _gate_window(root)

    now_utc = datetime.now(ZoneInfo("UTC"))
    now_bogota = now_utc.astimezone(ZoneInfo("America/Bogota"))
    print(f"FABDEM grid for {aoi_key} bbox {bbox}", flush=True)
    fabdem = _fetch_fabdem(bbox)
    print(
        f"FABDEM median elevation {fabdem['median_elev_m']:.1f} m "
        f"on {fabdem['n_finite']}/{fabdem['n_pixels']} finite pixels",
        flush=True,
    )
    auth = earthaccess.login(strategy="environment", persist=False)
    if not getattr(auth, "authenticated", False):
        raise RuntimeError("earthaccess login did not authenticate")
    catalog = _search_gunw(bbox, search_start, search_end)
    hh_rows = [row for row in catalog if row["single_pol_hh"]]
    selected, skipped_ur = _prefer_provisional(hh_rows)
    print(
        f"ASF GUNW {len(catalog)}; single-pol HH {len(hh_rows)}; "
        f"processing {len(selected)} after dropping {len(skipped_ur)} UR copies",
        flush=True,
    )
    fs = earthaccess.get_fsspec_https_session()
    import h5py

    processed: list[dict] = []
    pair_rows: list[dict] = []
    for row in selected:
        print(f"reading {row['scene_name']}", flush=True)
        record = {
            "scene_name": row["scene_name"],
            "track": row["track"],
            "frame": row["frame"],
            "direction": row["direction"],
            "crid": row["crid"],
            "url": row["url"],
            "status": "ok",
        }
        try:
            with fs.open(row["url"], "rb") as remote, h5py.File(remote, "r") as h5:
                arrays = _read_pair_arrays(h5, bbox)
                geometry = _read_geometry(h5, bbox, fabdem["median_elev_m"])
            elev = _sample_grid(
                fabdem["lon"],
                fabdem["lat"],
                fabdem["elev_m"],
                arrays["lon"],
                arrays["lat"],
            )
            slope = _sample_grid(
                fabdem["lon"],
                fabdem["lat"],
                fabdem["slope_deg"],
                arrays["lon"],
                arrays["lat"],
            )
            aspect = _sample_grid(
                fabdem["lon"], fabdem["lat"], fabdem["aspect_deg"], arrays["lon"], arrays["lat"]
            )
            corrected = correct_pair(
                arrays["phase"],
                arrays["iono"],
                arrays["components"],
                elev,
                slope,
                aspect,
                los_east=geometry["los_east"],
                los_north=geometry["los_north"],
                los_up=geometry["los_up"],
                incidence_deg=geometry["incidence_deg"],
                temporal_baseline_days=arrays["dt_days"],
                valley_floor_max_slope_deg=valley,
                extra_valid=arrays["land"],
            )
            wavelength = (
                SPEED_OF_LIGHT_M_S / arrays["center_frequency_hz"]
                if (
                    math.isfinite(arrays["center_frequency_hz"])
                    and arrays["center_frequency_hz"] > 0
                )
                else math.nan
            )
            record.update(
                {
                    "reference_date": arrays["reference_date"],
                    "secondary_date": arrays["secondary_date"],
                    "reference_time": arrays["reference_time"],
                    "secondary_time": arrays["secondary_time"],
                    "filename_reference_date": row.get("filename_reference_date"),
                    "filename_secondary_date": row.get("filename_secondary_date"),
                    "stream": row.get("stream"),
                    "dt_days": arrays["dt_days"],
                    "dt_days_text": _fmt_num(arrays["dt_days"], 2),
                    "center_frequency_hz": arrays["center_frequency_hz"],
                    "wavelength_product_m": wavelength,
                    "polarization": arrays["polarization"],
                    "epsg": arrays["epsg"],
                    "n_phase": arrays["n_phase"],
                    "n_iono": arrays["n_iono"],
                    "n_stable": corrected["n_stable"],
                    "n_valid": corrected["n_valid"],
                    "n_eligible": corrected["n_eligible"],
                    "n_layover_shadow": corrected["n_layover_shadow"],
                    "residual_rms_mm": corrected["residual_rms_mm"],
                    "rms_text": _fmt_num(corrected["residual_rms_mm"], 3),
                    "tropo_offset_mm": corrected["tropo_offset_mm"],
                    "tropo_scale_mm_per_m": corrected["tropo_scale_mm_per_m"],
                    "reference_component_id": corrected["reference_component_id"],
                    "incidence_deg": geometry["incidence_deg"],
                    "incidence_source": geometry["incidence_source"],
                    "los_east": geometry["los_east"],
                    "los_north": geometry["los_north"],
                    "los_up": geometry["los_up"],
                    "n_exceed_rms": _exceed_count(
                        corrected["d_los_mm"],
                        corrected["d_downslope_mm"],
                        corrected["residual_rms_mm"],
                    ),
                    "dates": frozenset(
                        date
                        for date in (arrays["reference_date"], arrays["secondary_date"])
                        if date
                    ),
                }
            )
            out_dir = root / "local_cache" / "aburra" / "pairs"
            out_dir.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(
                out_dir / f"{row['scene_name']}.npz",
                d_los_mm=corrected["d_los_mm"].astype(np.float32),
                d_downslope_mm=corrected["d_downslope_mm"].astype(np.float32),
                rate_mm_per_yr=corrected["rate_mm_per_yr"].astype(np.float32),
                x=arrays["x"],
                y=arrays["y"],
                epsg=np.int32(arrays["epsg"]),
            )
            processed.append(
                {
                    **record,
                    "x": arrays["x"],
                    "y": arrays["y"],
                    "d_los_mm": corrected["d_los_mm"],
                    "d_downslope_mm": corrected["d_downslope_mm"],
                    "rate_mm_per_yr": corrected["rate_mm_per_yr"],
                    "d_downslope_stable_mm": corrected["d_downslope_stable_mm"],
                    "rate_stable_mm_per_yr": corrected["rate_stable_mm_per_yr"],
                }
            )
            print(
                f"  dt={arrays['dt_days']:.2f} d  stable={corrected['n_stable']}  "
                f"rms={corrected['residual_rms_mm']}  eligible={corrected['n_eligible']}",
                flush=True,
            )
        except Exception as exc:
            record["status"] = "missing"
            record["error"] = f"{type(exc).__name__}: {exc}"
            record["dt_days_text"] = "missing"
            record["rms_text"] = "missing"
            record["n_stable"] = "missing"
            record["n_eligible"] = "missing"
            record["n_exceed_rms"] = "missing"
            record["reference_date"] = None
            record["secondary_date"] = None
            print(f"  failed {record['error']}", flush=True)
        pair_rows.append(record)

    stacks_out = []
    calibration_rows: list[dict] = []
    kept_total = 0
    rms_values = [
        float(pair["residual_rms_mm"])
        for pair in processed
        if math.isfinite(pair["residual_rms_mm"])
    ]
    for group in _stack_pairs(processed):
        los = [pair["d_los_mm"] for pair in group]
        down = [pair["d_downslope_mm"] for pair in group]
        rate = [pair["rate_mm_per_yr"] for pair in group]
        rms = [pair["residual_rms_mm"] for pair in group]
        dates = [pair["dates"] for pair in group]
        result = noise_floor(los, down, rate, rms, dates)
        kept_total += result.n_pixels_kept
        head = group[0]
        key = f"track {head['track']} frame {head['frame']} {head['direction']}"
        print(f"stack {key}: {result.verdict}", flush=True)
        print(
            f"calibrating {key}: stable-pixel false-positive rate and "
            f"sign-flip null ({draws} draws, seed {seed})",
            flush=True,
        )
        stable_fp = stable_pixel_false_positive(
            los,
            [pair["d_downslope_stable_mm"] for pair in group],
            [pair["rate_stable_mm_per_yr"] for pair in group],
            rms,
            dates,
        )
        cal = calibrate_keep_rule(los, down, rate, rms, dates, draws=draws, seed=seed)
        row = _calibration_row(key, result.n_pairs, cal, stable_fp)
        calibration_rows.append(row)
        print(
            f"  hillslope kept {_fmt_frac(row['observed_kept_fraction'])} "
            f"of {cal.n_eligible}; stable-pixel false-positive "
            f"{_fmt_frac(row['stable_kept_fraction'])} "
            f"({stable_fp.n_kept} of {stable_fp.n_stable}); "
            f"sign-flip null mean {_fmt_frac(row['null_mean'])}, "
            f"p95 {_fmt_frac(row['null_p95'])}",
            flush=True,
        )
        stack_dir = root / "local_cache" / "aburra" / "stacks"
        stack_dir.mkdir(parents=True, exist_ok=True)
        safe = key.replace(" ", "_")
        shape = result.kept_rate_mm_per_yr.shape
        np.savez_compressed(
            stack_dir / f"{safe}.npz",
            kept_rate_mm_per_yr=result.kept_rate_mm_per_yr.astype(np.float32),
            x=head["x"],
            y=head["y"],
        )
        stacks_out.append(
            {
                "key": key,
                "n_pairs": result.n_pairs,
                "n_pixels_kept": result.n_pixels_kept,
                "n_pixels_positive": result.n_pixels_positive,
                "n_pixels_negative": result.n_pixels_negative,
                "n_grid": int(result.kept_rate_mm_per_yr.size),
                "grid_text": f"{shape[0]}×{shape[1]}" if len(shape) == 2 else "missing",
                "noise_floor_mm": _json_float(result.noise_floor_mm),
                "rms_text": _fmt_num(result.noise_floor_mm, 3),
                "verdict": result.verdict,
            }
        )
    calibration_rows.sort(key=lambda item: str(item["stack"]))

    floor_mm = (
        float(np.median(np.asarray(rms_values, dtype=np.float64))) if rms_values else math.nan
    )
    if kept_total == 0:
        raw_verdict = null_motion_sentence(floor_mm, len(rms_values))
    else:
        shown = format_mm(floor_mm) if math.isfinite(floor_mm) else "missing"
        raw_verdict = (
            f"kept downslope rates on {kept_total} pixels; "
            f"noise floor {shown} mm ({len(rms_values)} pairs)"
        )
    comparison = stable_comparison_sentence(calibration_rows)
    verdict = calibration_headline(floor_mm, len(rms_values), calibration_rows)
    notes = []
    if skipped_ur:
        notes.append(
            "Urgent-response copies of a provisional pair with the same track, frame and dates. "
            "They are the same acquisition pair, so they are not a second independent pair:"
        )
        notes.extend(f"- {name}" for name in skipped_ur)
    else:
        notes.append("No urgent-response copy of a provisional pair was returned by the search.")
    long_pairs = [
        pair
        for pair in pair_rows
        if _json_float(pair.get("dt_days")) is not None and abs(pair["dt_days"] - 12.0) > 1.0
    ]
    if long_pairs:
        notes.append(
            "Temporal-baseline mismatch (not a 12-day pair; |Δt − 12| > 1 day), kept visible:"
        )
        for pair in long_pairs:
            notes.append(
                f"- {pair['scene_name']}: Δt = {pair['dt_days_text']} days "
                f"({pair.get('reference_date')} → {pair.get('secondary_date')}) *(measured)*."
            )
    else:
        notes.append("Every processed pair has |Δt − 12| ≤ 1 day.")
    failed = [pair for pair in pair_rows if pair.get("status") != "ok"]
    if failed:
        notes.append("Pairs that did not produce a noise floor:")
        for pair in failed:
            notes.append(f"- {pair['scene_name']}: {pair.get('error', 'missing')}")
    wavelength_notes = sorted(
        {
            round(float(pair["wavelength_product_m"]), 6)
            for pair in pair_rows
            if _json_float(pair.get("wavelength_product_m")) is not None
        }
    )
    if wavelength_notes:
        notes.append(
            "Product wavelength c/centerFrequency = "
            + ", ".join(f"{item:.6f} m" for item in wavelength_notes)
            + " *(measured)*. Displacement uses λ = 0.24 m as fixed by the brief."
        )
    point = fabdem["point_elev_m"]
    fabdem_note = (
        f"{fabdem['source']}. Grid {fabdem['width']}×{fabdem['height']} at ~80 m. "
        f"Median elevation {_fmt_num(fabdem['median_elev_m'], 1)} m on "
        f"{fabdem['n_finite']}/{fabdem['n_pixels']} finite pixels *(measured)*. "
        f"AOI-center `reduceRegion` elevation {_fmt_num(point, 1)} m *(measured)*."
    )
    limitations = [
        "Cross-track sign agreement is not tested: each track keeps its native grid.",
        (
            "The radar-grid LOS vector is the cell nearest the AOI center at the "
            "height nearest the FABDEM median, not the D-102272 §6 per-pixel interpolation."
        ),
        (
            "The 1-sigma RMS test is the rule in the brief. Valley-floor pixels are "
            "excluded from detection because they define that RMS."
        ),
        (
            "No granule after the last secondary date in the table intersects this "
            "box inside the search window."
        ),
    ]
    summary = {
        "verdict": verdict,
        "raw_keep_verdict": raw_verdict,
        "stable_comparison": comparison,
        "calibration": calibration_rows,
        "calibration_draws": draws,
        "calibration_seed": seed,
        "noise_floor_mm": _json_float(floor_mm),
        "noise_floor_text": (f"{format_mm(floor_mm)} mm" if math.isfinite(floor_mm) else "missing"),
        "n_pairs_with_rms": len(rms_values),
        "n_granules_sh": len(hh_rows),
        "n_granules_searched": len(catalog),
        "n_ur_copies_skipped": len(skipped_ur),
        "n_pixels_kept": kept_total,
        "bbox": list(bbox),
        "aoi_key": aoi_key,
        "search_start": search_start,
        "search_end": search_end,
        "valley_floor_max_slope_deg": valley,
        "min_abs_cos": MIN_ABS_COS_XI,
        "preregistered_landslide": prereg_text,
        "command": "uv run python -m gee_math.landslide_insar_math",
        "measured_at_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "measured_at_bogota": now_bogota.strftime("%Y-%m-%d %H:%M"),
        "pairs": [
            {
                key: value
                for key, value in pair.items()
                if key
                not in {
                    "d_los_mm",
                    "d_downslope_mm",
                    "rate_mm_per_yr",
                    "d_downslope_stable_mm",
                    "rate_stable_mm_per_yr",
                    "x",
                    "y",
                    "dates",
                }
            }
            for pair in pair_rows
        ],
        "stacks": stacks_out,
        "notes": notes,
        "fabdem_note": fabdem_note,
        "limitations": limitations,
    }
    cache_dir = root / "local_cache" / "aburra"
    cache_dir.mkdir(parents=True, exist_ok=True)
    if calibration_rows:
        (cache_dir / "calibration.json").write_text(
            json.dumps(calibration_rows, indent=1) + "\n", encoding="utf-8"
        )
    (cache_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    report = render_report(summary)
    report_path = root / "reports" / "aburra.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(verdict, flush=True)
    print(comparison, flush=True)
    print(f"wrote {report_path}", flush=True)
    return summary


_STABLE_RATE_KEYS = ("n_stable", "stable_n_kept", "stable_kept_fraction", "exceeds_stable")


def _saved_stable_rates(path: Path) -> dict[str, dict]:
    """Stable-pixel fields already written by a live run, keyed by stack."""
    import json

    if not path.is_file():
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(rows, list):
        return {}
    saved: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict) or "stack" not in row:
            continue
        kept = {key: row[key] for key in _STABLE_RATE_KEYS if key in row}
        if kept:
            saved[str(row["stack"])] = kept
    return saved


def calibrate_from_cache(root: Path, draws: int, seed: int) -> list[dict]:
    """Keep-rule sign-flip null from the cached per-pair arrays (no network).

    Reads ``local_cache/aburra/summary.json`` (per-pair RMS and dates) and
    ``local_cache/aburra/pairs/<scene>.npz``; groups pairs by track and frame
    exactly as the run does; writes ``local_cache/aburra/calibration.json``.
    The cached pair files have no stable mask, so this path keeps any
    stable-pixel false-positive fields a live run already wrote.
    """
    import json

    prereg = _read_yaml(root / "config" / "preregistered.yaml")
    check_noise_floor_rule(prereg.get("landslide") if isinstance(prereg, dict) else None)
    base = root / "local_cache" / "aburra"
    prior_stable = _saved_stable_rates(base / "calibration.json")
    summary = json.loads((base / "summary.json").read_text(encoding="utf-8"))
    groups: dict[tuple, list[dict]] = {}
    for pair in summary["pairs"]:
        rms = pair.get("residual_rms_mm")
        path = base / "pairs" / f"{pair['scene_name']}.npz"
        if pair.get("status") != "ok" or rms is None or not path.is_file():
            continue
        arrays = np.load(path, allow_pickle=False)
        groups.setdefault((pair["track"], pair["frame"], pair["direction"]), []).append(
            {
                "los": arrays["d_los_mm"].astype(np.float64),
                "down": arrays["d_downslope_mm"].astype(np.float64),
                "rate": arrays["rate_mm_per_yr"].astype(np.float64),
                "rms": float(rms),
                "dates": frozenset({pair["reference_date"], pair["secondary_date"]}),
            }
        )
    out = []
    for (track, frame, direction), group in sorted(groups.items()):
        cal = calibrate_keep_rule(
            [g["los"] for g in group],
            [g["down"] for g in group],
            [g["rate"] for g in group],
            [g["rms"] for g in group],
            [g["dates"] for g in group],
            draws=draws,
            seed=seed,
        )
        stack = f"track {track} frame {frame} {direction}"
        row = {
            "stack": stack,
            "n_pairs": len(group),
            "n_eligible": cal.n_eligible,
            "observed_kept_fraction": _json_float(cal.observed_fraction),
            "null_mean": _json_float(cal.null_mean),
            "null_p95": _json_float(cal.null_p95),
            "draws": cal.draws,
            "seed": cal.seed,
            "exceeds_null": cal.exceeds_null,
        }
        saved = prior_stable.get(stack, {})
        row.update(saved)
        if (
            row.get("stable_kept_fraction") is not None
            and row.get("observed_kept_fraction") is not None
        ):
            row["exceeds_stable"] = exceeds_stable_rate(
                float(row["observed_kept_fraction"]), float(row["stable_kept_fraction"])
            )
        out.append(row)
        print(
            f"{row['stack']}: {row['n_pairs']} pairs, eligible {cal.n_eligible} px; "
            f"kept {cal.observed_fraction:.4f} vs sign-flip null mean {cal.null_mean:.4f}, "
            f"p95 {cal.null_p95:.4f} ({draws} draws, seed {seed}); "
            f"exceeds null: {cal.exceeds_null}",
            flush=True,
        )
    (base / "calibration.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return out


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Aburrá GUNW landslide noise-floor run")
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        default=None,
        help="Override the Aburrá box. The default is config/bailasar.yaml.",
    )
    parser.add_argument(
        "--calibrate-from-cache",
        action="store_true",
        help="Offline: run the keep-rule sign-flip null on local_cache/aburra/pairs.",
    )
    parser.add_argument("--draws", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20261115)
    args = parser.parse_args()
    if args.calibrate_from_cache:
        calibrate_from_cache(Path(__file__).resolve().parents[1], args.draws, args.seed)
        return
    run_aburra(
        tuple(args.bbox) if args.bbox is not None else None,
        draws=args.draws,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
