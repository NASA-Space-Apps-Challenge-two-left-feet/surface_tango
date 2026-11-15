"""Shared real-fixture loading and evidence assertions; no data creation."""

import hashlib
import io
import json
import re
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def fixture_paths(aoi, name):
    """Return paths restricted to the fixture directory."""
    for component in (aoi, name):
        if (
            not component
            or component in {".", ".."}
            or re.fullmatch(r"[A-Za-z0-9_-]+", component) is None
        ):
            raise ValueError("invalid fixture name or AOI")
    archive = ROOT / "tests" / "fixtures" / aoi / f"{name}.npz"
    return archive, archive.with_suffix(".provenance.json")


def load_fixture(aoi, name):
    """Return arrays and provenance, refusing an archive with a mismatched digest."""
    archive, sidecar = fixture_paths(aoi, name)
    provenance = json.loads(sidecar.read_text(encoding="utf-8"))
    payload = archive.read_bytes()
    if hashlib.sha256(payload).hexdigest() != provenance["sha256"]:
        raise ValueError(f"fixture sha256 mismatch: {archive}")
    with np.load(io.BytesIO(payload), allow_pickle=False) as data:
        arrays = {key: data[key] for key in data.files}
    if set(arrays) != set(provenance["variables"]):
        raise ValueError("fixture variables do not match sidecar")
    return arrays, provenance


def require_fixture(aoi, name):
    """Skip unavailable real data, but fail on corrupt evidence."""
    archive, sidecar = fixture_paths(aoi, name)
    if not (ROOT / "local_cache").is_dir() or not archive.is_file() or not sidecar.is_file():
        pytest.skip("fixture not cut: run scripts/cut_fixtures.py ...")
    return load_fixture(aoi, name)


def assert_provenance(arrays, provenance):
    """Require recorded source identifiers for every available variable."""
    assert provenance["source_cube"].startswith("local_cache/")
    assert provenance["git_commit"]
    assert provenance["cut_time_utc"]
    for name, array in arrays.items():
        assert np.issubdtype(array.dtype, np.floating), name
        assert "fill_value" in provenance["variable_metadata"][name], name
        source = provenance["variable_provenance"][name]
        if source == "missing":
            assert np.isnan(array).all(), name
            continue
        identifiers = [source] if isinstance(source, str) else source
        assert isinstance(identifiers, list) and len(identifiers) >= 1, name
        assert all(isinstance(item, str) and item.strip() for item in identifiers), name
        assert source in provenance["nisar_provenance"].values(), name


def require_variables(arrays, names):
    """Skip pending real cube inputs without substituting other bands."""
    missing = set(names) - arrays.keys()
    if missing:
        pytest.skip(f"real rule inputs absent from fixture: {', '.join(sorted(missing))}")
