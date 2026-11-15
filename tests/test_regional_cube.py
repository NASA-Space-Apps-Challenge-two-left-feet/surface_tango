"""Regional cube routing boundaries and real-cache round-trip verification."""

import pytest
from fastapi.testclient import TestClient

import app as web


def test_failed_build_does_not_publish_a_partial_store(monkeypatch, tmp_path):
    from scripts import build_regional_cube as builder

    def fail(cache, aoi, target):
        target.mkdir()
        raise RuntimeError("interrupted source read")

    monkeypatch.setattr(builder, "_build", fail)
    with pytest.raises(RuntimeError, match="interrupted"):
        builder.build(tmp_path, "mojana")
    assert not (tmp_path / "regional-cubes/mojana.zarr").exists()
    assert list((tmp_path / "regional-cubes").iterdir()) == []


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
def test_native_pixel_inspector_and_outside_coverage():
    import numpy as np
    import rasterio
    import xarray as xr

    store, meta = web.cube_layer("aburra", "los_disp_mm")
    with xr.open_zarr(store, group="los_disp_mm", consolidated=False, chunks=None) as ds:
        ys, xs = np.where(np.isfinite(ds.value.values))
        row, col = int(ys[0]), int(xs[0])
        expected = float(ds.value.values[row, col])
        lon, lat = rasterio.warp.transform(
            meta["crs"], "EPSG:4326", [float(ds.x.values[col])], [float(ds.y.values[row])]
        )
    with TestClient(web.app) as client:
        sample = client.get(
            "/api/cube/aburra/los_disp_mm/sample", params={"lon": lon[0], "lat": lat[0]}
        )
        assert sample.status_code == 200
        assert sample.json()["value"] == expected
        assert sample.json()["units"] == "mm"
        outside = client.get("/api/cube/aburra/los_disp_mm/sample?lon=0&lat=0")
        assert outside.json()["value"] is None
        assert client.get("/api/cube/aburra/los_disp_mm/sample?lon=999&lat=0").status_code == 422


@pytest.mark.cache
def test_scientific_legends_preserve_zero_and_nodata():
    import numpy as np

    _, metadata = web.cube_layer("aburra", "los_disp_mm")
    display = web.cube_display(metadata)
    assert display["minimum"] == -display["maximum"]
    # Use actual cached pixels; no generated science fixture.
    import xarray as xr

    store, _ = web.cube_layer("aburra", "los_disp_mm")
    with xr.open_zarr(store, group="los_disp_mm", consolidated=False, chunks=None) as ds:
        values = ds.value.values
    rgba = web.cube_colors(values, metadata)
    np.testing.assert_array_equal(rgba[3] > 0, np.isfinite(values))


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
