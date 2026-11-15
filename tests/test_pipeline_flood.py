"""Offline flood invariants on real La Mojana observations only."""

import numpy as np
import pytest
from pipeline_fixtures import ROOT, assert_provenance, require_fixture, require_variables

from gee_math import flood_polarimetric_math as flood


def _inputs(names):
    arrays, provenance = require_fixture("mojana", "flood")
    assert_provenance(arrays, provenance)
    require_variables(arrays, names)
    assert len({arrays[name].shape for name in names}) == 1
    thresholds = flood.load_flood_thresholds(ROOT / "config" / "preregistered.yaml")
    return arrays, provenance, thresholds


def _db(power):
    result = flood.power_to_db(power)
    valid = np.isfinite(power) & (power > 0)
    assert result.shape == power.shape
    assert np.array_equal(np.isfinite(result), valid)
    assert np.isnan(result[~valid]).all()
    return result


@pytest.mark.cache
def test_flood_fixture_provenance_and_sha():
    arrays, provenance = require_fixture("mojana", "flood")
    assert_provenance(arrays, provenance)
    assert provenance["source_cube"].startswith("local_cache/mojana/")


@pytest.mark.cache
def test_flood_absolute_water_excludes_missing():
    arrays, _, thresholds = _inputs(["gcov_hhhh_post", "hand_m"])
    hh = _db(arrays["gcov_hhhh_post"])
    hand = arrays["hand_m"]
    valid = np.isfinite(hh) & np.isfinite(hand) & (hand < thresholds.hand_max_m)
    n_water, n_valid = flood.absolute_water_counts(hh, hand, thresholds)
    raster = flood.water_raster(hh, hand, thresholds)
    assert 0 <= n_water <= n_valid <= hh.size
    assert n_valid == np.count_nonzero(valid)
    assert raster.shape == hh.shape
    assert np.isin(raster, (flood.CLASS_NODATA, 0, 1)).all()
    assert np.array_equal(raster == flood.CLASS_NODATA, ~valid)
    assert n_water == np.count_nonzero(raster == 1)


@pytest.mark.cache
def test_flood_change_classes_exclude_missing():
    names = ["gcov_hhhh_post", "gcov_hvhv_post", "gcov_hhhh_pre", "gcov_hvhv_pre", "hand_m"]
    arrays, _, thresholds = _inputs(names)
    hh, hv, hh_ref, hv_ref = (_db(arrays[name]) for name in names[:-1])
    hand = arrays["hand_m"]
    args = (hh, hv, hh_ref, hv_ref, hand, thresholds)
    class1, class2, valid1, valid2 = flood.class_masks(*args)
    hand_ok = np.isfinite(hand) & (hand < thresholds.hand_max_m)
    expected1 = hand_ok & np.isfinite(hh) & np.isfinite(hh_ref)
    expected2 = expected1 & np.isfinite(hv) & np.isfinite(hv_ref)
    assert np.array_equal(valid1, expected1)
    assert np.array_equal(valid2, expected2)
    for mask, valid in ((class1, valid1), (class2, valid2)):
        assert mask.shape == valid.shape == hand.shape
        assert mask.dtype == valid.dtype == np.dtype(bool)
        assert not mask[~valid].any()
    counts = flood.change_class_counts(*args)
    assert 0 <= counts.n_class1 <= counts.n_valid_class1 <= hh.size
    assert 0 <= counts.n_class2 <= counts.n_valid_class2 <= counts.n_valid_class1
    assert counts.n_valid_class1 == np.count_nonzero(valid1)
    assert counts.n_valid_class2 == np.count_nonzero(valid2)
    assert counts.n_class1 == np.count_nonzero(class1)
    assert counts.n_class2 == np.count_nonzero(class2)
    raster = flood.class_raster_from_db(*args)
    assert raster.shape == hand.shape
    assert np.isin(raster, (flood.CLASS_NODATA, 0, 1, 2)).all()
    assert np.array_equal(raster == flood.CLASS_NODATA, ~valid1)
    assert not (raster[~valid2] == 2).any()
    assert np.array_equal(raster == 1, class1)
    assert np.array_equal(raster == 2, class2 & ~class1)


@pytest.mark.cache
def test_flood_single_observation_has_no_baseline_or_class2():
    names = ["gcov_hhhh_post", "gcov_hvhv_post", "hand_m"]
    arrays, provenance, thresholds = _inputs(names)
    source = provenance["variable_provenance"]["gcov_hhhh_post"]
    identifiers = (source,) if isinstance(source, str) else tuple(source)
    # This label identifies the observation; it is not an invented acquisition date.
    cube = flood.DateCube(
        str(source), identifiers, arrays["gcov_hhhh_post"], arrays["gcov_hvhv_post"]
    )
    analysis = flood.classify_stack(
        [cube], arrays["hand_m"], thresholds, pixel_area_m2=flood.ANALYSIS_CELL_M**2
    )
    assert not analysis.baseline.accepted
    assert analysis.baseline.reference_date is None
    assert len(analysis.dates) == 1
    result = analysis.dates[0]
    assert result.n_class1 is result.n_valid_class1 is None
    assert result.n_class2 is result.n_valid_class2 is None
    assert result.class_raster is None
    hh = _db(cube.hh_linear)
    assert (result.n_water, result.n_valid) == flood.absolute_water_counts(
        hh, arrays["hand_m"], thresholds
    )
    assert 0 <= result.n_water <= result.n_valid <= hh.size
    assert np.array_equal(result.water_raster, flood.water_raster(hh, arrays["hand_m"], thresholds))
    for scenario in result.sensitivity:
        assert 0 <= scenario.n_water <= scenario.n_valid_water <= hh.size
        assert scenario.n_class1 is scenario.n_valid_class1 is None
        assert scenario.n_class2 is scenario.n_valid_class2 is None
