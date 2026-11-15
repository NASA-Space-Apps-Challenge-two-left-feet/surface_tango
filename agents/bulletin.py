"""Bulletin placeholder contract. Agents supply prose; tools supply evidence."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from string import Formatter

BADGE = "SI-Assisted Analytics"
SENSOR_NAMES = ("Sentinel-1", "Sentinel-2")
KEY = re.compile(r"[a-z][a-z_]*(?:\.[a-z][a-z_0-9]*)+")


class BulletinContractError(ValueError):
    """The bulletin must not be generated or served."""


@dataclass(frozen=True)
class Placeholder:
    """Declared by deterministic tool integration, never by LLM prose.

    Numeric values need a unit, evidence label, denominator and provenance.
    Rounding is per key; locale rendering belongs to the graph integration.
    """

    key: str
    unit: str | None = None
    decimal_places: int | None = None
    evidence: str | None = None
    denominator: str | None = None
    source: str | None = None

    def __post_init__(self):
        if not KEY.fullmatch(self.key):
            raise BulletinContractError("invalid placeholder key")
        if self.decimal_places is not None:
            if type(self.decimal_places) is not int or self.decimal_places < 0:
                raise BulletinContractError("invalid rounding rule")
            if self.evidence not in {"measured", "estimate"}:
                raise BulletinContractError("numeric placeholders need an evidence label")
            if not all((self.unit, self.denominator, self.source)):
                raise BulletinContractError("numeric placeholders need units and provenance")


def tool_output_hash(outputs: Mapping) -> str:
    encoded = json.dumps(outputs, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _lookup(outputs, key):
    value = outputs
    for part in key.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise BulletinContractError(f"missing placeholder: {key}")
        value = value[part]
    if value is None:
        raise BulletinContractError(f"missing observation: {key}")
    if isinstance(value, Mapping | list | tuple | bool):
        raise BulletinContractError(f"placeholder must be a scalar: {key}")
    return value


def check_template(text, outputs, schema, expected_hash):
    """Run on generation and again on cached prose before serving.

    Only exact sensor names bypass the no-digit rule. Places and event facts
    must use declared keys. Formatter conversions and format specs are forbidden.
    """
    if tool_output_hash(outputs) != expected_hash:
        raise BulletinContractError("tool-output hash changed")
    keys = []
    try:
        chunks = list(Formatter().parse(text))
    except ValueError as exc:
        raise BulletinContractError("malformed placeholder") from exc
    for literal, key, spec, conversion in chunks:
        # Boundaries prevent a sensor allow-list match from hiding other digits.
        clean = literal
        for name in SENSOR_NAMES:
            clean = re.sub(r"(?<!\w)" + re.escape(name) + r"(?!\w)", "", clean)
        if any(character.isnumeric() for character in clean):
            raise BulletinContractError("number outside a placeholder")
        if key is None:
            continue
        if not KEY.fullmatch(key) or spec or conversion:
            raise BulletinContractError("invalid placeholder syntax")
        if key not in schema or schema[key].key != key:
            raise BulletinContractError(f"undeclared placeholder: {key}")
        value = _lookup(outputs, key)
        if isinstance(value, int | float) and schema[key].decimal_places is None:
            raise BulletinContractError("numeric value has no rounding rule")
        keys.append(key)
    return tuple(keys)


def verified_event_values(event_facts):
    """Unverified event constants are unavailable to prose and rendering."""
    result = {}
    for event, record in event_facts.items():
        if event.startswith("_") or record.get("status") != "verified":
            continue
        sources = record.get("sources", {})
        if not sources or not all(sources.values()) or not record.get("kb_note"):
            raise BulletinContractError("verified event needs primary sources and KB note")
        result[event] = {
            key: value
            for key, value in record.items()
            if key not in {"status", "sources", "kb_note"} and value is not None
        }
    return result
