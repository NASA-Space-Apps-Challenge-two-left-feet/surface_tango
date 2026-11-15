"""Regional cube routing boundaries and real-cache round-trip verification."""

import pytest
from fastapi.testclient import TestClient

import app as web


def test_cube_missing_regions_are_explicit(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "CACHE_ROOT", tmp_path)
    with TestClient(web.app) as client:
        response = client.get("/api/cube")
        assert response.status_code == 200
        assert all(region["state"] == "not cached" for region in response.json()["regions"])
        assert client.get("/api/cube/unknown/layer/preview.png").status_code == 404
        assert client.get("/api/cube/mojana/absent/preview.png").status_code == 404
        assert client.get("/cube").status_code == 200


@pytest.mark.cache
def test_packaged_layers_preserve_source_pixels():
    import numpy as np
    import rasterio
    import xarray as xr

    catalog = web.cube_catalog()
    available = [r for r in catalog["regions"] if r["state"] == "cached"]
    assert available, "Package at least one regional cube before running cache tests"
    for region in available:
        layer = region["layers"][0]
        store, _ = web.cube_layer(region["aoi"], layer["id"])
        with rasterio.open(web.CACHE_ROOT / layer["source_file"]) as source:
            expected = source.read(1, masked=True).astype("float32").filled(np.nan)
        with xr.open_zarr(store, group=layer["id"], consolidated=False, chunks=None) as dataset:
            np.testing.assert_array_equal(dataset.value.values, expected)
        with TestClient(web.app) as client:
            result = client.get(f"/api/cube/{region['aoi']}/{layer['id']}/preview.png")
            assert result.status_code == 200
            assert result.content.startswith(b"\x89PNG")
