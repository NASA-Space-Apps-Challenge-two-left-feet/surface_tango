"""Edge cases for the La Mojana flood classes: missing data, empty inputs, sensitivity.

Arrays here are hand-written known-answer inputs (2 to 4 cells). Every value is
placed relative to the thresholds that load_flood_thresholds() reads from
config/preregistered.yaml, so no threshold number appears in this file. Expected
counts and codes are hand-computed from the module's documented rules. These
arrays never enter the cache, a report or the app.
"""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from gee_math.flood_polarimetric_math import (
    CLASS_NODATA,
    FloodThresholds,
    absolute_water_counts,
    change_class_counts,
    class_masks,
    class_raster_from_db,
    iter_sensitivity,
    load_flood_thresholds,
    mosaic_linear,
    power_to_db,
    water_raster,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "preregistered.yaml"
NAN = np.nan


@pytest.fixture
def thr() -> FloodThresholds:
    return load_flood_thresholds(CONFIG)


def _inside(thr: FloodThresholds, n: int) -> np.ndarray:
    """HAND values strictly inside the gate."""
    return np.full(n, thr.hand_max_m - 1.0)


# --- absolute open water: NaN windows, HAND gate, empty AOI -------------------


def test_all_nan_hh_window_has_no_valid_and_no_water(thr):
    hh = np.full((2, 2), NAN)
    hand = np.full((2, 2), thr.hand_max_m - 1.0)
    assert absolute_water_counts(hh, hand, thr) == (0, 0)
    assert (water_raster(hh, hand, thr) == CLASS_NODATA).all()


def test_mixed_nan_hh_and_hand_count_as_missing_not_dry(thr):
    dark = thr.open_water_abs_hh_db - 1.0
    bright = thr.open_water_abs_hh_db + 1.0
    inside = thr.hand_max_m - 1.0
    # cell 0: water; cell 1: dry; cell 2: HH missing; cell 3: HAND missing.
    hh = np.array([dark, bright, NAN, dark])
    hand = np.array([inside, inside, inside, NAN])
    assert absolute_water_counts(hh, hand, thr) == (1, 2)
    assert list(water_raster(hh, hand, thr)) == [1, 0, CLASS_NODATA, CLASS_NODATA]


@pytest.mark.parametrize("label", ["all_nan", "all_above_gate", "all_at_gate"])
def test_hand_without_eligible_pixels_reports_no_water(thr, label):
    hh = np.full(3, thr.open_water_abs_hh_db - 1.0)  # would be water if eligible
    hand = {
        "all_nan": np.full(3, NAN),
        "all_above_gate": np.full(3, thr.hand_max_m + 1.0),
        "all_at_gate": np.full(3, thr.hand_max_m),  # gate is strict: HAND < hand_max_m
    }[label]
    assert absolute_water_counts(hh, hand, thr) == (0, 0)
    assert (water_raster(hh, hand, thr) == CLASS_NODATA).all()
    counts = change_class_counts(hh, hh, hh - 10.0, hh - 10.0, hand, thr)
    assert (counts.n_valid_class1, counts.n_valid_class2) == (0, 0)
    assert (counts.n_class1, counts.n_class2) == (0, 0)


def test_empty_aoi_gives_zero_over_zero_and_empty_rasters(thr):
    empty = np.empty((0, 0))
    assert absolute_water_counts(empty, empty, thr) == (0, 0)
    assert water_raster(empty, empty, thr).shape == (0, 0)
    counts = change_class_counts(empty, empty, empty, empty, empty, thr)
    assert (counts.n_class1, counts.n_valid_class1) == (0, 0)
    assert (counts.n_class2, counts.n_valid_class2) == (0, 0)
    assert class_raster_from_db(empty, empty, empty, empty, empty, thr).shape == (0, 0)


# --- change classes: missing HV, missing reference ----------------------------


def test_missing_hv_keeps_class1_and_leaves_class2_unevaluated(thr):
    ref = np.zeros(2)
    hand = _inside(thr, 2)
    # cell 0: HH drop past the class-1 cut; cell 1: HH rise past the class-2 cut.
    hh = np.array([thr.class1_delta_hh_db_max - 1.0, thr.class2_delta_hh_db_min + 1.0])
    hv_missing = np.full(2, NAN)
    class1, class2, valid1, valid2 = class_masks(hh, hv_missing, ref, ref, hand, thr)
    assert list(class1) == [True, False]
    assert list(valid1) == [True, True]
    # Class 2 needs a finite HV/HH ratio on both dates: never evaluated, never detected.
    assert list(valid2) == [False, False]
    assert list(class2) == [False, False]
    counts = change_class_counts(hh, hv_missing, ref, ref, hand, thr)
    assert (counts.n_class1, counts.n_valid_class1) == (1, 2)
    assert (counts.n_class2, counts.n_valid_class2) == (0, 0)


def test_missing_hv_on_reference_date_only_also_blocks_class2(thr):
    hh = np.array([thr.class2_delta_hh_db_min + 1.0])
    hv = hh.copy()  # ratio change of 0 dB would satisfy the ratio test
    ref = np.zeros(1)
    counts = change_class_counts(hh, hv, ref, np.array([NAN]), _inside(thr, 1), thr)
    assert (counts.n_class2, counts.n_valid_class2) == (0, 0)
    assert counts.n_valid_class1 == 1


def test_missing_reference_hh_makes_both_classes_missing(thr):
    hh = np.array([thr.class1_delta_hh_db_max - 1.0])
    ref_hh = np.array([NAN])
    ref_hv = np.zeros(1)
    counts = change_class_counts(hh, hh, ref_hh, ref_hv, _inside(thr, 1), thr)
    assert (counts.n_class1, counts.n_valid_class1) == (0, 0)
    assert (counts.n_class2, counts.n_valid_class2) == (0, 0)
    raster = class_raster_from_db(hh, hh, ref_hh, ref_hv, _inside(thr, 1), thr)
    assert list(raster) == [CLASS_NODATA]


def test_class_raster_codes_for_missing_hand_and_missing_hh(thr):
    ref = np.zeros(4)
    c1 = thr.class1_delta_hh_db_max - 1.0
    c2 = thr.class2_delta_hh_db_min + 1.0
    hh = np.array([c1, c2, c1, NAN])
    hv = hh.copy()  # zero ratio change, inside the class-2 ratio window
    hand = np.array([thr.hand_max_m - 1.0, thr.hand_max_m - 1.0, NAN, thr.hand_max_m - 1.0])
    raster = class_raster_from_db(hh, hv, ref, ref, hand, thr)
    assert list(raster) == [1, 2, CLASS_NODATA, CLASS_NODATA]


def test_missing_hv_pixel_without_class1_is_coded_zero_in_the_raster(thr):
    """Documents current behaviour: the raster has no "class 2 not evaluated" code.

    A pixel with valid ΔHH, no class-1 drop and missing HV is written as 0
    ("neither class") although class 2 was never evaluated. The counts keep it
    out of the class-2 denominator (n_valid_class2), so the hectares are honest;
    a display that reads the raster alone cannot tell "no flood" from "class 2
    unknown" (see briefs/proposal-mcp-evidence-fields.md on Class 2 support).
    """
    hh = np.array([thr.class2_delta_hh_db_min + 1.0])
    ref = np.zeros(1)
    raster = class_raster_from_db(hh, np.array([NAN]), ref, ref, _inside(thr, 1), thr)
    assert list(raster) == [0]
    counts = change_class_counts(hh, np.array([NAN]), ref, ref, _inside(thr, 1), thr)
    assert counts.n_valid_class2 == 0


# --- sensitivity scenarios come from config -----------------------------------


def test_iter_sensitivity_covers_every_configured_cut(thr):
    scenarios = dict(iter_sensitivity(thr))
    fields = (
        "open_water_abs_hh_db",
        "class1_delta_hh_db_max",
        "class2_delta_hh_db_min",
        "class2_delta_hv_hh_db_abs_max",
    )
    expected = {"nominal"}
    expected |= {f"{f}_{side}" for f in fields for side in ("minus", "plus")}
    expected |= {f"hand_{h:g}" for h in thr.hand_sensitivity_m if h != thr.hand_max_m}
    assert set(scenarios) == expected
    assert scenarios["nominal"] == thr
    for field in fields:
        base = getattr(thr, field)
        assert getattr(scenarios[f"{field}_minus"], field) == base - thr.db_step
        assert getattr(scenarios[f"{field}_plus"], field) == base + thr.db_step
        # Only the named cut moves.
        assert replace(scenarios[f"{field}_plus"], **{field: base}) == thr
    for hand in thr.hand_sensitivity_m:
        if hand != thr.hand_max_m:
            assert scenarios[f"hand_{hand:g}"].hand_max_m == hand


def test_hand_sensitivity_value_changes_the_denominator(thr):
    others = [h for h in thr.hand_sensitivity_m if h != thr.hand_max_m]
    if not others:
        pytest.skip("config lists no HAND sensitivity value besides the nominal gate")
    wider = max(others)
    if wider <= thr.hand_max_m:
        pytest.skip("config lists no HAND sensitivity value above the nominal gate")
    hh = np.full(2, thr.open_water_abs_hh_db - 1.0)
    # cell 0 inside both gates; cell 1 between the nominal gate and the wider one.
    hand = np.array([thr.hand_max_m - 1.0, (thr.hand_max_m + wider) / 2.0])
    scenarios = dict(iter_sensitivity(thr))
    assert absolute_water_counts(hh, hand, thr) == (1, 1)
    assert absolute_water_counts(hh, hand, scenarios[f"hand_{wider:g}"]) == (2, 2)


# --- linear power helpers never zero-fill -------------------------------------


def test_mosaic_of_all_nan_layers_stays_nan():
    layer = np.full((2, 2), NAN)
    out = mosaic_linear([layer, layer.copy()])
    assert out.shape == (2, 2)
    assert np.isnan(out).all()


def test_mosaic_rejects_no_layers_and_mismatched_shapes():
    with pytest.raises(ValueError, match="no layers"):
        mosaic_linear([])
    with pytest.raises(ValueError, match="share a shape"):
        mosaic_linear([np.ones((2, 2)), np.ones((2, 3))])


def test_power_to_db_keeps_zero_negative_and_infinite_power_missing():
    out = power_to_db(np.array([0.0, -1.0, np.inf, NAN, 10.0]))
    assert np.isnan(out[:4]).all()
    assert out[4] == pytest.approx(10.0)
