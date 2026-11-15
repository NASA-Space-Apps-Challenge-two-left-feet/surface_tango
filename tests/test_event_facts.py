"""Display-policy checks against the actual primary-source event record."""

import json
from decimal import ROUND_HALF_UP, Decimal
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


def _facts():
    return json.loads((ROOT / "validation/event_facts.json").read_text(encoding="utf-8"))


def test_evidence_and_verification_notes_cannot_reach_prose():
    values = verified_event_values(_facts())
    assert "quake_2026_08_10" in values
    assert all(not key.startswith("_") for key in values)
    assert set(values["quake_2026_08_10"]) == {
        "date",
        "magnitude_mw",
        "magnitude_type",
        "epicenter",
        "depth_km",
    }


def test_depth_is_the_rounded_usgs_preferred_origin_estimate_only():
    facts = _facts()
    evidence = facts["_evidence"]["quake_2026_08_10"]["depth_km"]
    usgs = evidence["usgs_preferred_origin"]
    assert evidence["classification"] == "estimate"
    assert evidence["label"] == "USGS estimate"
    assert evidence["unit"] == "km"
    assert usgs["field"].startswith("products.origin[0]") and "source us" in usgs["field"]
    expected = int(Decimal(str(usgs["value"])).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    shown = verified_event_values(facts)["quake_2026_08_10"]["depth_km"]
    assert type(shown) is int and shown == expected
    # The SGC bulletin is evidence only; its value must never be the displayed depth.
    assert shown != round(evidence["sgc_manual_bulletin"]["value"])


def test_depth_placeholder_needs_rounding_unit_and_estimate_label():
    facts = _facts()
    outputs = {"events": verified_event_values(facts)}
    key = "events.quake_2026_08_10.depth_km"
    with pytest.raises(BulletinContractError, match="rounding"):
        check_template("{" + key + "}", outputs, {key: Placeholder(key)}, tool_output_hash(outputs))
    usgs = facts["_evidence"]["quake_2026_08_10"]["depth_km"]["usgs_preferred_origin"]
    spec = Placeholder(
        key,
        unit="km",
        decimal_places=0,
        evidence="estimate",
        denominator="USGS event us6000tjl2, preferred origin",
        source=usgs["source"],
    )
    assert check_template("{" + key + "}", outputs, {key: spec}, tool_output_hash(outputs)) == (
        key,
    )


def test_primary_source_magnitude_still_requires_numeric_display_evidence():
    outputs = {"events": verified_event_values(_facts())}
    key = "events.quake_2026_08_10.magnitude_mw"
    with pytest.raises(BulletinContractError, match="rounding"):
        check_template("{" + key + "}", outputs, {key: Placeholder(key)}, tool_output_hash(outputs))
