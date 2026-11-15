"""Response-posture heuristics. Hand-written envelopes only; never a cache product."""

import json
from pathlib import Path

import pytest
import yaml

from mcp_servers import evidence
from mcp_servers.decision import decide, decision_config, product_for_aoi, roster

ROOT = Path(__file__).resolve().parents[1]
PROV = {
    "source": "test",
    "granule_ids": ["fixture-granule"],
    "command": "tests/test_decision.py",
    "cache_build_time": "2026-11-15T00:00:00Z",
}


def _cfg():
    ops = yaml.safe_load((ROOT / "config" / "bailasar.yaml").read_text(encoding="utf-8"))
    return decision_config(ops)


def _area(**over):
    base = {
        "value_ha": 10.0,
        "pixel_count": 1000,
        "valid_pixel_count": 1000,
        "pixel_area_m2": 100.0,
        "source_ids": ["fixture-granule"],
        "reference_date": "2026-06-17",
        "command": "tests/test_decision.py",
    }
    base.update(over)
    return base


def _flood_artifact(**over):
    artifact = {
        "schema": "flood/1",
        "provenance": PROV,
        "uncalibrated": ["open_water_abs_hh_db"],
        "baseline": {"accepted": True, "reason": None},
        "water_extent": _area(),
    }
    artifact.update(over)
    return artifact


def _landslide(outcome, **verdict_over):
    verdict = {"outcome": outcome, "text": outcome}
    verdict.update(verdict_over)
    return {
        "schema": "landslide/1",
        "provenance": PROV,
        "noise_floor_verdict": verdict,
        "uncalibrated": [],
    }


def _quake(valid_pixels, **over):
    artifact = {
        "schema": "quake/1",
        "provenance": PROV,
        "counts": {"valid_pixels": valid_pixels},
        "scorecard": {"state": "uninformative", "reason": "no barrio labels"},
        "uncalibrated": [],
    }
    artifact.update(over)
    return artifact


