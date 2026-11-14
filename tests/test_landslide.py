"""Allow-listed pure-logic known-answer tests using hand-written arrays only."""

from copy import deepcopy

import numpy as np
import pytest

from gee_math.landslide_insar_math import hklsi, noise_floor_verdict, project_los_to_downslope

PARAMS = {
    "coherence_min": 0.35,
    "stable_slope_max_deg": 8.0,
    "min_slope_deg": 15.0,
    "cos_xi_floor": 0.25,
    "noise_floor": {"min_pairs": 2, "require_sign_agreement": True},
    "hklsi": {
        "weights": {"velocity": 0.5, "slope": 0.25, "rain": 0.25},
        "velocity_norm_mm_yr": 120.0,
        "slope_offset_deg": 15.0,
        "slope_norm_deg": 30.0,
        "rain_norm_mm": 200.0,
    },
    "incidence_deg": 90.0,
    "heading_deg": 0.0,
}


def test_same_sign_pairs_keep_hand_computed_mean():
    # RMS floors are sqrt((9 + 9)/2) = 3 and sqrt((16 + 16)/2) = 4.
    # Both rates exceed their floor; mean = (6 + 8)/2 = 7 mm/yr.
    result = noise_floor_verdict([[6.0], [8.0]], [[3.0, -3.0], [4.0, -4.0]], PARAMS)
    np.testing.assert_array_equal(result["kept_mask"], [True])
    np.testing.assert_array_equal(result["kept_rate"], [7.0])
    assert result["per_pair_noise_floor_mm_yr"] == [3.0, 4.0]
    assert result["noise_floor_mm_yr"] == 4.0
    assert result["n_pairs"] == 2
    assert result["verdict"] == "motion detected"
    assert result["text"] == "motion above 4.0 mm noise floor in 1 pixels (2 pairs)"


def test_opposite_sign_pairs_are_null():
    # Each RMS is 3; opposite signs veto rates with magnitudes 6 and 8.
    result = noise_floor_verdict([[6.0], [-8.0]], [[3.0, -3.0], [3.0]], PARAMS)
    assert not result["kept_mask"].any()
    assert np.isnan(result["kept_rate"]).all()
    assert result["verdict"] == "null"
    assert result["text"] == "no motion detected above 3.0 mm noise floor (2 pairs)"


def test_one_pair_is_null():
    # RMS = 3, but one independent pair is fewer than the required two.
    result = noise_floor_verdict([[6.0]], [[3.0, -3.0]], PARAMS)
    assert result["verdict"] == "null"
    assert np.isnan(result["kept_rate"]).all()
    assert result["text"] == "no motion detected above 3.0 mm noise floor (1 pairs)"


def test_rate_equal_to_rms_is_not_kept():
    # RMS = sqrt((9 + 9)/2) = 3 exactly; equality fails the strict comparison.
    result = noise_floor_verdict([[3.0], [6.0]], [[3.0, -3.0], [3.0]], PARAMS)
    assert not result["kept_mask"].any()


def test_nan_rate_remains_missing():
    # A missing rate vetoes its pixel even when the other rate exceeds RMS = 3.
    result = noise_floor_verdict([[np.nan, 6.0], [8.0, np.nan]], [[3.0], [3.0]], PARAMS)
    assert np.isnan(result["kept_rate"]).all()
    assert not result["kept_mask"].any()


def test_min_pairs_parameter_changes_verdict():
    params = deepcopy(PARAMS)
    params["noise_floor"]["min_pairs"] = 3
    # Two rates above RMS = 3 are insufficient when three pairs are required.
    assert noise_floor_verdict([[6.0], [8.0]], [[3.0], [3.0]], params)["verdict"] == "null"


def test_sign_agreement_parameter_changes_verdict():
    params = deepcopy(PARAMS)
    params["noise_floor"]["require_sign_agreement"] = False
    # Without the sign veto, (6 - 8)/2 = -1 mm/yr is retained.
    result = noise_floor_verdict([[6.0], [-8.0]], [[3.0], [3.0]], params)
    np.testing.assert_array_equal(result["kept_rate"], [-1.0])
    assert result["verdict"] == "motion detected"


