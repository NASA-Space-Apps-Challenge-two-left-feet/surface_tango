"""Coverage AOIs display their own coherence. They never borrow the Eje store."""

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient

from scripts.cut_quake_coherence_cog import bboxes_match, cut_aoi, write_coherence_cog
from scripts.prestage_tiles import is_nodata_hatch, tile_lonlat_bounds
from scripts.write_hazard_evidence import quake_artifact
from src.bailasar.config import get_config

GRANULE = "NISAR_TEST_C"


def test_bboxes_match_accepts_a_float_spelling_and_rejects_another_window():
    assert bboxes_match([0.0, 0.0, 1.0, 1.0], [0, 0, 1, 1])
    assert not bboxes_match([0.0, 0.0, 1.0, 1.0], [0.0, 0.0, 1.0, 2.0])
    assert not bboxes_match("not-a-box", [0.0, 0.0, 1.0, 1.0])


def test_coherence_cog_keeps_a_measured_zero_and_a_missing_pixel(tmp_path: Path):
    values = np.array([[0.0, np.nan], [np.nan, 0.0]], dtype=np.float32)
    xs = np.array([10.0, 30.0])
    ys = np.array([40.0, 20.0])
    out = tmp_path / "coherence.tif"
    write_coherence_cog(values, xs, ys, 32618, out)
    with rasterio.open(out) as source:
        grid = source.read(1, masked=True).astype(np.float32).filled(np.nan)
        assert source.tags()["role"] == "coevent_coherence_not_a_damage_class"
    assert grid[0, 0] == 0.0
    assert grid[1, 1] == 0.0
    assert np.isnan(grid[0, 1])
    assert np.isnan(grid[1, 0])


def _write_zarr(cache: Path, folder: str, prov: dict, track: int = 11) -> None:
    store = cache / folder / f"dpm_track{track}.zarr"
    store.mkdir(parents=True)
    (store / "zarr.json").write_text(
        json.dumps({"attributes": {"provenance": json.dumps(prov)}}),
        encoding="utf-8",
    )


def _prov(box: list[float], granule: str = GRANULE) -> dict:
    return {
        "aoi": box,
        "run_utc": "2026-11-15T04:00:00Z",
        "prereg_status": "frozen",
        "control_K_timing": "post_event",
        "pairs": {
            "C": {"granule_id": granule, "baseline_days": 24},
            "R": {"granule_id": "NISAR_TEST_R", "baseline_days": 12},
            "K": {"granule_id": "NISAR_TEST_K", "baseline_days": 12},
        },
        "summary_C": {
            "n_px_valid": 4,
            "n_px_total": 8,
            "n_units_total": 2,
            "n_units_evaluated": 1,
            "n_units_excluded": 1,
        },
        "summary_K_control": {"n_px_valid": 4},
        "grid": {"epsg": 32618},
    }


def test_choco_artifact_does_not_read_the_eje_store(tmp_path, monkeypatch):
    import scripts.write_hazard_evidence as whe

    eje = list(get_config().aoi_bbox("2_eje_cafetero_quake"))
    _write_zarr(tmp_path, "quake", _prov(eje))
    monkeypatch.setattr(whe, "CACHE", tmp_path)
    assert quake_artifact(aoi="choco_epicenter", track=11) is None
    assert quake_artifact(aoi="valle_del_cauca", track=11) is None


def test_choco_artifact_refuses_the_eje_window(tmp_path, monkeypatch):
    import scripts.write_hazard_evidence as whe

    eje = list(get_config().aoi_bbox("2_eje_cafetero_quake"))
    _write_zarr(tmp_path, "choco_epicenter", _prov(eje))
    monkeypatch.setattr(whe, "CACHE", tmp_path)
    assert quake_artifact(aoi="choco_epicenter", track=11) is None


def test_choco_artifact_accepts_its_own_window(tmp_path, monkeypatch):
    import scripts.write_hazard_evidence as whe

    box = list(get_config().aoi_bbox("4_choco_epicenter_quake"))
    _write_zarr(tmp_path, "choco_epicenter", _prov(box))
    prereg = tmp_path / "prereg.yaml"
    prereg.write_text("status: frozen\nlabels: {uncalibrated: []}\n", encoding="utf-8")
    monkeypatch.setattr(whe, "CACHE", tmp_path)
    monkeypatch.setattr(whe, "PREREG", prereg)
    art = quake_artifact(aoi="choco_epicenter", track=11)
    assert art is not None
    assert art["provenance"]["aoi"] == "choco_epicenter"
    assert art["provenance"]["track"] == 11
    assert art["pairs"]["C"]["granule_id"] == GRANULE
    assert art["provenance"]["control_K_timing"] == "post_event"


