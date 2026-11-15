"""Offline quake invariants on real observations; never substitute missing layers."""

import numpy as np
import pytest
from pipeline_fixtures import assert_provenance, require_fixture, require_variables

from gee_math import earthquake_dpm_math as quake


def _inputs():
    arrays, provenance = require_fixture("eje_cafetero", "quake")
    assert_provenance(arrays, provenance)
    require_variables(arrays, ["coherence_R", "coherence_C"])
    ref, cmp = arrays["coherence_R"], arrays["coherence_C"]
    assert ref.shape == cmp.shape
    for coherence in (ref, cmp):
        assert (np.isnan(coherence) | ((coherence >= 0) & (coherence <= 1))).all()
    return arrays, quake.delta_gamma(ref, cmp)


@pytest.mark.cache
def test_quake_fixture_provenance_and_sha():
    arrays, provenance = require_fixture("eje_cafetero", "quake")
    assert_provenance(arrays, provenance)


@pytest.mark.cache
def test_quake_coherence_loss_preserves_missing():
    arrays, delta = _inputs()
    missing = np.isnan(arrays["coherence_R"]) | np.isnan(arrays["coherence_C"])
    assert delta.shape == arrays["coherence_R"].shape
    assert np.array_equal(np.isnan(delta), missing)
    assert (np.isnan(delta) | ((delta >= -1) & (delta <= 1))).all()


@pytest.mark.cache
def test_quake_standardization_and_dpm_domains():
    arrays, delta = _inputs()
    require_variables(arrays, ["footprint_coverage", "landcover", "gunw_mask"])
    assert all(array.shape == delta.shape for array in arrays.values())
    params = quake.load_quake_prereg()
    coverage = arrays["footprint_coverage"]
    assert (np.isnan(coverage) | ((coverage >= 0) & (coverage <= 1))).all()
    built, non_built = quake.classify_coverage(
        coverage,
        params["built_up_min_footprint_fraction"],
        params["non_built_max_footprint_fraction"],
    )
    assert not (built & non_built).any()
    assert not (built | non_built)[np.isnan(coverage)].any()
    gunw_valid, gunw_water = quake.gunw_mask_flags(arrays["gunw_mask"])
    landcover = arrays["landcover"]
    vegetation = np.isin(landcover, quake.WORLDCOVER_VEGETATION_CLASSES)
    water = (landcover == quake.WORLDCOVER_WATER_CLASS) | gunw_water
    valid = quake.valid_pixels(delta, vegetation, water, gunw_valid)
    # Missing ancillary observations cannot establish a reference pixel.
    valid &= np.isfinite(landcover) & np.isfinite(arrays["gunw_mask"])
    assert not valid[np.isnan(delta)].any()
    z, _, _, _ = quake.standardize(delta, valid & non_built)
    dpm = quake.dpm_from_z(z)
    assert z.shape == dpm.shape == delta.shape
    assert np.isnan(z[np.isnan(delta)]).all()
    assert np.array_equal(np.isnan(dpm), np.isnan(z))
    assert (np.isnan(z) | np.isfinite(z)).all()
    assert (np.isnan(dpm) | (np.isfinite(dpm) & (dpm >= 0))).all()
