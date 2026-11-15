"""Evidence checks only until offline earthquake rules exist."""

import pytest
from pipeline_fixtures import assert_provenance, require_fixture


@pytest.mark.cache
def test_quake_fixture_provenance_and_sha():
    arrays, provenance = require_fixture("antioquia_aburra", "quake")
    assert_provenance(arrays, provenance)


@pytest.mark.cache
def test_quake_numpy_rules_pending():
    require_fixture("antioquia_aburra", "quake")
    pytest.skip("quake NumPy rules pending (03-02)")
