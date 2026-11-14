"""Known-answer logic tests for the flood rules (validation/ALLOWLIST.md: hand-written arrays).

Every array below is hand-written and every expected value is computed by hand in the
comment next to it. Nothing here reaches the app, the cache or the video.
"""

import math
from pathlib import Path

import numpy as np
import pytest

from gee_math import flood_polarimetric_math as fl

# Same values as the flood: section of config/preregistered.yaml, passed explicitly so the
# tests pin the rule logic, not the config file.
PARAMS = {
    "open_water_abs_hh_db": -18.0,
    "class1_delta_hh_db_max": -5.5,
    "class2_delta_hh_db_min": 3.0,
    "class2_delta_hv_hh_db_abs_max": 1.5,
    "hand_max_m": 18,
    "no_baseline_relative_gap": 0.20,
}

NAN = np.nan


def _same(a, b):
    np.testing.assert_array_equal(np.asarray(a, dtype=float), np.asarray(b, dtype=float))


# --- open-water fraction ---------------------------------------------------------------------


def test_open_water_fraction_excludes_nan_and_high_hand_from_denominator():
    hh = [-20.0, -10.0, NAN, -19.0, -25.0]
    hand = [5.0, 5.0, 5.0, 25.0, NAN]
    # valid: px0 (water, -20 < -18), px1 (not water); px2 NaN HH, px3 HAND 25, px4 NaN HAND
    # -> denominator 2, fraction 1/2
    frac, denom = fl.open_water_fraction(hh, hand, PARAMS)
    assert denom == 2
    assert frac == 0.5


def test_open_water_fraction_all_missing_is_nan_not_zero():
    frac, denom = fl.open_water_fraction([NAN, NAN], [5.0, 5.0], PARAMS)
    assert denom == 0
    assert math.isnan(frac)


# --- reference date and the no-baseline rule ------------------------------------------------


def test_gap_025_has_baseline():
    # (0.4 - 0.3) / 0.4 = 0.25 >= 0.20 -> baseline; driest date is the reference
    out = fl.pick_reference_date({"2026-10-20": 0.4, "2026-11-01": 0.3}, PARAMS)
    assert out["has_baseline"] is True
    assert out["reference_date"] == "2026-11-01"
    assert out["wettest_date"] == "2026-10-20"
    assert out["relative_gap"] == pytest.approx(0.25)


def test_gap_010_no_baseline():
    # (0.5 - 0.45) / 0.5 = 0.10 < 0.20 -> no baseline
    out = fl.pick_reference_date({"a": 0.5, "b": 0.45}, PARAMS)
    assert out["has_baseline"] is False
    assert out["reason"] == "no acceptable dry baseline"


def test_gap_exactly_020_counts_as_baseline():
    # (0.625 - 0.5) / 0.625 = 0.2 exactly in binary floating point
    assert fl.pick_reference_date({"a": 0.625, "b": 0.5}, PARAMS)["has_baseline"] is True
    # (0.5 - 0.4) / 0.5 is 0.2 on paper but 0.19999999999999996 in floats; still a baseline
    assert fl.pick_reference_date({"a": 0.5, "b": 0.4}, PARAMS)["has_baseline"] is True


def test_wettest_zero_means_no_baseline():
    out = fl.pick_reference_date({"a": 0.0, "b": 0.0}, PARAMS)
    assert out["has_baseline"] is False
    assert math.isnan(out["relative_gap"])


def test_nan_fraction_dates_are_skipped():
    # date c has no valid pixels; a/b give (0.4 - 0.3) / 0.4 = 0.25
    out = fl.pick_reference_date({"a": 0.4, "b": 0.3, "c": NAN}, PARAMS)
    assert out["reference_date"] == "b"
    assert out["has_baseline"] is True


# --- classes ---------------------------------------------------------------------------------

# px0: dHH -6 dB              -> Class 1 (-6 < -5.5)
# px1: dHH +4, d(HV/HH) 1 dB  -> Class 2 (4 > 3 and |1| < 1.5)
# px2: dHH +4, d(HV/HH) 2 dB  -> not Class 2 (|2| >= 1.5)
# px3: dHH -6, HAND 25 m      -> masked (25 >= 18)
# px4: dHH NaN                -> stays NaN
D_HH = [-6.0, 4.0, 4.0, -6.0, NAN]
D_RATIO = [0.0, 1.0, 2.0, 0.0, 0.0]
HAND = [5.0, 5.0, 5.0, 25.0, 5.0]


def test_classes_with_baseline():
    out = fl.classify(D_HH, D_RATIO, HAND, True, PARAMS)
    _same(out["class1"], [1.0, 0.0, 0.0, NAN, NAN])
    _same(out["class2"], [0.0, 1.0, 0.0, NAN, NAN])
    assert out["class2_reason"] is None
    assert out["calibrated"] is False
    assert set(out["uncalibrated"]) == set(fl.FLOOD_THRESHOLD_KEYS)


