"""Locale rendering and revalidated cache for placeholder-only LLM prose."""

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from string import Formatter

from agents.bulletin import (
    BADGE,
    BulletinContractError,
    _lookup,
    check_template,
    tool_output_hash,
)

LANGUAGES = {"es", "en"}


def evidence_outputs(value):
    """Canonicalize delivery labels while retaining payloads and all provenance."""
    if isinstance(value, dict):
        envelope = (
            isinstance(value.get("state"), str)
            and value["state"] in {"live", "cached"}
            and "data" in value
        )
        return {
            key: "available" if envelope and key == "state" else evidence_outputs(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [evidence_outputs(item) for item in value]
    return value


def cache_key(outputs, schema, recipe):
    """Include the integration's model/prompt revision and schema in cache identity."""
    outputs = evidence_outputs(outputs)
    if not recipe:
        raise BulletinContractError("cache requires a model/prompt recipe")
    context = {
        "tool_output_hash": tool_output_hash(outputs),
        "schema": {key: asdict(value) for key, value in schema.items()},
        "recipe": recipe,
    }
    return hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()


def validate_record(record, outputs, schema, recipe):
    outputs = evidence_outputs(outputs)
    if not isinstance(record, dict) or record.get("key") != cache_key(outputs, schema, recipe):
        raise BulletinContractError("bulletin cache context changed")
    templates = record.get("templates")
    if not isinstance(templates, dict) or set(templates) != LANGUAGES:
        raise BulletinContractError("bulletin requires ES and EN prose")
    for template in templates.values():
        if not isinstance(template, str) or not template.strip():
            raise BulletinContractError("bulletin prose must be nonempty text")
        check_template(template, outputs, schema, record.get("tool_output_hash"))


def make_record(templates, outputs, schema, recipe):
    outputs = evidence_outputs(outputs)
    record = {
        "key": cache_key(outputs, schema, recipe),
        "tool_output_hash": tool_output_hash(outputs),
        "templates": dict(templates),
    }
    validate_record(record, outputs, schema, recipe)
    return record


def render_template(template, outputs, schema, language):
    outputs = evidence_outputs(outputs)
    if language not in LANGUAGES:
        raise BulletinContractError("unsupported locale")
    check_template(template, outputs, schema, tool_output_hash(outputs))
    parts = []
    for literal, key, _, _ in Formatter().parse(template):
        parts.append(literal)
        if key is None:
            continue
        value = _lookup(outputs, key)
        spec = schema[key]
        if spec.decimal_places is not None:
            try:
                number = Decimal(str(value))
                if not number.is_finite():
                    raise BulletinContractError("non-finite observation")
                value = format(
                    number.quantize(
                        Decimal(1).scaleb(-spec.decimal_places), rounding=ROUND_HALF_UP
                    ),
                    f".{spec.decimal_places}f",
                )
            except InvalidOperation as exc:
                raise BulletinContractError("invalid numeric observation") from exc
            if language == "es":
                value = value.replace(".", ",")
            value = f"{value} {spec.unit} ({spec.evidence}; {spec.denominator})"
        parts.append(str(value))
    return "".join(parts)


def serve_record(record, outputs, schema, recipe, *, cached=False):
    """Recheck source prose and hashes at serve time, then render fresh text."""
    validate_record(record, outputs, schema, recipe)
    return {
        "state": "cached" if cached else "live",
        "badge": BADGE,
        "tool_output_hash": record["tool_output_hash"],
        "citizen_story_es": render_template(record["templates"]["es"], outputs, schema, "es"),
        "decision_maker_brief_en": render_template(
            record["templates"]["en"], outputs, schema, "en"
        ),
        "sources": {key: spec.source for key, spec in schema.items() if spec.source},
    }


class BulletinCache:
    """Store source prose, never trust previously rendered text."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def load(self, outputs, schema, recipe):
        path = self.directory / f"{cache_key(outputs, schema, recipe)}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            raise BulletinContractError("cannot read bulletin cache") from exc
        validate_record(record, outputs, schema, recipe)
        return record

    def store(self, record, outputs, schema, recipe):
        validate_record(record, outputs, schema, recipe)
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.directory, delete=False
            ) as stream:
                temporary = Path(stream.name)
                json.dump(record, stream, ensure_ascii=False, allow_nan=False)
            os.replace(temporary, self.directory / f"{record['key']}.json")
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
