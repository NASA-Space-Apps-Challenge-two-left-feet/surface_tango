"""Pure prose rendering/cache tests; no measured hazard data is generated."""

import json

import pytest

from agents.bulletin import BADGE, BulletinContractError, Placeholder
from agents.bulletin_runtime import BulletinCache, make_record, serve_record

OUTPUTS = {"eq": {"place": "Comuna 13"}}
SCHEMA = {"eq.place": Placeholder("eq.place")}
TEMPLATES = {"es": "Sin datos para {eq.place}.", "en": "No data for {eq.place}."}
RECIPE = "checker-contract-test"


def test_serving_renders_places_and_badge():
    record = make_record(TEMPLATES, OUTPUTS, SCHEMA, RECIPE)
    served = serve_record(record, OUTPUTS, SCHEMA, RECIPE)
    assert served["badge"] == BADGE
    assert served["citizen_story_es"] == "Sin datos para Comuna 13."
    assert served["decision_maker_brief_en"] == "No data for Comuna 13."


def test_cache_round_trip_and_context_invalidation(tmp_path):
    cache = BulletinCache(tmp_path)
    record = make_record(TEMPLATES, OUTPUTS, SCHEMA, RECIPE)
    cache.store(record, OUTPUTS, SCHEMA, RECIPE)
    restored = cache.load(OUTPUTS, SCHEMA, RECIPE)
    assert serve_record(restored, OUTPUTS, SCHEMA, RECIPE, cached=True)["state"] == "cached"
    assert cache.load({"eq": {"place": "Bello"}}, SCHEMA, RECIPE) is None
    assert cache.load(OUTPUTS, SCHEMA, "different-prompt") is None
    assert cache.load(OUTPUTS, {"eq.place": Placeholder("eq.place", unit="barrio")}, RECIPE) is None


def test_tampered_cache_is_rejected_at_serve_time(tmp_path):
    cache = BulletinCache(tmp_path)
    record = make_record(TEMPLATES, OUTPUTS, SCHEMA, RECIPE)
    cache.store(record, OUTPUTS, SCHEMA, RECIPE)
    path = next(tmp_path.glob("*.json"))
    record["templates"]["en"] = "M7.4"
    path.write_text(json.dumps(record))
    with pytest.raises(BulletinContractError, match="number"):
        cache.load(OUTPUTS, SCHEMA, RECIPE)


def test_stale_record_is_rejected_even_without_cache():
    record = make_record(TEMPLATES, OUTPUTS, SCHEMA, RECIPE)
    with pytest.raises(BulletinContractError):
        serve_record(record, {"eq": {"place": "Bello"}}, SCHEMA, RECIPE)


def test_locale_rounding_uses_declared_rules():
    # Pure formatting input, not an observation; hand-computed decimal output.
    outputs = {"format": {"decimal": "1.255"}}
    schema = {
        "format.decimal": Placeholder(
            "format.decimal",
            unit="test-unit",
            decimal_places=2,
            evidence="estimate",
            denominator="formatting example",
            source=__file__,
        )
    }
    templates = {language: "{format.decimal}" for language in ("es", "en")}
    record = make_record(templates, outputs, schema, RECIPE)
    served = serve_record(record, outputs, schema, RECIPE)
    assert served["citizen_story_es"].startswith("1,26 test-unit")
    assert served["decision_maker_brief_en"].startswith("1.26 test-unit")


@pytest.mark.parametrize("text", ["NaN", "Infinity", "missing"])
def test_invalid_numeric_observations_are_rejected(text):
    outputs = {"format": {"decimal": text}}
    schema = {
        "format.decimal": Placeholder(
            "format.decimal",
            unit="test-unit",
            decimal_places=2,
            evidence="estimate",
            denominator="formatting example",
            source=__file__,
        )
    }
    record = make_record(
        {"es": "{format.decimal}", "en": "{format.decimal}"}, outputs, schema, RECIPE
    )
    with pytest.raises(BulletinContractError):
        serve_record(record, outputs, schema, RECIPE)


def test_delivery_state_does_not_invalidate_identical_evidence(tmp_path):
    from agents.bulletin_runtime import cache_key

    live = {"tool": {"state": "live", "data": {"status": "contract-only"}}}
    cached = {"tool": {"state": "cached", "data": {"status": "contract-only"}}}
    assert cache_key(live, {}, RECIPE) == cache_key(cached, {}, RECIPE)
    cache = BulletinCache(tmp_path)
    prose = {"es": "Prueba de contrato.", "en": "Contract check."}
    record = make_record(prose, live, {}, RECIPE)
    cache.store(record, live, {}, RECIPE)
    restored = cache.load(cached, {}, RECIPE)
    assert serve_record(restored, cached, {}, RECIPE, cached=True)["state"] == "cached"


def test_provenance_change_invalidates_evidence_cache():
    from agents.bulletin_runtime import cache_key

    first = {"tool": {"state": "live", "data": None, "provenance": {"source": "before"}}}
    second = {"tool": {"state": "cached", "data": None, "provenance": {"source": "after"}}}
    assert cache_key(first, {}, RECIPE) != cache_key(second, {}, RECIPE)
