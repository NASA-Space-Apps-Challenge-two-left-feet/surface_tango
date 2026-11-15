"""The pitch shows only numbers parsed from the merged reports (AGENTS.md: numbers are evidence)."""

import json
from pathlib import Path

import pytest

from video.assemble import read_shots, shot_cards
from video.report_facts import ReportFactError, load_pitch_facts, mojana_facts, render

ROOT = Path(__file__).resolve().parents[1]


def test_facts_keep_their_report_line_and_source():
    facts = load_pitch_facts()
    flood = facts["flood"]
    for key in ("water_pixels", "open_water_ha", "sensitivity_ha", "s1_comparison"):
        fact = flood[key]
        assert fact["kind"] == "measured"
        assert fact["source"].startswith("reports/mojana.md#")
        report = (ROOT / "reports/mojana.md").read_text(encoding="utf-8")
        assert fact["report_line"] in report
    assert facts["landslide"]["noise_floor_mm"]["source"] == "reports/aburra.md#verdict"
    assert facts["landslide"]["exceeds_null"] is False
    assert facts["earthquake"]["scorecard"] == "uninformative"


def test_story_evidence_holds_placeholders_not_numbers():
    evidence = json.loads((ROOT / "static/story-evidence.json").read_text(encoding="utf-8"))
    facts = load_pitch_facts()
    for chapter in evidence.values():
        rendered = render(chapter["summary"], facts)
        assert "{" not in rendered
        template = chapter["summary"]
        for path in chapter.get("facts", []):
            assert "{" + path + "}" in template


def test_a_report_without_the_expected_line_raises(tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports/mojana.md").write_text("# La Mojana\n\n## Reproduce\n", encoding="utf-8")
    with pytest.raises(ReportFactError):
        mojana_facts(tmp_path)


def test_unknown_placeholder_raises():
    with pytest.raises(ReportFactError):
        render("{flood.not_a_fact}", load_pitch_facts())


def test_storyboard_shots_cover_thirty_seconds_and_map_to_cards():
    shots = read_shots()
    assert shots[0].start == 0 and shots[-1].end == 30
    cards = shot_cards(shots, load_pitch_facts())
    assert len(cards) == len(shots)
    assert all(card["vo"].startswith("VO placeholder") for card in cards)


# --- Recorded bulletin and measured flood timeline (the live-run UI surface) ---


def test_bulletin_report_sections_parse():
    from app import parse_bulletin_report

    text = (ROOT / "reports/bulletin_demo.md").read_text(encoding="utf-8")
    sections = parse_bulletin_report(text)
    assert sections["es"].startswith("Terremoto")
    assert sections["en"].startswith("Earthquake")
    assert "glm-5.3" in (sections["serving_model"] or "")


def test_flood_series_serves_measured_counts_only():
    from app import flood_series_entry

    series = flood_series_entry()
    if series is None:
        pytest.skip("flood evidence artifact not staged")
    assert series["state"] in {"live", "gate result"}
    assert series["pixel_area_m2"] == 8100.0
    for entry in series["dates"]:
        assert entry["n_water"] <= entry["n_valid"]
        assert entry["granule_ids"], "every date keeps its granule provenance"
    display = next(entry for entry in series["dates"] if entry["date"] == series["display_date"])
    assert display["n_water"] * series["pixel_area_m2"] / 10000 == pytest.approx(
        series["display_ha"], abs=0.01
    )


@pytest.mark.cache
def test_flood_mask_png_renders_measured_water_pixels():
    import numpy as np
    import rasterio
    from fastapi.testclient import TestClient

    from app import app

    with TestClient(app) as client:
        bounds = client.get("/api/flood-mask", params={"date": "2026-06-17"}).json()
        west, south, east, north = bounds["bounds"]
        assert west < east and south < north
        response = client.get("/api/flood-mask/2026-06-17.png")
        assert response.status_code == 200
        with rasterio.open(__import__("io").BytesIO(response.content)) as mask:
            rgba = mask.read()
        water = rgba[3] > 0
        artifact = json.loads((ROOT / "local_cache/mojana/flood_evidence.json").read_text())
        expected = next(e for e in artifact["dates"] if e["date"] == "2026-06-17")
        assert int(np.count_nonzero(water)) == expected["n_water"]
