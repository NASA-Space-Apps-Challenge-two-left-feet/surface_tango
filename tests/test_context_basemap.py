"""The visor background is a same-origin Sentinel-2 context composite."""

from pathlib import Path

import numpy as np
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_bounds

from scripts.context_basemap_tiles import (
    composite_layers,
    frame_dimensions,
    pad_bbox,
    render_context_tile,
    sample_rgba,
    stretch_reflectance,
)
from src.bailasar.config import get_config

ROOT = Path(__file__).resolve().parents[1]
TILES = "/api/context-basemap/{z}/{x}/{y}.png"
CREDIT = "Sentinel-2 cloud-free median. Geographic context, not a measurement."


def test_context_style_keeps_a_dark_field_under_the_imagery():
    script = (ROOT / "static/context-basemap.js").read_text(encoding="utf-8")
    assert TILES in script
    assert "arcgisonline.com" not in script
    assert "{z}/{y}/{x}" not in script
    assert CREDIT in script
    assert "not a measurement" in script
    layers = script.split("layers:", 1)[1]
    assert layers.index('id: "background"') < layers.index('type: "raster"')


def test_curtain_uses_the_context_style_and_says_so():
    page = (ROOT / "static/index.html").read_text(encoding="utf-8")
    assert page.index("/static/context-basemap.js") < page.index("contextBasemapStyle")
    assert 'contextBasemapStyle("#0f172a")' in page
    assert "attributionControl: false" in page
    assert 'id="context-basemap-credit"' in page
    assert CREDIT in page
    assert "not a measurement" in page
    assert "Unobserved pixels stay dark" in page
    assert '"raster-opacity": 1' in page
    assert 'href="/cube"' not in page
    assert "arcgisonline.com" not in page


def test_context_settings_come_from_operational_config():
    spec = get_config().ops("context_basemap")
    assert spec["asset"] == "COPERNICUS/S2_SR_HARMONIZED"
    assert spec["cloud_score_band"] == "cs_cdf"
    assert spec["clear_min"] == 0.60
    assert set(spec["frames"]) == {
        "aburra",
        "eje_cafetero",
        "mojana",
        "choco_epicenter",
        "valle_del_cauca",
        "la_picacha",
    }


def test_stretch_leaves_a_masked_pixel_transparent():
    """DN 0 -> 0, DN 1000 -> 102, DN 2500 -> 255. A NaN stays alpha 0.

    1000 / 2500 * 255 = 102 exactly. The NaN pixel's RGB 0 is not a reflectance.
    """
    stack = np.array(
        [
            [[0.0, 1000.0], [np.nan, 2500.0]],
            [[0.0, 1000.0], [np.nan, 2500.0]],
            [[0.0, 1000.0], [np.nan, 2500.0]],
        ],
        dtype=np.float32,
    )
    rgba = stretch_reflectance(stack, 2500)
    assert tuple(rgba[:, 0, 0]) == (0, 0, 0, 255)
    assert tuple(rgba[:, 0, 1]) == (102, 102, 102, 255)
    assert tuple(rgba[:, 1, 0]) == (0, 0, 0, 0)
    assert tuple(rgba[:, 1, 1]) == (255, 255, 255, 255)


def test_finer_context_replaces_only_where_it_was_observed():
    coarse = np.zeros((1, 2, 4), dtype=np.uint8)
    coarse[0, 0] = (1, 1, 1, 255)
    fine = np.zeros((1, 2, 4), dtype=np.uint8)
    fine[0, 1] = (9, 9, 9, 255)
    painted = composite_layers([coarse, fine])
    assert tuple(painted[0, 0]) == (1, 1, 1, 255)
    assert tuple(painted[0, 1]) == (9, 9, 9, 255)


def test_pad_and_posting_are_hand_computed():
    assert pad_bbox([0.0, 0.0, 1.0, 1.0], 0.1) == [-0.1, -0.1, 1.1, 1.1]
    # 1 degree at the equator is 111320 m. Posting 111320 m is one pixel.
    # Mid-latitude 0.5 degree: width uses cos(0.5°) = 0.9999619230641713, which rounds to 1.
    assert frame_dimensions([0.0, 0.0, 1.0, 1.0], 111_320.0) == (1, 1)


def test_nearest_sample_keeps_a_transparent_pixel(tmp_path):
    rgba = np.zeros((4, 2, 2), dtype=np.uint8)
    rgba[:, 0, 0] = (10, 20, 30, 255)
    path = tmp_path / "frame.tif"
    transform = from_bounds(0.0, 0.0, 2.0, 2.0, 2, 2)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=4,
        dtype="uint8",
        crs="EPSG:4326",
        transform=transform,
    ) as dataset:
        dataset.write(rgba)
    # The tile transform matches the file, so nearest resampling copies the cells.
    sampled = sample_rgba(path, transform, 2, dst_crs="EPSG:4326")
    assert tuple(sampled[0, 0]) == (10, 20, 30, 255)
    assert tuple(sampled[0, 1]) == (0, 0, 0, 0)


def test_missing_cache_renders_a_transparent_tile(tmp_path):
    tile = render_context_tile(tmp_path, 2, 1, 1)
    assert tile.shape == (256, 256, 4)
    assert int(tile[..., 3].max()) == 0


def test_context_route_does_not_require_a_cache(monkeypatch, tmp_path):
    import app as web

    monkeypatch.setattr(web, "CACHE_ROOT", tmp_path)
    with TestClient(web.app) as client:
        response = client.get("/api/context-basemap/2/1/1.png")
    assert response.status_code == 200
    assert response.content.startswith(b"\x89PNG")
    assert response.headers["x-bailasar-role"] == "geographic-context"
    assert not (tmp_path / "context-basemap" / "xyz").exists()
