"""Hand-written prose contracts; no hazard observations or numeric arrays."""

import pytest

from agents.bulletin import (
    BulletinContractError,
    Placeholder,
    check_template,
    tool_output_hash,
    verified_event_values,
)

OUTPUTS = {"eq": {"place": "Comuna 13"}}
SCHEMA = {"eq.place": Placeholder("eq.place")}


def check(text, outputs=OUTPUTS, schema=SCHEMA):
    return check_template(text, outputs, schema, tool_output_hash(outputs))


def test_sensor_names_and_places_use_the_contract():
    assert check("Sentinel-1 y Sentinel-2: {eq.place}") == ("eq.place",)


@pytest.mark.parametrize(
    "text",
    [
        "Comuna 13",
        "M7.4",
        "Sentinel-13",
        "Sentinel-1x",
        "Ⅻ",
        "{eq.place!r}",
        "{eq.place:>10}",
        "{eq[place]}",
        "{missing.key}",
        "{eq.place",
    ],
)
def test_rejects_untrusted_numbers_and_placeholders(text):
    with pytest.raises(BulletinContractError):
        check(text)


def test_hash_check_detects_changed_outputs():
    with pytest.raises(BulletinContractError, match="hash"):
        check_template("{eq.place}", {"eq": {"place": "Bello"}}, SCHEMA, tool_output_hash(OUTPUTS))


def test_missing_observations_are_not_renderable():
    with pytest.raises(BulletinContractError, match="missing"):
        check("{eq.place}", {"eq": {"place": None}})


def test_undeclared_numeric_rounding_is_rejected():
    with pytest.raises(BulletinContractError, match="rounding"):
        check("{eq.place}", {"eq": {"place": len(())}})


def test_unverified_events_cannot_be_used():
    assert verified_event_values({"event": {"status": "unverified"}}) == {}
    with pytest.raises(BulletinContractError, match="primary sources"):
        verified_event_values({"event": {"status": "verified"}})


def test_numeric_spec_requires_evidence():
    with pytest.raises(BulletinContractError):
        Placeholder("eq.precision", decimal_places=len(()))


def test_hash_is_independent_of_key_order():
    assert tool_output_hash({"eq": {}, "flood": {}}) == tool_output_hash({"flood": {}, "eq": {}})
