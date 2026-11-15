"""Unit tests for Sentinel-1/2 curtain slider tile pre-staging (DATA-02 / #30).

Every Earth Engine call is mocked; tests run offline (no network, no credentials).
"""

from __future__ import annotations

from datetime import date

from scripts.prestage_tiles import (
    aoi_fractions,
    build_manifest,
    group_acquisitions,
    in_window,
    least_cloudy,
    nearest_after,
    nearest_to,
    select,
    tile_range,
)


def test_group_acquisitions_by_day_and_orbit():
    granules = [
        {"id": "G1", "date": "2026-08-11", "orbit": 10},
        {"id": "G2", "date": "2026-08-11", "orbit": 10},
        {"id": "G3", "date": "2026-08-12", "orbit": 10},
        {"id": "G4", "date": "2026-08-11", "orbit": 20},
    ]
    acqs = group_acquisitions(granules, ("orbit",))
    assert len(acqs) == 3
    # G1 and G2 grouped together
    assert acqs[0]["ids"] == ["G1", "G2"]
    assert acqs[0]["date"] == "2026-08-11"
    assert acqs[0]["orbit"] == 10


def test_in_window_filters_dates():
    acqs = [
        {"date": "2026-08-01", "ids": ["A"]},
        {"date": "2026-08-10", "ids": ["B"]},
        {"date": "2026-08-15", "ids": ["C"]},
        {"date": "2026-08-20", "ids": ["D"]},
    ]
    res = in_window(acqs, date(2026, 8, 10), date(2026, 8, 15))
    assert [a["ids"][0] for a in res] == ["B", "C"]


def test_least_cloudy_selects_lowest_obscured_pct():
    acqs = [
        {"ids": ["A"], "date": "2026-08-11", "obscured_pct": 25.5},
        {"ids": ["B"], "date": "2026-08-12", "obscured_pct": 5.0},
        {"ids": ["C"], "date": "2026-08-13", "obscured_pct": 12.0},
    ]
    winner = least_cloudy(acqs)
    assert winner is not None
    assert winner["ids"] == ["B"]


def test_least_cloudy_breaks_ties_by_earliest_date():
    acqs = [
        {"ids": ["B"], "date": "2026-08-15", "obscured_pct": 10.0},
        {"ids": ["A"], "date": "2026-08-11", "obscured_pct": 10.0},
    ]
    winner = least_cloudy(acqs)
    assert winner is not None
    assert winner["ids"] == ["A"]


def test_nearest_after_quake_respects_orbit_direction():
    event = date(2026, 8, 10)
    acqs = [
        {"ids": ["S1_PRE"], "date": "2026-08-08", "pass": "DESCENDING"},
        {"ids": ["S1_SAME_DAY"], "date": "2026-08-10", "pass": "DESCENDING"},
        {"ids": ["S1_ASC"], "date": "2026-08-11", "pass": "ASCENDING"},
        {"ids": ["S1_DESC_1"], "date": "2026-08-13", "pass": "DESCENDING"},
        {"ids": ["S1_DESC_2"], "date": "2026-08-25", "pass": "DESCENDING"},
    ]
    winner = nearest_after(acqs, event, orbit_pass="DESCENDING")
    assert winner is not None
    assert winner["ids"] == ["S1_DESC_1"]
    assert winner["date"] == "2026-08-13"


def test_nearest_to_target_date():
    target = date(2026, 7, 20)
    acqs = [
        {"ids": ["A"], "date": "2026-07-10"},
        {"ids": ["B"], "date": "2026-07-22"},
        {"ids": ["C"], "date": "2026-07-25"},
    ]
    winner = nearest_to(acqs, target)
    assert winner is not None
    assert winner["ids"] == ["B"]


def test_aoi_fractions_calculation_and_null_handling():
    # 80% coverage, 20% cloud of total AOI -> cloud_pct of imaged = 25%, obscured = 40%
    f = aoi_fractions(0.8, 0.2)
    assert f["coverage_pct"] == 80.0
    assert f["cloud_pct"] == 25.0
    assert f["obscured_pct"] == 40.0

    # Null handling: missing stays None, no zero-fill
    null_f = aoi_fractions(None, 0.1)
    assert null_f["coverage_pct"] is None
    assert null_f["cloud_pct"] is None
    assert null_f["obscured_pct"] is None