def _walk_numbers(node, trail):
    if isinstance(node, bool) or node is None or isinstance(node, str):
        return
    if isinstance(node, int | float):
        raise AssertionError(f"numeric decision value at {trail}: {node}")
    if isinstance(node, dict):
        for key, value in node.items():
            _walk_numbers(value, f"{trail}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk_numbers(value, f"{trail}[{index}]")


def test_decision_config_has_no_numeric_thresholds():
    ops = yaml.safe_load((ROOT / "config" / "bailasar.yaml").read_text(encoding="utf-8"))
    _walk_numbers(ops["decision"], "decision")
    assert ops["decision"]["rank"] == [
        "deploy_assessment",
        "provisional",
        "not_assessed",
        "monitor",
    ]


def test_flood_uncalibrated_water_is_provisional_and_does_not_size_people():
    env = evidence.build_flood_envelope(_flood_artifact(), {}, "analyze_flood_inundation")
    product = decide(["flood"], {"flood": [env]}, _cfg())
    assert product["posture"] == "provisional"
    assert product["lights_applicable"] is False
    assert product["product_kind"] == "flood_extent_response"
    assert product["chip"] == "Open water"
    assert product["damage_level"]["availability"] == "unavailable"
    assert product["response_package"]
    assert all(
        item["quantity"]["availability"] == "unavailable" for item in product["response_package"]
    )
    assert product["action"] == "preposition_assessment"
    assert product["clearance"] is False
    extent = product["magnitude"]["extent"]
    assert extent["value_ha"] == 10.0
    assert extent["pixel_count"] == 1000
    assert extent["valid_pixel_count"] == 1000
    assert extent["pixel_area_m2"] == 100.0
    assert extent["source_ids"] == ["fixture-granule"]
    assert extent["represents"] == "provisional_open_water"
    assert "not people flooded" in extent["label"]
    assert product["magnitude"]["social_impact"]["availability"] == "unavailable"
    assert product["magnitude"]["economic_impact"]["availability"] == "unavailable"
    cover = product["land_cover"]
    assert cover["availability"] == "unavailable"
    assert cover["economic_weight"] == "unavailable"
    assert "Agricultural, livestock, and vacant land are not counted." in cover["reason"]
    assert "No economic multiplier is applied." in cover["reason"]
    _walk_numbers(cover, "land_cover")
    assert product["buildings"]["amount"] == "unavailable"
    _walk_numbers(product["buildings"], "buildings")
    assert all(
        line["quantity"]["availability"] == "unavailable" for line in product["lines_of_effort"]
    )
    assert all(item["status"] == "not_assessed" for item in product["lifelines"])


def test_landslide_no_motion_is_monitor_and_not_a_clearance():
    env = evidence.build_landslide_envelope(
        _landslide("no_motion"), {}, "analyze_landslide_kinematics"
    )
    product = decide(["landslide"], {"landslide": [env]}, _cfg())
    assert product["posture"] == "monitor"
    assert product["lights_applicable"] is True
    assert product["product_kind"] == "landslide_ews"
    assert product["chip"] == product["posture_label"]
    assert product["action"] == "no_dispatch"
    assert product["clearance"] is False
    assert "not a safety clearance" in product["clearance_text"]
    assert product["magnitude"]["extent"]["availability"] == "unavailable"
    flood = next(row for row in product["hazards"] if row["domain"] == "flood")
    assert flood["light"] == "out_of_scope"
    assert "not a safety clearance" in flood["reason"]


def test_landslide_too_few_pairs_is_not_assessed():
    env = evidence.build_landslide_envelope(
        _landslide("too_few_pairs"), {}, "analyze_landslide_kinematics"
    )
    product = decide(["landslide"], {"landslide": [env]}, _cfg())
    assert product["posture"] == "not_assessed"
    assert product["action"] == "preposition_assessment"


def test_quake_uninformative_scorecard_is_a_window_not_affected_area():
    env = evidence.build_quake_envelope(_quake(1000), {}, "analyze_earthquake_dpm", is_frozen=True)
    env["track"] = 11
    product = decide(["earthquake"], {"earthquake": [env]}, _cfg())
    assert product["posture"] == "not_assessed"
    assert product["lights_applicable"] is False
    assert product["product_kind"] == "quake_window_response"
    assert product["chip"] == "Analyzed window"
    assert product["damage_level"]["availability"] == "unavailable"
    assert all(
        item["quantity"]["availability"] == "unavailable" for item in product["response_package"]
    )
    extent = product["magnitude"]["extent"]
    assert extent["represents"] == "analyzed_window"
    assert extent["valid_pixels"] == 1000
    assert "value_ha" not in extent
    assert "not affected area" in extent["label"]
    assert product["posture"] != "deploy_assessment"
    buildings = product["buildings"]
    assert buildings["availability"] == "unavailable"
    assert buildings["typology"] == "unavailable"
    assert buildings["amount"] == "unavailable"
    assert "damaged-building labels" in buildings["reason"]
    assert "not assessed" in buildings["reason"]
    _walk_numbers(buildings, "buildings")
    assert product["land_cover"]["economic_weight"] == "unavailable"
    _walk_numbers(product["land_cover"], "land_cover")


def test_missing_envelope_is_not_assessed():
    product = decide(["flood"], {}, _cfg())
    assert product["posture"] == "not_assessed"
    assert product["state"] == "not cached"
    assert product["action"] == "preposition_assessment"


def test_monitor_does_not_clear_an_unassessed_sibling():
    landslide = evidence.build_landslide_envelope(
        _landslide("no_motion"), {}, "analyze_landslide_kinematics"
    )
    missing = evidence.not_cached("analyze_flood_inundation", "flood", "no flood evidence")
    product = decide(
        ["landslide", "flood"],
        {"landslide": [landslide], "flood": [missing]},
        _cfg(),
    )
    assert product["posture"] == "not_assessed"
    assert product["action"] == "preposition_assessment"


def test_motion_red_and_empty_uncalibrated_dispatches_assessment_only():
    env = {
        "state": "live",
        "tool": "analyze_landslide_kinematics",
        "domain": "landslide",
        "uncalibrated": [],
        "error": None,
        "reason": "motion",
        "provenance": PROV,
        "data": {
            "alert_level": "RED",
            "alert_reason": "graded on the retained-rate statistic (mm/yr), strict >",
            "area_evidence": None,
            "area_reason": "no area is computed for the landslide verdict",
            "noise_floor_verdict": {"outcome": "motion", "retained_rate_stat_mm_yr": 80},
        },
    }
    product = decide(["landslide"], {"landslide": [env]}, _cfg())
    assert product["posture"] == "deploy_assessment"
    assert product["action"] == "dispatch_life_safety"
    assert product["magnitude"]["social_impact"]["availability"] == "unavailable"
    assert product["magnitude"]["economic_impact"]["availability"] == "unavailable"
    assert product["magnitude"]["extent"]["availability"] == "unavailable"
    row = next(item for item in product["hazards"] if item["domain"] == "landslide")
    assert row["kinematics"]["retained_rate_stat_mm_yr"] == 80
    assert all(
        line["quantity"]["availability"] == "unavailable" for line in product["lines_of_effort"]
    )


def test_red_on_an_uncalibrated_product_does_not_dispatch():
    env = {
        "state": "live",
        "tool": "analyze_landslide_kinematics",
        "uncalibrated": ["landslide"],
        "error": None,
        "provenance": PROV,
        "data": {
            "alert_level": "RED",
            "alert_reason": "graded on the retained-rate statistic (mm/yr), strict >",
            "area_evidence": None,
            "area_reason": "no area is computed",
            "noise_floor_verdict": {"outcome": "motion", "retained_rate_stat_mm_yr": 80},
        },
    }
    product = decide(["landslide"], {"landslide": [env]}, _cfg())
    assert product["posture"] == "provisional"
    assert product["action"] == "preposition_assessment"


def test_yellow_motion_is_not_a_dispatch():
    env = {
        "state": "live",
        "tool": "analyze_landslide_kinematics",
        "uncalibrated": [],
        "error": None,
        "provenance": PROV,
        "data": {
            "alert_level": "YELLOW",
            "alert_reason": "below dispatch",
            "area_evidence": None,
            "area_reason": "no area is computed",
            "noise_floor_verdict": {"outcome": "motion"},
        },
    }
    assert decide(["landslide"], {"landslide": [env]}, _cfg())["posture"] == "provisional"


def test_quake_windows_are_not_added_or_turned_into_hectares():
    first = evidence.build_quake_envelope(_quake(100), {}, "analyze_earthquake_dpm", is_frozen=True)
    second = evidence.build_quake_envelope(
        _quake(250, counts={"valid_pixels": 250, "pixel_area_m2": 100.0}),
        {},
        "analyze_earthquake_dpm",
        is_frozen=True,
    )
    first["track"] = 11
    second["track"] = 47
    product = decide(["earthquake"], {"earthquake": [first, second]}, _cfg())
    extent = product["magnitude"]["extent"]
    assert extent["combined"] is False
    assert "value_ha" not in json.dumps(extent)
    dumped = json.dumps(extent)
    assert '"valid_pixels": 100' in dumped
    assert '"valid_pixels": 250' in dumped
    assert '"valid_pixels": 350' not in dumped


def test_measured_exposure_is_copied_and_not_invented_when_absent():
    env = evidence.build_flood_envelope(_flood_artifact(), {}, "analyze_flood_inundation")
    env["data"]["population"] = {
        "value": 10,
        "unit": "people",
        "source_ids": ["fixture-worldpop"],
        "command": "tests/test_decision.py",
    }
    product = decide(["flood"], {"flood": [env]}, _cfg())
    social = product["magnitude"]["social_impact"]
    assert social["availability"] == "measured"
    assert social["value"] == 10
    assert social["source_ids"] == ["fixture-worldpop"]
    assert product["magnitude"]["economic_impact"]["availability"] == "unavailable"


def test_unknown_aoi_and_empty_cache(tmp_path):
    assert product_for_aoi("no-such-aoi", cache_root=tmp_path) is None
    product = product_for_aoi("mojana", cache_root=tmp_path)
    assert product["posture"] == "not_assessed"
    assert product["state"] == "not cached"
    assert product["action"] == "preposition_assessment"
    board = roster(cache_root=tmp_path)
    assert board["posture"] == "not_assessed"
    assert all(item["posture"] != "deploy_assessment" for item in board["aois"])
    assert {item["aoi"] for item in board["aois"]} == {
        "mojana",
        "aburra",
        "la_picacha",
        "eje_cafetero",
        "choco_epicenter",
        "valle_del_cauca",
    }


@pytest.mark.cache
def test_staged_cache_does_not_dispatch():
    """The linked cache's current envelopes. Skipped in CI (no cache)."""
    board = roster(cache_root=ROOT / "local_cache")
    by_id = {item["aoi"]: item for item in board["aois"]}
    assert by_id["mojana"]["posture"] == "provisional"
    assert by_id["mojana"]["lights_applicable"] is False
    assert by_id["mojana"]["chip"] == "Open water"
    assert by_id["mojana"]["magnitude"]["extent"]["represents"] == "provisional_open_water"
    assert by_id["mojana"]["magnitude"]["social_impact"]["availability"] == "unavailable"
    assert by_id["mojana"]["land_cover"]["economic_weight"] == "unavailable"
    assert "No economic multiplier is applied." in by_id["mojana"]["land_cover"]["reason"]
    assert by_id["aburra"]["posture"] == "monitor"
    assert by_id["aburra"]["lights_applicable"] is True
    assert by_id["aburra"]["clearance"] is False
    assert by_id["eje_cafetero"]["posture"] == "not_assessed"
    assert by_id["eje_cafetero"]["lights_applicable"] is False
    assert by_id["eje_cafetero"]["chip"] == "Analyzed window"
    assert by_id["eje_cafetero"]["buildings"]["typology"] == "unavailable"
    assert by_id["eje_cafetero"]["buildings"]["amount"] == "unavailable"
    quake = next(row for row in by_id["eje_cafetero"]["hazards"] if row["domain"] == "earthquake")
    assert "value_ha" not in json.dumps(quake["extent"])
    assert by_id["la_picacha"]["state"] == "not cached"
    assert by_id["choco_epicenter"]["state"] == "not cached"
    assert by_id["valle_del_cauca"]["state"] == "not cached"
    assert board["lights_applicable"] is False
    assert board["product_kind"] == "mixed"
    assert board["posture"] != "deploy_assessment"
