"""The flood telemetry row must follow the graph node name."""

from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "static" / "index.html"


def test_flood_caregato_event_marks_the_flood_row():
    page = PAGE.read_text(encoding="utf-8")
    handler = page.split('addEventListener("agent_update"', 1)[1].split(
        'addEventListener("complete"', 1
    )[0]
    assert 'id="node-flood_agent"' in page
    assert 'node === "flood_caregato_agent" ? "flood_agent"' in handler
    assert "unfinishedNodes.delete(badgeId)" in handler
    assert 'markNodeBadge(badgeId, "DONE ✓"' in handler
