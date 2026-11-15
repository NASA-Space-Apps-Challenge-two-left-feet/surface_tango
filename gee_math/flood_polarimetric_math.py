"""Dual-pol NISAR L-band flood classes (design doc Hazard 3; config `flood:` section).

Two layers:

* Pure NumPy rule functions (``open_water_fraction``, ``pick_reference_date``, ``classify``).
  They need no Earth Engine and are the logic covered by ``tests/test_flood.py``.
* The Earth Engine pipeline ``compute_flood_scattering_decomposition``, which applies the
  same rules server-side.

Every threshold is read from ``params`` (the ``flood:`` section of
``config/preregistered.yaml``). All five thresholds in ``FLOOD_THRESHOLD_KEYS`` are
**uncalibrated** plan values and are labelled so in every output.

Class 1 (open-water flood): ``delta_hh_db < class1_delta_hh_db_max`` and ``HAND < hand_max_m``.
Class 2 (sub-canopy double bounce): ``delta_hh_db > class2_delta_hh_db_min`` and
``|delta_hv_hh_db| < class2_delta_hv_hh_db_abs_max`` and ``HAND < hand_max_m``.
Without an acceptable dry baseline, Class 2 is not computed (all missing) and Class 1 is
reported as absolute water extent on the post date (``hh_db < open_water_abs_hh_db``).

Missing data stays missing: NaN inputs give NaN outputs and are excluded from denominators.
Sentinel-1 VV is a comparison band only; it never enters a class rule.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np

from bailasar.config import get_config

FLOOD_THRESHOLD_KEYS = [
    "open_water_abs_hh_db",
    "class1_delta_hh_db_max",
    "class2_delta_hh_db_min",
    "class2_delta_hv_hh_db_abs_max",
    "hand_max_m",
]
NO_BASELINE_REASON = "no acceptable dry baseline"


def load_params(section: str) -> Mapping[str, Any]:
    """Read a preregistered section through the shared loader; propagate ConfigError."""
    return get_config().prereg(section)


def _p(params: Mapping[str, Any], key: str) -> float:
    if key not in params:
        raise KeyError(f"flood param {key!r} missing (config/preregistered.yaml flood:)")
    return float(params[key])


# ---------------------------------------------------------------------------------------------
# Pure NumPy rules
# ---------------------------------------------------------------------------------------------


def _floodplain(hand_m: np.ndarray, params: Mapping[str, Any]) -> np.ndarray:
    """True where HAND is finite and below hand_max_m."""
    hand = np.asarray(hand_m, dtype=float)
    with np.errstate(invalid="ignore"):
        return np.isfinite(hand) & (hand < _p(params, "hand_max_m"))


def open_water_fraction(
    hh_db: np.ndarray, hand_m: np.ndarray, params: Mapping[str, Any]
) -> tuple[float, int]:
    """Fraction of valid pixels that are open water on one date.

    Valid = finite HH and HAND < hand_max_m. NaN pixels are excluded from the denominator.
    Returns ``(fraction, denominator)``; the fraction is NaN when the denominator is 0.
    """
    hh = np.asarray(hh_db, dtype=float)
    valid = np.isfinite(hh) & _floodplain(hand_m, params)
    denominator = int(valid.sum())
    if denominator == 0:
        return float("nan"), 0
    water = valid & (hh < _p(params, "open_water_abs_hh_db"))
    return float(water.sum()) / denominator, denominator


def pick_reference_date(
    fractions_by_date: Mapping[str, float], params: Mapping[str, Any]
) -> dict[str, Any]:
    """Pick the driest date as reference and decide whether it is an acceptable baseline.

    ``has_baseline`` is ``(f_wettest - f_driest) / f_wettest >= no_baseline_relative_gap``.
    A gap equal to the threshold counts as a baseline. Equality allows only float rounding
    (absolute 1e-12), so (0.5 - 0.4) / 0.5 = 0.19999999999999996 counts as 0.20 while a
    real shortfall such as (1.0 - 0.8000000001) / 1.0 does not.
    ``f_wettest == 0`` means no baseline. Dates with a NaN fraction are skipped.
    """
    finite = {d: float(f) for d, f in fractions_by_date.items() if np.isfinite(f)}
    if not finite:
        return {
            "reference_date": None,
            "wettest_date": None,
            "relative_gap": float("nan"),
            "has_baseline": False,
            "reason": NO_BASELINE_REASON,
        }
    driest = min(finite, key=finite.get)
    wettest = max(finite, key=finite.get)
    f_dry, f_wet = finite[driest], finite[wettest]
    threshold = _p(params, "no_baseline_relative_gap")
    if f_wet == 0:
        gap = float("nan")
        has_baseline = False
    else:
        gap = (f_wet - f_dry) / f_wet
        has_baseline = gap >= threshold or math.isclose(gap, threshold, rel_tol=0.0, abs_tol=1e-12)
    return {
        "reference_date": driest,
        "wettest_date": wettest,
        "relative_gap": gap,
        "has_baseline": bool(has_baseline),
        "reason": None if has_baseline else NO_BASELINE_REASON,
    }


def classify(
    delta_hh_db: np.ndarray,
    delta_hv_hh_db: np.ndarray,
    hand_m: np.ndarray,
    has_baseline: bool,
    params: Mapping[str, Any],
    *,
    hh_db: np.ndarray | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """Class 1 / Class 2 masks as float arrays: 1.0 = class, 0.0 = not class, NaN = missing.

    Pixels with HAND >= hand_max_m (or NaN HAND) are masked (NaN). NaN inputs stay NaN.
    Without a baseline, Class 2 is all NaN with ``class2_reason`` set, and Class 1 is the
    absolute water extent ``hh_db < open_water_abs_hh_db`` on ``date`` (``hh_db`` required).
    """
    floodplain = _floodplain(hand_m, params)
    meta = {"uncalibrated": list(FLOOD_THRESHOLD_KEYS), "calibrated": False}

    if not has_baseline:
        if hh_db is None or not date:
            raise ValueError("hh_db and date are required without a baseline (water extent)")
        hh = np.asarray(hh_db, dtype=float)
        valid = floodplain & np.isfinite(hh)
        class1 = np.full(hh.shape, np.nan)
        class1[valid] = (hh[valid] < _p(params, "open_water_abs_hh_db")).astype(float)
        return {
            "class1": class1,
            "class2": np.full(hh.shape, np.nan),
            "class1_label": f"water extent on date {date}",
            "class2_reason": NO_BASELINE_REASON,
            **meta,
        }

    d_hh = np.asarray(delta_hh_db, dtype=float)
    d_ratio = np.asarray(delta_hv_hh_db, dtype=float)
    valid1 = floodplain & np.isfinite(d_hh)
    valid2 = valid1 & np.isfinite(d_ratio)

    class1 = np.full(d_hh.shape, np.nan)
    class1[valid1] = (d_hh[valid1] < _p(params, "class1_delta_hh_db_max")).astype(float)

    class2 = np.full(d_hh.shape, np.nan)
    class2[valid2] = (
        (d_hh[valid2] > _p(params, "class2_delta_hh_db_min"))
        & (np.abs(d_ratio[valid2]) < _p(params, "class2_delta_hv_hh_db_abs_max"))
    ).astype(float)

    return {
        "class1": class1,
        "class2": class2,
        "class1_label": "open-water flood (change vs dry baseline)",
        "class2_reason": None,
        **meta,
    }


# ---------------------------------------------------------------------------------------------
# Earth Engine pipeline
# ---------------------------------------------------------------------------------------------


def _ee_db(ee: Any, gcs_path: str, name: str) -> Any:
    """Linear gamma0 COG -> dB. Non-positive pixels are masked (missing), never floored."""
    lin = ee.Image.loadGeoTIFF(gcs_path)
    return lin.updateMask(lin.gt(0)).log10().multiply(10.0).rename(name)


def ee_open_water_fraction(
    gcov_hhhh_gcs: str, aoi: Any, scale_m: float, params: Mapping[str, Any] | None = None
) -> Any:
    """Server-side ``open_water_fraction`` for one date: ee.Dictionary(fraction, denominator).

    Feed the per-date fractions to ``pick_reference_date``. ``scale_m`` is the reduction
    scale chosen by the caller (operational setting, config/bailasar.yaml).
    """
    import ee

    params = load_params("flood") if params is None else params
    hh_db = _ee_db(ee, gcov_hhhh_gcs, "hh_db")
    hand = ee.Image("MERIT/Hydro/v1_0_1").select("hnd")
    # Valid = HH present and HAND < hand_max_m; everything else is masked out of the sums.
    valid = hh_db.mask().And(hand.lt(_p(params, "hand_max_m")))
    water = hh_db.lt(_p(params, "open_water_abs_hh_db"))
    sums = (
        ee.Image.cat([water.rename("water"), valid.rename("valid")])
        .updateMask(valid)
        .reduceRegion(
            reducer=ee.Reducer.sum(), geometry=aoi, scale=scale_m, maxPixels=1e9, bestEffort=True
        )
    )
    # An all-masked AOI reduces to null sums: that is a count of zero valid pixels, and the
    # fraction is then returned as missing (None), never 0.
    valid_n = ee.Number(ee.Algorithms.If(sums.get("valid"), sums.get("valid"), 0))
    water_n = ee.Number(ee.Algorithms.If(sums.get("water"), sums.get("water"), 0))
    return ee.Dictionary(
        {
            "fraction": ee.Algorithms.If(valid_n.gt(0), water_n.divide(valid_n), None),
            "denominator": valid_n,
        }
    )


def compute_flood_scattering_decomposition(
    gcov_hhhh_post_gcs: str,
    gcov_hvhv_post_gcs: str,
    aoi: Any,
    post_date: str,
    has_baseline: bool,
    gcov_hhhh_pre_gcs: str | None = None,
    gcov_hvhv_pre_gcs: str | None = None,
    s1_post_start: str | None = None,
    s1_post_end: str | None = None,
    params: Mapping[str, Any] | None = None,
) -> Any:
    """NISAR L2 GCOV dual-pol flood classes, with MERIT Hydro HAND as floodplain mask.

    ``has_baseline`` comes from ``pick_reference_date`` on the per-date open-water fractions;
    the pre (reference) images are required only when it is True. Thresholds come from
    ``params`` (default: the ``flood:`` section of config/preregistered.yaml) and are
    UNCALIBRATED: the output image carries ``calibrated: False`` and the list of
    uncalibrated keys. Sentinel-1 VV, when dates are given, is a separate comparison band
    (``s1_vv_db_comparison``) and does not enter any class rule.
    """
    import ee

    params = load_params("flood") if params is None else params

    hh_post_db = _ee_db(ee, gcov_hhhh_post_gcs, "hh_post_db")
    hv_post_db = _ee_db(ee, gcov_hvhv_post_gcs, "hv_post_db")
    hand = ee.Image("MERIT/Hydro/v1_0_1").select("hnd").clip(aoi).rename("hand_m")
    floodplain = hand.lt(_p(params, "hand_max_m"))

    bands = [hh_post_db, hv_post_db, hand]

    if has_baseline:
        if not (gcov_hhhh_pre_gcs and gcov_hvhv_pre_gcs):
            raise ValueError("has_baseline=True needs the pre (reference) HH and HV images")
        hh_pre_db = _ee_db(ee, gcov_hhhh_pre_gcs, "hh_pre_db")
        hv_pre_db = _ee_db(ee, gcov_hvhv_pre_gcs, "hv_pre_db")
        delta_hh_db = hh_post_db.subtract(hh_pre_db).rename("delta_hh_db")
        delta_hv_hh_db = (
            hv_post_db.subtract(hh_post_db)
            .subtract(hv_pre_db.subtract(hh_pre_db))
            .rename("delta_hv_hh_db")
        )
        class1 = (
            delta_hh_db.lt(_p(params, "class1_delta_hh_db_max"))
            .updateMask(floodplain)
            .rename("specular_open_flood")
        )
        class2 = (
            delta_hh_db.gt(_p(params, "class2_delta_hh_db_min"))
            .And(delta_hv_hh_db.abs().lt(_p(params, "class2_delta_hv_hh_db_abs_max")))
            .updateMask(floodplain)
            .rename("subcanopy_double_bounce_flood")
        )
        regime = class1.add(class2.multiply(2)).rename("flood_regime_class")
        class1_label = "open-water flood (change vs dry baseline)"
        class2_reason = ""
        bands += [delta_hh_db, delta_hv_hh_db]
    else:
        class1 = (
            hh_post_db.lt(_p(params, "open_water_abs_hh_db"))
            .updateMask(floodplain)
            .rename("specular_open_flood")
        )
        # Fully masked band: Class 2 is missing without a baseline, never zero.
        class2 = ee.Image(0).updateMask(ee.Image(0)).rename("subcanopy_double_bounce_flood")
        regime = class1.rename("flood_regime_class")
        class1_label = f"water extent on date {post_date}"
        class2_reason = NO_BASELINE_REASON

    bands += [class1, class2, regime]

    if s1_post_start and s1_post_end:
        s1 = (
            ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(aoi)
            .filterDate(s1_post_start, s1_post_end)
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
            .select("VV")
        )
        # No S1 scene in the window -> a fully masked (missing) comparison band.
        s1_vv = ee.Image(
            ee.Algorithms.If(
                s1.size().gt(0), s1.median().clip(aoi), ee.Image(0).updateMask(ee.Image(0))
            )
        ).rename("s1_vv_db_comparison")
        bands.append(s1_vv)

    return ee.Image.cat(bands).set(
        {
            "calibrated": False,
            "uncalibrated": list(FLOOD_THRESHOLD_KEYS),
            "has_baseline": bool(has_baseline),
            "post_date": post_date,
            "class1_label": class1_label,
            "class2_reason": class2_reason,
        }
    )
