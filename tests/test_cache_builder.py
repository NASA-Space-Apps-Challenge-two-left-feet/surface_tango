"""Tests for NISAR data cache builder (brief feat/data-cache-builder, issue #30).

Pure-logic tests (no network or live cache required, runnable under CI).
Hand-written arrays verify missing bands, coverage checks, and manifest provenance.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import xarray as xr

from scripts.build_cache import (
    GEE_NODATA_SENTINEL,
    MERIT_HYDRO_ASSET,
    check_array_coverage,
    gee_nodata_to_nan,
    grid_from_cube_coords,
    hand_array_from_sample,
    hand_manifest_entry,
    load_aois,
    make_missing_band,
    merit_hand_source_id,
    parse_nisar_scene_name,
    resolve_aoi,
    structured_band,
    write_hand_variable,
)

ROOT = Path(__file__).resolve().parents[1]


def test_load_aois_from_config():
    """AOIs are read from config/bailasar.yaml and include all 3 required areas."""
    aois = load_aois()
    assert "1_aburra_medellin_bello" in aois
    assert "2_eje_cafetero_quake" in aois
    assert "3_la_mojana_caregato" in aois

    for key, bbox in aois.items():
        assert len(bbox) == 4, f"AOI {key} bbox must have 4 elements"
        w, s, e, n = bbox
        assert w < e, f"AOI {key}: min_lon must be < max_lon"
        assert s < n, f"AOI {key}: min_lat must be < max_lat"


def test_resolve_aoi_aliases():
    """CLI aliases map to canonical keys and directory names."""
    alias_map = {
        "aburra": "1_aburra_medellin_bello",
        "eje_cafetero": "2_eje_cafetero_quake",
        "mojana": "3_la_mojana_caregato",
        "la_mojana": "3_la_mojana_caregato",
    }
    for alias, expected_key in alias_map.items():
        key, short_name, bbox = resolve_aoi(alias)
        assert key == expected_key
        assert len(bbox) == 4


def test_parse_nisar_metadata():
    """Granule naming parses stream, product, polarization, and dates."""
    scene = (
        "NISAR_L2_PR_GUNW_025_011_D_086_026_4000_SH_"
        "20260708T232913_20260708T232947_20260720T232912_20260720T232946_P05023_N_F_J_001"
    )
    meta = parse_nisar_scene_name(scene)
    assert meta["stream"] == "PR"
    assert meta["product"] == "GUNW"
    assert meta["polarization"] == "SH"
    assert meta["date_1"] == "2026-07-08"
    assert meta["date_2"] == "2026-07-20"


def test_coverage_check_counts_finite_pixels():
    """Swaths with <5% finite pixel coverage over the AOI are rejected."""
    shape = (100, 100)

    # Hand-written test array: only 400 finite pixels (4.0% < 5.0%)
    under_covered = np.full(shape, np.nan, dtype=np.float32)
    under_covered[:20, :20] = 0.5
    assert not check_array_coverage(under_covered, min_ratio=0.05)

    # Hand-written test array: 600 finite pixels (6.0% >= 5.0%)
    sufficiently_covered = np.full(shape, np.nan, dtype=np.float32)
    sufficiently_covered[:20, :30] = 0.5
    assert check_array_coverage(sufficiently_covered, min_ratio=0.05)


def test_missing_band_is_nan_and_marked_missing():
    """A band that fails to load is strictly all-NaN float32 and marked 'missing'."""
    shape = (512, 512)
    arr = make_missing_band(shape)

    assert arr.shape == shape
    assert arr.dtype == np.float32
    assert np.isnan(arr).all(), "Missing band must be 100% NaN (no zero-fill fallback)"
    assert not np.any(np.isfinite(arr))


def test_manifest_lists_ids_for_every_band():
    """Manifest records an exact granule/asset ID or 'missing' for every band."""
    from scripts.build_cache import assemble_manifest_record

    # Mock band dictionary with hand-written arrays
    bands = {
        "coherence_C": {
            "arr": np.ones((10, 10), dtype=np.float32),
            "source_id": "NISAR_L2_PR_GUNW_026_011_D_086_028_4000_SH_...",
            "asset_type": "NISAR_GUNW",
            "stream": "PR",
            "dates": ["2026-07-20", "2026-08-13"],
        },
        "chirps_15d": {
            "arr": np.full((10, 10), np.nan, dtype=np.float32),
            "source_id": None,
            "asset_type": "GEE",
            "stream": None,
            "dates": None,
        },
    }

    manifest = assemble_manifest_record(
        aoi_key="2_eje_cafetero_quake",
        aoi_short="eje_cafetero",
        bbox=[-75.85, 4.40, -75.40, 5.15],
        bands=bands,
        cog_paths={"coherence_C": "/tmp/cogs/coh_c.tif"},
        zarr_path="/tmp/cube.zarr",
    )

    assert "bands" in manifest
    assert "nisar_granule_provenance" in manifest

    for _band_name, meta in manifest["bands"].items():
        src_id = meta["source_id"]
        assert isinstance(src_id, str) and len(src_id) > 0
        assert src_id.startswith("NISAR_") or src_id.startswith("GEE") or src_id == "missing", (
            f"Invalid band source ID: {src_id}"
        )

    assert manifest["bands"]["chirps_15d"]["status"] == "missing"
    assert manifest["bands"]["chirps_15d"]["source_id"] == "missing"
    assert manifest["bands"]["coherence_C"]["status"] == "cached"


def test_no_synthetic_data_in_scripts():
    """Ensure scripts/ contains no synthetic data generators."""
    forbidden = re.compile(r"synthesiz|simulat|np\.random|random\.(rand|normal|uniform|gauss)")
    for script_file in [
        ROOT / "scripts" / "build_cache.py",
        ROOT / "scripts" / "prewarm_antioquia_cache.py",
    ]:
        if script_file.exists():
            content = script_file.read_text(encoding="utf-8")
            for i, line in enumerate(content.splitlines(), 1):
                assert not forbidden.search(line), (
                    f"Forbidden pattern in {script_file.name}:{i} -> {line}"
                )


def test_hand_grid_reads_edge_affine_from_coordinates():
    """Edge-aligned cube coordinates use span/count, not a hardcoded 512 or 90 m."""
    # Hand-written: 4 rows, 5 columns, outer edges on the bbox.
    y = np.array([10.0, 9.0, 8.0, 7.0])
    x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    grid = grid_from_cube_coords(y, x, "EPSG:4326", [0.0, 7.0, 4.0, 10.0])
    assert grid.crs == "EPSG:4326"
    assert (grid.width, grid.height) == (5, 4)
    assert grid.scale_x == 0.8  # (4 - 0) / 5
    assert grid.scale_y == -0.75  # (7 - 10) / 4
    assert grid.translate_x == 0.0
    assert grid.translate_y == 10.0
    assert grid.clip_bbox == (0.0, 7.0, 4.0, 10.0)


def test_hand_grid_reads_cell_centers_from_spacing():
    """Projected coordinates that are not bbox edges use their own spacing."""
    # Hand-written 90 m cell centers. Expected origin is the first center minus half a cell.
    x = np.array([45.0, 135.0, 225.0])
    y = np.array([225.0, 135.0, 45.0])
    grid = grid_from_cube_coords(y, x, "EPSG:32618", [-75.4, 7.9, -74.2, 9.2])
    assert grid.crs == "EPSG:32618"
    assert (grid.width, grid.height) == (3, 3)
    assert grid.scale_x == 90.0
    assert grid.scale_y == -90.0
    assert grid.translate_x == 0.0  # 45 - 90/2
    assert grid.translate_y == 270.0  # 225 - (-90)/2
    assert grid.clip_bbox == (-75.4, 7.9, -74.2, 9.2)


def test_hand_sample_keeps_zero_and_maps_sentinel_to_nan():
    """HAND missing stays NaN. A drainage value of 0 m is kept. No zero-fill."""
    # Hand-written 2x3 sample. Expected finite count: 3 of 6
    # (0 m, 4.5 m, 18 m). Two sentinels and one infinity stay NaN.
    raw = np.array(
        [
            [-9999.0, 0.0, 4.5],
            [np.inf, 18.0, -9999.0],
        ],
        dtype=np.float32,
    )
    out = hand_array_from_sample(raw, (2, 3))
    assert out.shape == (2, 3)
    assert out.dtype == np.float32
    assert np.isnan(out[0, 0])
    assert out[0, 1] == 0.0
    assert out[0, 2] == np.float32(4.5)
    assert np.isnan(out[1, 0])
    assert out[1, 1] == 18.0
    assert np.isnan(out[1, 2])
    assert int(np.isfinite(out).sum()) == 3
    assert out.size == 6


def test_structured_band_picks_hnd_not_the_mask():
    """The measurement field is hnd. A mask field with the same stem is ignored."""
    raw = np.zeros(2, dtype=[("hnd", "f4"), ("hnd_mask", "f4")])
    raw["hnd"] = np.array([0.0, -9999.0], dtype=np.float32)
    raw["hnd_mask"] = np.array([1.0, 0.0], dtype=np.float32)
    picked = structured_band(raw, "hnd")
    out = gee_nodata_to_nan(picked)
    assert out[0] == 0.0
    assert np.isnan(out[1])


def test_hand_manifest_records_merit_provenance():
    """A finite HAND sample records the MERIT asset, band, version and grid."""
    y = np.array([10.0, 7.0])
    x = np.array([0.0, 4.0])
    grid = grid_from_cube_coords(y, x, "EPSG:4326", [0.0, 7.0, 4.0, 10.0])
    # Hand-written: 3 finite of 4. 0 m stays finite.
    present = np.array([[0.0, np.nan], [12.0, 4.0]], dtype=np.float32)
    record, provenance = hand_manifest_entry(present, grid)
    assert record["status"] == "cached"
    assert record["source_id"].startswith("GEE MERIT/Hydro/v1_0_1")
    assert record["band"] == "hnd"
    assert record["version"] == "v1_0_1"
    assert record["source"] == MERIT_HYDRO_ASSET
    assert record["grid"]["crs"] == "EPSG:4326"
    assert record["grid"]["width"] == 2
    assert record["grid"]["height"] == 2
    assert record["finite_pixel_count"] == 3
    assert record["finite_pixel_ratio"] == 0.75
    assert provenance == record["source_id"]
    assert merit_hand_source_id(grid) == provenance

    empty = np.full((2, 2), np.nan, dtype=np.float32)
    missing, missing_id = hand_manifest_entry(empty, grid)
    assert missing["status"] == "missing"
    assert missing["source_id"] == "missing"
    assert missing_id == "missing"
    assert missing["finite_pixel_count"] == 0
    assert missing["source"] == MERIT_HYDRO_ASSET


def test_write_hand_band_keeps_other_bytes_attrs_and_nan(tmp_path):
    """Appending hand_m leaves an existing band's chunks and the cube crs in place."""
    y = np.linspace(10.0, 7.0, 4)
    x = np.linspace(0.0, 4.0, 4)
    attrs = {
        "aoi": "mojana",
        "aoi_key": "3_la_mojana_caregato",
        "bbox": [0.0, 7.0, 4.0, 10.0],
        "crs": "EPSG:4326",
    }
    store = tmp_path / "cube.zarr"
    slope = np.arange(16, dtype=np.float32).reshape(4, 4)
    xr.Dataset(
        {"slope_deg": (("y", "x"), slope)},
        coords={"y": y, "x": x},
        attrs=attrs,
    ).to_zarr(store, mode="w", encoding={"slope_deg": {"chunks": (2, 2)}})
    chunk = store / "slope_deg" / "c" / "0" / "0"
    before = chunk.read_bytes()
    # Hand-written: one missing sample stays NaN, 0 m stays 0.
    hand = np.full((4, 4), 3.0, dtype=np.float32)
    hand[0, 1] = np.nan
    hand[1, 0] = 0.0
    write_hand_variable(store, hand, y, x, (2, 2), attrs)
    assert chunk.read_bytes() == before
    with xr.open_zarr(store, chunks=None, mask_and_scale=False) as dataset:
        assert dict(dataset.attrs) == attrs
        written = dataset["hand_m"].values
        assert np.isnan(written[0, 1])
        assert written[1, 0] == 0.0
        assert written[0, 0] == 3.0
        assert np.array_equal(dataset["slope_deg"].values, slope)


def test_hand_fetch_does_not_request_nearest_resample():
    """computePixels nearest is the default. resample('nearest') is illegal."""
    source = (ROOT / "scripts" / "build_cache.py").read_text(encoding="utf-8")
    assert 'resample("nearest")' not in source
    assert "resample('nearest')" not in source


def test_gee_nodata_to_nan_maps_sentinel():
    """Sentinel masked pixels become NaN; real values, including 0.0, are kept."""
    arr = np.array(
        [-9999.0, 0.0, 12.5, float("inf"), -9999.0],
        dtype=np.float32,
    )
    out = gee_nodata_to_nan(arr)
    # Hand-computed expectation: 3 of 5 pixels are NaN (sentinel, inf, sentinel)
    assert np.isnan(out[0])
    assert np.isnan(out[3])
    assert np.isnan(out[4])
    assert out[1] == 0.0
    assert out[2] == 12.5
    assert int(np.isnan(out).sum()) == 3
    assert GEE_NODATA_SENTINEL == -9999.0
