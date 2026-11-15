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