def test_nan_residuals_are_ignored():
    # Ignoring missing residuals leaves RMS = sqrt(9) = 3 for each pair.
    result = noise_floor_verdict([[6.0], [8.0]], [[np.nan, 3.0], [-3.0, np.nan]], PARAMS)
    assert result["per_pair_noise_floor_mm_yr"] == [3.0, 3.0]
    np.testing.assert_array_equal(result["kept_rate"], [7.0])


@pytest.mark.parametrize("residuals", [[], [np.nan], [np.inf, -np.inf]])
def test_pair_without_finite_residuals_vetoes_all_pixels(residuals):
    result = noise_floor_verdict([[6.0], [8.0]], [[3.0], residuals], PARAMS)
    assert result["verdict"] == "null"
    assert not result["kept_mask"].any()
    assert np.isnan(result["kept_rate"]).all()
    assert np.isnan(result["noise_floor_mm_yr"])


def test_no_pairs_is_null():
    result = noise_floor_verdict([], [], PARAMS)
    assert result["n_pairs"] == 0
    assert result["verdict"] == "null"
    assert np.isnan(result["noise_floor_mm_yr"])
    assert result["per_pair_noise_floor_mm_yr"] == []


def test_projection_keeps_signed_quotient():
    # Incidence = 90, heading = 0, slope = 0, aspect = 270: cos_xi = +1.
    # Negative LOS / +1 = -6 mm; with aspect = 90, cos_xi = -1 and result = +6.
    result = project_los_to_downslope([-6.0, -6.0], [0.0, 0.0], [270.0, 90.0], PARAMS)
    np.testing.assert_allclose(result, [-6.0, 6.0])


def test_projection_cosine_floor_preserves_both_signs():
    # Flat north-facing slope is orthogonal: cosine zero uses +0.25.
    # Aspect = 180 gives a tiny negative cosine: use -0.25. -2 / (+/-0.25) = -/+8.
    result = project_los_to_downslope([-2.0, -2.0], [0.0, 0.0], [0.0, 180.0], PARAMS)
    np.testing.assert_allclose(result, [-8.0, 8.0])


def test_projection_uses_scene_geometry():
    params = deepcopy(PARAMS)
    params["heading_deg"] = 180.0
    # Reversing heading reverses the flat east-facing projection: -6 / +1 = -6.
    np.testing.assert_allclose(project_los_to_downslope([-6.0], [0.0], [90.0], params), [-6.0])


def test_hklsi_known_answer_and_weight_change():
    # |v|/120 = 1/2, (slope-15)/30 = 1/2, rain/200 = 1/2.
    # Score = .5*.5 + .25*.5 + .25*.5 = .5, for either velocity sign.
    np.testing.assert_allclose(
        hklsi([-60.0, 60.0], [30.0, 30.0], [100.0, 100.0], PARAMS), [0.5, 0.5]
    )
    params = deepcopy(PARAMS)
    params["hklsi"]["weights"]["velocity"] = 1.0
    # Changing the velocity weight adds .5*.5 = .25, yielding .75.
    np.testing.assert_allclose(hklsi([-60.0], [30.0], [100.0], params), [0.75])


def test_hklsi_missing_input_stays_missing():
    assert np.isnan(hklsi([np.nan], [30.0], [100.0], PARAMS)).all()


def test_missing_nested_parameter_names_full_key():
    params = deepcopy(PARAMS)
    del params["noise_floor"]["min_pairs"]
    with pytest.raises(KeyError, match=r"noise_floor\.min_pairs"):
        noise_floor_verdict([[6.0]], [[3.0]], params)


def test_projection_requires_scene_geometry():
    params = deepcopy(PARAMS)
    del params["incidence_deg"]
    with pytest.raises(KeyError, match="incidence_deg"):
        project_los_to_downslope([-6.0], [0.0], [270.0], params)
