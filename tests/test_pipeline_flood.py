"""Invariant checks on real flood inputs only."""

import numpy as np
import pytest
from pipeline_fixtures import assert_provenance, require_fixture, require_variables

from gee_math import flood_polarimetric_math as flood


@pytest.mark.cache
def test_flood_fixture_provenance():
    arrays, provenance = require_fixture("antioquia_aburra", "flood")
    assert_provenance(arrays, provenance)


def _inputs():
    arrays, provenance = require_fixture("antioquia_aburra", "flood")
    assert_provenance(arrays, provenance)
    require_variables(arrays, ["hh_db", "delta_hh_db", "delta_hv_hh_db", "hand_m"])
    assert len({array.shape for array in arrays.values()}) == 1
    return arrays, flood.load_params("flood"), provenance


@pytest.mark.cache
def test_flood_class_masks_preserve_missing():
    arrays, params, _ = _inputs()
    result = flood.classify(
        arrays["delta_hh_db"], arrays["delta_hv_hh_db"], arrays["hand_m"], True, params
    )
    assert result["calibrated"] is False
    missing = np.isnan(arrays["delta_hh_db"]) | np.isnan(arrays["hand_m"])
    assert np.isnan(result["class1"][missing]).all()
    assert np.isnan(result["class2"][missing | np.isnan(arrays["delta_hv_hh_db"])]).all()
    for key in ("class1", "class2"):
        assert result[key].shape == arrays["hand_m"].shape
        assert (np.isnan(result[key]) | np.isin(result[key], (0.0, 1.0))).all()


@pytest.mark.cache
def test_flood_fraction_denominator_excludes_missing():
    arrays, params, _ = _inputs()
    hh, hand = arrays["hh_db"], arrays["hand_m"]
    fraction, denominator = flood.open_water_fraction(hh, hand, params)
    valid = np.isfinite(hh) & np.isfinite(hand) & (hand < params["hand_max_m"])
    assert denominator >= 0
    assert denominator == np.count_nonzero(valid)
    if denominator == 0:
        assert np.isnan(fraction)
    else:
        assert np.isfinite(fraction) and 0 <= fraction <= 1


@pytest.mark.cache
def test_flood_no_baseline_class2_is_missing():
    arrays, params, provenance = _inputs()
    result = flood.classify(
        arrays["delta_hh_db"],
        arrays["delta_hv_hh_db"],
        arrays["hand_m"],
        False,
        params,
        hh_db=arrays["hh_db"],
        date=str(provenance["variable_provenance"]["hh_db"]),
    )
    assert result["calibrated"] is False
    assert np.isnan(result["class2"]).all()
    missing = np.isnan(arrays["hh_db"]) | np.isnan(arrays["hand_m"])
    assert np.isnan(result["class1"][missing]).all()
    assert (np.isnan(result["class1"]) | np.isin(result["class1"], (0.0, 1.0))).all()
