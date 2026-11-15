"""The visor background is labeled context and uses Esri's row/column tile order."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TILES = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
CREDIT = "Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community"


def test_context_style_keeps_a_dark_field_under_the_imagery():
    script = (ROOT / "static/context-basemap.js").read_text(encoding="utf-8")
    assert TILES in script
    assert "{z}/{x}/{y}" not in script
    assert CREDIT in script
    assert "not a measurement" in script
    layers = script.split("layers:", 1)[1]
    assert layers.index('id: "background"') < layers.index('type: "raster"')


def test_curtain_and_atlas_use_the_context_style_and_say_so():
    page = (ROOT / "static/index.html").read_text(encoding="utf-8")
    atlas = (ROOT / "static/cube.html").read_text(encoding="utf-8")
    cube = (ROOT / "static/cube.js").read_text(encoding="utf-8")
    assert page.index("/static/context-basemap.js") < page.index("contextBasemapStyle")
    assert 'contextBasemapStyle("#0f172a")' in page
    assert "attributionControl: false" in page
    assert 'id="context-basemap-credit"' in page
    assert CREDIT in page
    assert "not a measurement" in page
    assert '"raster-opacity": 1' in page
    assert "/static/context-basemap.js" in atlas
    assert 'id="context-basemap-credit"' in atlas
    assert CREDIT in atlas
    assert 'contextBasemapStyle("#202524")' in cube
    assert 'event?.sourceId==="context-basemap"' in cube