def test_no_baseline_class2_all_nan_and_class1_is_water_extent():
    hh = [-20.0, -10.0, NAN, -20.0]
    hand = [5.0, 5.0, 5.0, 25.0]
    # Class 1 = absolute water: -20 < -18 -> 1; -10 -> 0; NaN stays NaN; HAND 25 masked
    out = fl.classify(
        [-6.0, 4.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        hand,
        False,
        PARAMS,
        hh_db=hh,
        date="2026-11-10",
    )
    _same(out["class1"], [1.0, 0.0, NAN, NAN])
    assert np.isnan(out["class2"]).all()
    assert out["class2_reason"] == "no acceptable dry baseline"
    assert out["class1_label"] == "water extent on date 2026-11-10"


def test_no_baseline_requires_hh_db_and_date():
    with pytest.raises(ValueError):
        fl.classify(D_HH, D_RATIO, HAND, False, PARAMS)
    with pytest.raises(ValueError):
        fl.classify(D_HH, D_RATIO, HAND, False, PARAMS, hh_db=[-20.0] * 5)


def test_gap_just_below_threshold_is_no_baseline():
    # (1.0 - 0.8000000001) / 1.0 = 0.1999999999: a real shortfall, not float rounding
    assert fl.pick_reference_date({"a": 1.0, "b": 0.8000000001}, PARAMS)["has_baseline"] is False


def test_comparisons_are_strict_at_every_threshold():
    # px0: dHH = -5.5 exactly          -> not Class 1 (strict <)
    # px1: dHH = +3.0 exactly, ratio 0 -> not Class 2 (strict >)
    # px2: dHH = +4, |ratio| = 1.5     -> not Class 2 (strict <)
    # px3: dHH = +4, ratio = -1.0      -> Class 2 (|-1| < 1.5)
    # px4: HAND = 18 exactly           -> masked (strict <)
    d_hh = [-5.5, 3.0, 4.0, 4.0, -6.0]
    ratio = [0.0, 0.0, -1.5, -1.0, 0.0]
    hand = [5.0, 5.0, 5.0, 5.0, 18.0]
    out = fl.classify(d_hh, ratio, hand, True, PARAMS)
    _same(out["class1"], [0.0, 0.0, 0.0, 0.0, NAN])
    _same(out["class2"], [0.0, 0.0, 0.0, 1.0, NAN])


def test_missing_ratio_only_blanks_class2():
    # dHH -6 is valid -> Class 1 = 1; the NaN ratio leaves Class 2 missing, not 0
    out = fl.classify([-6.0], [NAN], [5.0], True, PARAMS)
    _same(out["class1"], [1.0])
    _same(out["class2"], [NAN])


def test_open_water_fraction_excludes_infinite_values():
    # +inf HH and -inf HAND are not valid pixels: denominator 1 (px0), water 1 -> 1.0
    frac, denom = fl.open_water_fraction([-20.0, np.inf, -20.0], [5.0, 5.0, -np.inf], PARAMS)
    assert (frac, denom) == (1.0, 1)


def test_changing_params_changes_result():
    stricter = {**PARAMS, "class1_delta_hh_db_max": -7.0}  # -6 is no longer < -7
    _same(fl.classify(D_HH, D_RATIO, HAND, True, stricter)["class1"], [0.0, 0.0, 0.0, NAN, NAN])
    wider_hand = {**PARAMS, "hand_max_m": 30}  # px3 (HAND 25) now inside: -6 < -5.5 -> 1
    _same(fl.classify(D_HH, D_RATIO, HAND, True, wider_hand)["class1"], [1.0, 0.0, 0.0, 1.0, NAN])
    wider_ratio = {**PARAMS, "class2_delta_hv_hh_db_abs_max": 2.5}  # px2 |2| < 2.5 -> Class 2
    _same(fl.classify(D_HH, D_RATIO, HAND, True, wider_ratio)["class2"], [0.0, 1.0, 1.0, NAN, NAN])
    # gap 0.25 is a baseline at 0.20 but not at 0.30
    assert not fl.pick_reference_date(
        {"a": 0.4, "b": 0.3}, {**PARAMS, "no_baseline_relative_gap": 0.3}
    )["has_baseline"]


def test_missing_param_raises():
    params = {k: v for k, v in PARAMS.items() if k != "hand_max_m"}
    with pytest.raises(KeyError, match="hand_max_m"):
        fl.classify(D_HH, D_RATIO, HAND, True, params)


def test_load_params_reads_preregistered_flood_section():
    params = fl.load_params("flood")
    for key in [*fl.FLOOD_THRESHOLD_KEYS, "no_baseline_relative_gap"]:
        assert key in params


def test_module_has_no_literal_thresholds():
    src = Path(fl.__file__).read_text(encoding="utf-8")
    for literal in ["-18.0", "-5.5", "3.0", "1.5", "-14.5", "-16.0", "-15.5", "0.55", "18.0"]:
        assert literal not in src, literal
