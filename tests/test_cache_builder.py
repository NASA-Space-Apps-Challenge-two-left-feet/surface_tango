"""Tests for NISAR data cache builder (brief feat/data-cache-builder, issue #30).

Pure-logic tests (no network or live cache required, runnable under CI).
Hand-written arrays verify missing bands, coverage checks, and manifest provenance.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from scripts.build_cache import (
    GEE_NODATA_SENTINEL,
    check_array_coverage,
    gee_nodata_to_nan,
    load_aois,
    make_missing_band,
    parse_nisar_scene_name,
    resolve_aoi,
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