def test_cutter_refuses_a_foreign_window_and_an_unlisted_aoi(tmp_path: Path):
    eje = list(get_config().aoi_bbox("2_eje_cafetero_quake"))
    _write_zarr(tmp_path, "choco_epicenter", _prov(eje))
    with pytest.raises(ValueError, match="does not match"):
        cut_aoi("choco_epicenter", 11, tmp_path)
    with pytest.raises(ValueError, match="not a coverage AOI"):
        cut_aoi("eje_cafetero", 11, tmp_path)


def _stage_panel(cache: Path, aoi: str = "choco_epicenter") -> None:
    root = cache / aoi
    evidence = {
        "schema": "quake/1",
        "provenance": {
            "aoi": aoi,
            "granule_ids": [GRANULE],
            "control_K_timing": "post_event",
        },
        "pairs": {"C": {"granule_id": GRANULE}},
    }
    (root / "quake_evidence_track11.json").parent.mkdir(parents=True)
    (root / "quake_evidence_track11.json").write_text(json.dumps(evidence), encoding="utf-8")
    manifest = {
        "aoi": aoi,
        "bands": {"coherence_coseismic": {"status": "cached", "source_id": GRANULE}},
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    west, south, east, north = tile_lonlat_bounds(3, 2, 3)
    width = 32
    posting_x = (east - west) / width
    posting_y = (north - south) / width
    xs = west + posting_x * (np.arange(width) + 0.5)
    ys = north - posting_y * (np.arange(width) + 0.5)
    values = np.zeros((width, width), dtype=np.float32)
    values[:, width // 2 :] = np.nan
    write_coherence_cog(values, xs, ys, 4326, root / "cogs" / f"{aoi}_coherence_coseismic.tif")


def test_panel_stays_absent_until_this_aoi_owns_the_files(tmp_path, monkeypatch):
    import app as web

    monkeypatch.setattr(web, "CACHE_ROOT", tmp_path)
    assert web.find_nisar_panel("choco_epicenter") is None
    assert web.find_nisar_panel("valle_del_cauca") is None


def test_panel_names_track_11_and_refuses_the_scorecard_label(tmp_path, monkeypatch):
    import app as web

    _stage_panel(tmp_path)
    monkeypatch.setattr(web, "CACHE_ROOT", tmp_path)
    panel = web.find_nisar_panel("choco_epicenter")
    assert panel is not None
    assert panel.tracks == [11]
    assert panel.granule_ids == [GRANULE]
    assert panel.style == "coherence"
    assert "not the Eje Cafetero scorecard" in panel.detail
    assert "Track 47 is not in this display" in panel.detail
    assert "post-event control" in panel.detail


def test_coherence_zero_stays_painted_inside_the_frame():
    """A measured 0 is not cleared. A missing pixel inside the frame is a hatch."""
    import app as web

    values = np.array([[0.0, np.nan], [0.5, 0.0]], dtype=np.float32)
    rgba = np.moveaxis(web._panel_rgba("coherence", values), 0, -1)
    frame = np.array([[True, True], [True, False]])
    out = web._clip_panel_to_frame("coherence", rgba, values, frame)
    assert list(out[0, 0]) == [35, 30, 75, 255]
    assert is_nodata_hatch(out[0, 1])
    # 0.5 * 220 = 110, so red is 35 + 110 = 145.
    # 0.5 * 185 = 92.5, so green truncates to 30 + 92 = 122.
    # 0.5 * 145 = 72.5, so blue truncates to 75 + 72 = 147.
    assert list(out[1, 0]) == [145, 122, 147, 255]
    assert list(out[1, 1, :3]) == [35, 30, 75]
    assert int(out[1, 1, 3]) == 0


def test_dry_water_stays_transparent_and_open_water_stays_painted():
    import app as web

    values = np.array([[1.0, 0.0], [np.nan, 1.0]], dtype=np.float32)
    rgba = np.moveaxis(web._panel_rgba("water", values), 0, -1)
    frame = np.array([[True, True], [True, False]])
    out = web._clip_panel_to_frame("water", rgba, values, frame)
    assert list(out[0, 0]) == [53, 196, 181, 200]
    assert list(out[0, 1]) == [0, 0, 0, 0]
    assert not is_nodata_hatch(out[0, 1])
    assert is_nodata_hatch(out[1, 0])
    assert list(out[1, 1]) == [53, 196, 181, 0]


def test_served_coherence_tile_keeps_a_measured_zero(tmp_path, monkeypatch):
    import app as web

    _stage_panel(tmp_path)
    bounds = tile_lonlat_bounds(3, 2, 3)
    monkeypatch.setattr(web, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(web, "aoi_curtain_frame", lambda _aoi: bounds)
    with TestClient(web.app) as client:
        response = client.get("/api/nisar-panel/choco_epicenter/3/2/3.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    path = tmp_path / "tile.png"
    path.write_bytes(response.content)
    with rasterio.open(path) as source:
        rgba = np.moveaxis(source.read(), 0, -1)
    # The staged grid is 0 on the west half and NaN on the east half.
    assert list(rgba[128, 64]) == [35, 30, 75, 255]
    assert is_nodata_hatch(rgba[128, 192])
