"""Evidence-envelope builders (#122 contract) — pure, synthetic artifacts only."""

import pytest

from mcp_servers import evidence

PROV = {
    "source": "cache",
    "granule_ids": ["NISAR_L2_PR_GCOV_X"],
    "cache_build_time": "2026-11-15T00:00:00Z",
}
ALERT_CFG = {
    "hazard_tools": {
        "flood": {"alert": {"red_above": 5000, "orange_above": 2000, "yellow_above": 500}},
        "landslide": {"alert": {"red_above": 80, "orange_above": 35, "yellow_above": 15}},
    }
}


def _area(**over):
    base = {
        "value_ha": 4486.59,
        "pixel_count": 5539,
        "valid_pixel_count": 197758,
        "pixel_area_m2": 8100.0,
        "source_ids": ["NISAR_L2_PR_GCOV_023_047_A_005"],
        "reference_date": "2026-06-17",
        "command": "uv run python -m gee_math.flood_polarimetric_math",
    }
    base.update(over)
    return base


def _flood_artifact(**over):
    art = {
        "schema": "flood/1",
        "provenance": PROV,
        "uncalibrated": ["open_water_abs_hh_db", "class1_delta_hh_db_max"],
        "baseline": {"accepted": True, "reference_date": "2026-10-27", "reason": None},
        "dates": [{"date": "2026-06-17", "granule_ids": ["NISAR_L2_PR_GCOV_023_047_A_005"]}],
        "water_extent": _area(),
    }
    art.update(over)
    return art


def _has_all_envelope_fields(env):
    assert set(env) == set(evidence.ENVELOPE_FIELDS)
    assert env["calibrated"] is False


# --- shared envelope ------------------------------------------------------- #
def test_not_cached_and_error_shapes():
    nc = evidence.not_cached("analyze_flood_inundation", "flood", "no evidence")
    _has_all_envelope_fields(nc)
    assert nc["state"] == "not cached" and nc["error"] == "not cached"
    err = evidence.errored("t", "flood", "bad", ["a.b.c"])
    assert err["state"] == "error" and err["error"]["missing_keys"] == ["a.b.c"]


def test_missing_schema_or_provenance_raises(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{"schema": "flood/1"}')  # no provenance
    with pytest.raises(evidence.EvidenceError):
        evidence.load_artifact(p)
    assert evidence.load_artifact(tmp_path / "absent.json") is None


# --- flood ----------------------------------------------------------------- #
def test_flood_accepted_baseline_is_live_with_denominators():
    env = evidence.build_flood_envelope(_flood_artifact(), ALERT_CFG, "analyze_flood_inundation")
    _has_all_envelope_fields(env)
    assert env["state"] == "live"
    water = env["data"]["area_evidence"]["water_extent_ha"]
    assert water["pixel_count"] == 5539 and water["valid_pixel_count"] == 197758
    assert water["pixel_area_m2"] == 8100.0 and water["source_ids"]
    # no total change metric -> alert null and total unavailable
    assert env["data"]["alert_level"] is None
    assert "area_evidence.total_inundated_ha" in env["unavailable"]
    # renderers/hotspot are null + unavailable, never an AOI centroid
    for f in ("gee_xyz_tile_url", "diagnostic_rgb_tile_url", "hotspot_coordinates"):
        assert env["data"][f] is None and f in env["unavailable"]


def test_flood_rejected_baseline_is_gate_result():
    art = _flood_artifact(
        baseline={"accepted": False, "reason": "reference date has 1 valid pixel"}
    )
    env = evidence.build_flood_envelope(art, ALERT_CFG, "analyze_flood_inundation")
    assert env["state"] == "gate result"
    assert "1 valid pixel" in env["reason"]


def test_flood_area_without_source_ids_raises():
    art = _flood_artifact(water_extent=_area(source_ids=[]))
    with pytest.raises(evidence.EvidenceError):
        evidence.build_flood_envelope(art, ALERT_CFG, "analyze_flood_inundation")


def test_flood_total_present_but_alert_config_missing_errors():
    art = _flood_artifact(
        total_inundated={
            "value_ha": 100.0,
            "pixel_count": 10,
            "valid_pixel_count": 20,
            "pixel_area_m2": 8100.0,
            "source_ids": ["x"],
        }
    )
    env = evidence.build_flood_envelope(art, {}, "analyze_flood_inundation")
    assert env["state"] == "error"
    assert env["error"]["missing_keys"] == [
        "hazard_tools.flood.alert.red_above",
        "hazard_tools.flood.alert.orange_above",
        "hazard_tools.flood.alert.yellow_above",
    ]


# --- landslide ------------------------------------------------------------- #
def _landslide_artifact(outcome, **verdict_over):
    verdict = {
        "outcome": outcome,
        "text": f"verdict {outcome}",
        "noise_floor_mm": 9.105,
        "n_pairs": 17,
    }
    verdict.update(verdict_over)
    return {
        "schema": "landslide/1",
        "provenance": PROV,
        "noise_floor_verdict": verdict,
        "pairs": [],
    }


def test_landslide_no_motion_is_gate_result_with_null_alert():
    env = evidence.build_landslide_envelope(
        _landslide_artifact("no_motion"), ALERT_CFG, "analyze_landslide_kinematics"
    )
    _has_all_envelope_fields(env)
    assert env["state"] == "gate result"
    assert env["data"]["alert_level"] is None
    assert env["data"]["sensitivity_range"] is None
    assert "residual RMS is not an interval" in env["data"]["sensitivity_reason"]


def test_landslide_too_few_pairs_is_gate_result():
    env = evidence.build_landslide_envelope(
        _landslide_artifact("too_few_pairs"), ALERT_CFG, "analyze_landslide_kinematics"
    )
    assert env["state"] == "gate result"


def test_landslide_motion_needs_alert_config():
    art = _landslide_artifact("motion", retained_rate_stat_mm_yr=50.0)
    assert evidence.build_landslide_envelope(art, {}, "t")["state"] == "error"
    env = evidence.build_landslide_envelope(art, ALERT_CFG, "t")
    assert env["state"] == "live" and env["data"]["alert_level"] == "ORANGE"


# --- earthquake ------------------------------------------------------------ #
def _quake_artifact():
    return {
        "schema": "quake/1",
        "provenance": PROV,
        "counts": {
            "valid_pixels": 316399,
            "window_pixels": 10353357,
            "units_total": 32,
            "evaluated": 28,
            "excluded": 4,
        },
        "coherence_statistics": {"excess_E": "SEALED-VALUE"},
        "scorecard": {"state": "uninformative", "reason": "no barrio labels"},
    }


def test_quake_seals_statistics_until_frozen():
    env = evidence.build_quake_envelope(
        _quake_artifact(), {}, "analyze_earthquake_dpm", is_frozen=False
    )
    _has_all_envelope_fields(env)
    assert env["state"] == "live"
    assert env["data"]["counts"]["valid_pixels"] == 316399
    assert env["data"]["coherence_statistics"] is None
    assert "coherence_statistics" in env["unavailable"]
    assert "SEALED-VALUE" not in str(env)


def test_quake_unseals_when_frozen():
    env = evidence.build_quake_envelope(
        _quake_artifact(), {}, "analyze_earthquake_dpm", is_frozen=True
    )
    assert env["data"]["coherence_statistics"] == {"excess_E": "SEALED-VALUE"}
    assert "coherence_statistics" not in env["unavailable"]