def test_lonlat_to_tile_and_tile_range():
    # Medellín bbox at zoom 10
    bbox = [-75.70, 6.12, -75.42, 6.45]
    tiles = tile_range(bbox, 10, 10)
    assert len(tiles) > 0
    for z, x, y in tiles:
        assert z == 10
        assert isinstance(x, int)
        assert isinstance(y, int)


def test_select_empty_collection_returns_missing_status():
    event = date(2026, 8, 10)
    window = (date(2026, 6, 17), date(2026, 11, 14))
    orbit = {"pass": "DESCENDING", "nisar_pair": "PAIR_C", "nisar_track": 11}

    # Empty candidates
    picks = select("eje_cafetero", [], [], event, window, orbit)
    vis = {"s2": {}, "s1": {}}
    manifest = build_manifest(
        "eje_cafetero",
        "2_eje_cafetero_quake",
        [-75.85, 4.40, -75.40, 5.15],
        event,
        window,
        orbit,
        picks,
        (9, 10),
        vis,
        {},
    )

    s2_layer = manifest["layers"]["optical_s2"]
    assert s2_layer["status"] == "missing"
    assert s2_layer["scene_ids"] == []
    assert s2_layer["cloud_pct"] is None
    assert "no acquisition in" in s2_layer["reason"]
    assert s2_layer["selection_rule"] != ""

    s1_layer = manifest["layers"]["cband_s1"]
    assert s1_layer["status"] == "missing"
    assert s1_layer["scene_ids"] == []
    assert s1_layer["status"] == "missing"


def test_manifest_records_ids_and_stated_rule():
    event = date(2026, 8, 10)
    window = (date(2026, 6, 17), date(2026, 11, 14))
    orbit = {"pass": "DESCENDING", "nisar_pair": "PAIR_C", "nisar_track": 11}

    s2_acqs = [
        {
            "ids": ["S2A_20260815"],
            "date": "2026-08-15",
            "SPACECRAFT_NAME": "Sentinel-2A",
            "SENSING_ORBIT_NUMBER": 46,
            "cloud_pct": 12.5,
            "coverage_pct": 98.0,
            "obscured_pct": 14.5,
            "granule_cloudy_pixel_pct": {"S2A_20260815": 10.0},
        }
    ]
    s1_acqs = [
        {
            "ids": ["S1A_20260813"],
            "date": "2026-08-13",
            "platform_number": "A",
            "relativeOrbitNumber_start": 86,
            "pass": "DESCENDING",
            "coverage_pct": 100.0,
        }
    ]

    picks = select("eje_cafetero", s2_acqs, s1_acqs, event, window, orbit)
    vis = {"s2": {"bands": ["B4", "B3", "B2"]}, "s1": {"bands": ["VV"]}}
    manifest = build_manifest(
        "eje_cafetero",
        "2_eje_cafetero_quake",
        [-75.85, 4.40, -75.40, 5.15],
        event,
        window,
        orbit,
        picks,
        (9, 13),
        vis,
        {"s2": {"written": 20, "requested": 20, "failed": []}},
    )

    s2_entry = manifest["layers"]["optical_s2"]
    assert s2_entry["status"] == "cached"
    assert s2_entry["scene_ids"] == ["S2A_20260815"]
    assert s2_entry["date"] == "2026-08-15"
    assert s2_entry["cloud_pct"] == 12.5
    assert "Least-cloudy" in s2_entry["selection_rule"]

    s1_entry = manifest["layers"]["cband_s1"]
    assert s1_entry["status"] == "cached"
    assert s1_entry["scene_ids"] == ["S1A_20260813"]
    assert s1_entry["date"] == "2026-08-13"
    assert s1_entry["orbit_pass"] == "DESCENDING"
    assert "DESCENDING pass" in s1_entry["selection_rule"]
