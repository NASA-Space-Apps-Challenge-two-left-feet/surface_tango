"""Display-policy checks against the actual primary-source event record."""

import json
from pathlib import Path

import pytest

from agents.bulletin import (
    BulletinContractError,
    Placeholder,
    check_template,
    tool_output_hash,
    verified_event_values,
)

ROOT = Path(__file__).resolve().parents[1]


def test_unresolved_depth_and_verification_notes_cannot_reach_prose():
    facts = json.loads((ROOT / "validation/event_facts.json").read_text(encoding="utf-8"))
    values = verified_event_values(facts)
    assert "quake_2026_08_10" in values
    assert all(not key.startswith("_") for key in values)
    assert "depth_km" not in values["quake_2026_08_10"]
    assert set(values["quake_2026_08_10"]) == {
        "date",
        "magnitude_mw",
        "magnitude_type",
        "epicenter",
    }


def test_primary_source_magnitude_still_requires_numeric_display_evidence():
    facts = json.loads((ROOT / "validation/event_facts.json").read_text(encoding="utf-8"))
    outputs = {"events": verified_event_values(facts)}
    key = "events.quake_2026_08_10.magnitude_mw"
    with pytest.raises(BulletinContractError, match="rounding"):
        check_template("{" + key + "}", outputs, {key: Placeholder(key)}, tool_output_hash(outputs))
