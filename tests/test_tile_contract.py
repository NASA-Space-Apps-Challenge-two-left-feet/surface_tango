"""Curtain contract: one frame per cached AOI, and no-data is never 0.

The footprints below are hand-written. They are not a measurement of the cache.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio

from scripts.prestage_tiles import (
    HATCH_LIGHT,
    NOT_CACHED_WITHOUT_TILES,
    curtain_aoi_state,
    is_nodata_hatch,
    layer_data_bbox,
    nodata_ui_label,
    render_frame_tile,
    shared_frame,
    walk_curtain,
)

# Each cached AOI has a config box and three layer footprints. The frame is
# their intersection, which sits inside the config box.
CURTAIN_FIXTURES = {
    "mojana": {
        "config": [-20.0, -20.0, 20.0, 20.0],
        "optical": [-10.0, -10.0, 10.0, 10.0],
        "cband": [-2.0, -8.0, 8.0, 4.0],
        "nisar": [-6.0, -3.0, 3.0, 9.0],
        "frame": [-2.0, -3.0, 3.0, 4.0],
    },
    "aburra": {
        "config": [-1.0, -1.0, 5.0, 5.0],
        "optical": [0.0, 0.0, 4.0, 4.0],
        "cband": [1.0, 0.0, 4.0, 3.0],
        "nisar": [0.0, 1.0, 3.0, 4.0],
        "frame": [1.0, 1.0, 3.0, 3.0],
    },
    "eje_cafetero": {
        "config": [9.0, 8.0, 16.0, 18.0],
        "optical": [10.0, 10.0, 14.0, 16.0],
        "cband": [11.0, 9.0, 15.0, 15.0],
        "nisar": [10.0, 11.0, 13.0, 16.0],
        "frame": [11.0, 11.0, 13.0, 15.0],
    },
}


def _footprints(fixture: dict) -> dict:
    return {name: fixture[name] for name in ("optical", "cband", "nisar")}


def test_curtain_bounds_stay_identical_from_5_to_95():
    for name, fixture in CURTAIN_FIXTURES.items():
        frame = shared_frame(_footprints(fixture))
        assert frame == fixture["frame"], name
        assert frame != fixture["config"], name
        assert frame[0] > fixture["config"][0] and frame[2] < fixture["config"][2], name
        stops = walk_curtain(frame)
        assert len(stops) == 91  # 5 through 95 inclusive
        for pct, panels in enumerate(stops, start=5):
            assert panels["optical"] == panels["cband"] == panels["nisar"] == frame, (name, pct)
            assert panels["optical"] is not panels["cband"]


def test_a_missing_layer_does_not_grow_the_frame_to_the_config_box():
    fixture = CURTAIN_FIXTURES["mojana"]
    footprints = _footprints(fixture)
    footprints["cband"] = None
    frame = shared_frame({**footprints, "config": fixture["config"]})
    assert frame == [-6.0, -3.0, 3.0, 9.0]
    assert frame != fixture["config"]


def test_disjoint_layers_have_no_frame():
    assert (
        shared_frame({"optical": [0, 0, 1, 1], "cband": [2, 2, 3, 3], "nisar": [4, 4, 5, 5]})
        is None
    )


def test_named_areas_stay_not_cached_without_a_manifest():
    footprints = {
        "optical": [0.0, 0.0, 1.0, 1.0],
        "cband": [0.0, 0.0, 1.0, 1.0],
        "nisar": [0.0, 0.0, 1.0, 1.0],
    }
    assert NOT_CACHED_WITHOUT_TILES == ("la_picacha", "choco_epicenter", "valle_del_cauca")
    for name in NOT_CACHED_WITHOUT_TILES:
        assert curtain_aoi_state(False, footprints) == {"state": "not cached", "frame": None}, name
        assert shared_frame(footprints) == [0.0, 0.0, 1.0, 1.0]
        # The name is not given a frame unless a tile manifest exists.
        assert (
            curtain_aoi_state(has_tile_manifest=False, layer_footprints=footprints)["frame"] is None
        )


def test_nodata_pixel_is_a_hatch_and_a_measured_zero_stays_zero():
    src = np.zeros((4, 4, 4), dtype=np.uint8)
    src[0, 0] = [0, 0, 0, 0]
    src[0, 1] = [0, 0, 0, 255]
    src[1, 1] = [10, 20, 30, 255]
    src[2, 2] = [9, 9, 9, 255]
    inside = np.zeros((4, 4), dtype=bool)
    inside[0, 0] = True
    inside[0, 1] = True
    inside[1, 1] = True
    out = render_frame_tile(src, inside)
    assert is_nodata_hatch(out[0, 0])
    assert nodata_ui_label(out[0, 0]) == "no data"
    assert not any(int(channel) == 0 for channel in out[0, 0])
    assert list(out[0, 1]) == [0, 0, 0, 255]
    assert nodata_ui_label(out[0, 1]) == ""
    assert list(out[1, 1]) == [10, 20, 30, 255]
    # Outside the frame the color is kept and the pixel is not filled with 0.
    assert list(out[2, 2, :3]) == [9, 9, 9]
    assert int(out[2, 2, 3]) == 0
    assert not is_nodata_hatch(out[2, 2])
    assert tuple(int(channel) for channel in out[0, 0][:3]) == HATCH_LIGHT


def test_opaque_pixels_define_the_layer_bbox(tmp_path: Path):
    """A 4x4 tile at z=3, x=2, y=2. The left half is observed. West is the tile edge."""
    width = 4
    rgba = np.zeros((width, width, 4), dtype=np.uint8)
    rgba[:, :2, :3] = [255, 0, 0]
    rgba[:, :2, 3] = 255
    dest = tmp_path / "s2" / "3" / "2" / "2.png"
    dest.parent.mkdir(parents=True)
    with rasterio.open(
        dest, "w", driver="PNG", width=width, height=width, count=4, dtype="uint8"
    ) as dst:
        dst.write(np.moveaxis(rgba, -1, 0))
    bbox = layer_data_bbox(tmp_path / "s2")
    assert bbox is not None
    # Tile x=2 at z=3 starts at lon -90. The observed half ends at lon -67.5.
    assert bbox[0] == -90.0
    assert bbox[2] == -67.5
    assert bbox[1] < bbox[3]


def test_story_chapter_keeps_the_feet_and_lands_on_one_frame():
    story = Path("static/story-map.js").read_text(encoding="utf-8")
    body = story.split("async function openStoryChapter", 1)[1].split("\nchapterSelect", 1)[0]
    assert body.index("playFeetTransition(chapter)") < body.index("fitChapter(storyFrame)")
    assert "curtainPanelBounds(storyFrame)" in body
    assert "no data" in story
    page = Path("static/index.html").read_text(encoding="utf-8")
    clip = page.split("function updateCurtainClips()", 1)[1].split("function moveHandleTo", 1)[0]
    assert "clipPath" in clip
    assert "fitBounds" not in clip
    assert "setZoom" not in clip
