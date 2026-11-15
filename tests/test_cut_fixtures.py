"""Known-answer serialization checks using only allowlisted temporary arrays."""

import hashlib
import json
from argparse import Namespace
from types import SimpleNamespace

import numpy as np
import pipeline_fixtures
import pytest
import xarray as xr
from pipeline_fixtures import load_fixture, require_fixture

from scripts import cut_fixtures


@pytest.fixture
def temporary_root(tmp_path, monkeypatch):
    """Isolate all cutter and loader I/O; Git metadata is a test label."""
    monkeypatch.setattr(cut_fixtures, "ROOT", tmp_path)
    monkeypatch.setattr(pipeline_fixtures, "ROOT", tmp_path)

    def git_head(command, **kwargs):
        assert command == ["git", "rev-parse", "HEAD"]
        assert kwargs == dict(cwd=tmp_path, check=True, capture_output=True, text=True)
        return SimpleNamespace(stdout="test-only-commit\n")

    monkeypatch.setattr(cut_fixtures.subprocess, "run", git_head)
    return tmp_path


def write_source(root, *, manifest=False, all_missing=False):
    """Write literal logic-test values; never use the real local cache."""
    aoi, name, variable = "mojana", "flood", "gcov_hhhh_pre"
    cube = root / "local_cache" / aoi / f"{aoi}_sar_cube.zarr"
    provenance = {variable: ["test-only-source"], "absent": "missing"}
    values = np.array([[1.0, -9999.0, 0.0], [-7777.0, np.nan, 4.0], [2.0, -8888.0, 8.0]])
    if all_missing:
        values[:] = np.nan
    dataset = xr.Dataset(
        {
            variable: (("y", "x"), values),
            "absent": (("y", "x"), np.array([[np.nan] * 3] * 3)),
        }
    )
    dataset[variable].attrs.update(missing_value=-7777.0, nodata=-8888.0)
    if not manifest:
        dataset.attrs["nisar_provenance"] = json.dumps(provenance)
    dataset.to_zarr(cube, zarr_format=2, encoding={variable: {"_FillValue": -9999.0}})
    if manifest:
        (cube.parent / "manifest.json").write_text(
            json.dumps({"nisar_granule_provenance": provenance}), encoding="utf-8"
        )
    args = Namespace(aoi=aoi, name=name, row=0, col=0, size=3, vars=[variable, "absent"])
    return args, cube, provenance


@pytest.mark.parametrize("manifest", [False, True])
def test_cut_round_trip_preserves_evidence(temporary_root, manifest):
    args, cube, provenance = write_source(temporary_root, manifest=manifest)
    cut_fixtures.cut_fixture(args)
    # The exact documented AOI/name is discoverable by the pipeline loader.
    arrays, sidecar = require_fixture(args.aoi, args.name)
    variable = args.vars[0]
    expected = [[1.0, np.nan, 0.0], [np.nan, np.nan, 4.0], [2.0, np.nan, 8.0]]
    np.testing.assert_array_equal(arrays[variable], expected)
    assert np.isnan(arrays["absent"]).all()
    assert sidecar["nisar_provenance"] == provenance
    assert sidecar["variable_provenance"] == provenance
    assert sidecar["source_cube"] == cube.relative_to(temporary_root).as_posix()
    assert sidecar["window"] == {"row": 0, "col": 0, "size": 3}
    assert sidecar["git_commit"] == "test-only-commit"
    assert sidecar["cut_time_utc"].endswith("+00:00")
    assert sidecar["variable_metadata"][variable]["fill_value"] == [-9999.0, -7777.0, -8888.0]
    if manifest:
        assert sidecar["nisar_provenance_attribute"] is None
        assert (
            sidecar["provenance_source"]
            == (cube.parent / "manifest.json").relative_to(temporary_root).as_posix()
        )
    else:
        assert sidecar["nisar_provenance_attribute"] == json.dumps(provenance)
        assert sidecar["provenance_source"] == "cube:nisar_provenance"
    archive, _ = pipeline_fixtures.fixture_paths(args.aoi, args.name)
    assert sidecar["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.write_bytes(archive.read_bytes() + b"test-only-corruption")
    with pytest.raises(ValueError, match="sha256 mismatch"):
        load_fixture(args.aoi, args.name)


def test_all_nan_window_is_refused(temporary_root):
    args, _, _ = write_source(temporary_root, all_missing=True)
    with pytest.raises(ValueError, match="entirely NaN"):
        cut_fixtures.cut_fixture(args)
    assert not (temporary_root / "tests").exists()


@pytest.mark.parametrize(
    "attribute,value", [("row", -1), ("col", -1), ("size", 0), ("row", 1), ("col", 1)]
)
def test_invalid_window_is_refused(temporary_root, attribute, value):
    args, _, _ = write_source(temporary_root)
    setattr(args, attribute, value)
    with pytest.raises(ValueError, match="nonnegative|extends beyond"):
        cut_fixtures.cut_fixture(args)
    assert not (temporary_root / "tests").exists()


@pytest.mark.parametrize("existing", ["archive", "sidecar"])
def test_existing_evidence_is_never_overwritten(temporary_root, existing):
    args, _, _ = write_source(temporary_root)
    archive, sidecar = pipeline_fixtures.fixture_paths(args.aoi, args.name)
    target = archive if existing == "archive" else sidecar
    target.parent.mkdir(parents=True)
    target.write_bytes(b"test-only-existing-evidence")
    with pytest.raises(ValueError, match="already exists"):
        cut_fixtures.cut_fixture(args)
    assert target.read_bytes() == b"test-only-existing-evidence"
    assert not (sidecar if existing == "archive" else archive).exists()
