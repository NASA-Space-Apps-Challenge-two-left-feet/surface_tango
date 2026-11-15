"""Independent-pair invariants; pending real layers are never substituted."""

import numpy as np
import pytest
from pipeline_fixtures import assert_provenance, require_fixture, require_variables

from gee_math import landslide_insar_math as landslide
from gee_math.flood_polarimetric_math import load_params


@pytest.mark.cache
def test_landslide_fixture_provenance():
    arrays, provenance = require_fixture("antioquia_aburra", "landslide")
    assert_provenance(arrays, provenance)


def _params():
    reason = "landslide keys not in config/preregistered.yaml yet"
    try:
        params = load_params("landslide")
        for dotted in landslide.LANDSLIDE_PARAM_KEYS:
            value = params
            for key in dotted.split("."):
                value = value[key]
    except (KeyError, TypeError):
        pytest.skip(reason)
    return params


@pytest.mark.cache
def test_landslide_pair_missing_stays_missing():
    params = _params()
    arrays, provenance = require_fixture("antioquia_aburra", "landslide")
    assert_provenance(arrays, provenance)
    names = sorted(name for name in arrays if name.startswith("rate_mm_yr_pair_"))
    if not names:
        pytest.skip("real independent pair rates and stable residuals not cached yet")
    residual_names = [
        name.replace("rate_mm_yr_pair_", "stable_residual_mm_yr_pair_") for name in names
    ]
    require_variables(arrays, residual_names)
    rates = [arrays[name] for name in names]
    residuals = [arrays[name].ravel() for name in residual_names]
    result = landslide.noise_floor_verdict(rates, residuals, params)
    missing = np.isnan(np.stack(rates)).any(axis=0)
    assert result["kept_rate"].shape == rates[0].shape
    assert np.isnan(result["kept_rate"][missing]).all()
    assert not result["kept_mask"][missing].any()
