"""Latency policy/control checks use hand-written arrays, never live timings."""

from copy import deepcopy
from pathlib import Path

import pytest

from mcp_servers import tool_latency as latency

ROOT = Path(__file__).resolve().parents[1]


def test_linear_p95_policy_and_full_sample_requirement():
    samples = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    result = latency.summarize(samples)
    assert result["p95_s"] == pytest.approx(9.55)
    assert result["budget_s"] == pytest.approx(10.05)
    assert result["range_s"] == [1, 10]
    assert result["interval"] is None
    with pytest.raises(latency.PlanError):
        latency.summarize(samples[:-1])


@pytest.mark.parametrize("state", ["cached", "gate result", "not cached", "error"])
def test_nonlive_responses_never_produce_live_budget_samples(state):
    with pytest.raises(latency.PlanError):
        latency.validate_response("analyze_earthquake_dpm", {"state": state, "data": None}, [])


def test_empty_catalog_is_a_real_coverage_result_but_empty_science_is_not():
    assert latency.validate_response("search_nisar_granules", [], []) == []
    with pytest.raises(latency.PlanError):
        latency.validate_response("analyze_flood_inundation", {}, [])


def test_preflight_only_reads_sources_and_does_not_import_live_servers(monkeypatch):
    def forbidden(*args):
        pytest.fail("preflight imported a live/authenticating module")

    monkeypatch.setattr(latency.importlib, "import_module", forbidden)
    plan = latency.read_json(ROOT / "reports/tool_latency_plan.json")
    result = latency.preflight(plan)
    search = next(item for item in result if item["tool"] == "search_nisar_granules")
    assert search["status"] == "ready"
    assert search["arguments"]["bbox"]
    assert all("server_bootstrap_incomplete" not in item["blockers"] for item in result)


def test_budget_writer_cannot_change_config_without_real_complete_evidence(tmp_path):
    filename = tmp_path / "bailasar.yaml"
    original = (ROOT / "config/bailasar.yaml").read_text()
    filename.write_text(original)
    with pytest.raises(latency.PlanError):
        latency.apply_budgets(
            filename, [{"tool": "search_nisar_granules", "status": "failed", "budget_s": None}]
        )
    assert filename.read_text() == original


def test_budget_writer_preserves_other_operational_settings(tmp_path):
    import yaml

    filename = tmp_path / "bailasar.yaml"
    original = (ROOT / "config/bailasar.yaml").read_text()
    filename.write_text(original)
    before = yaml.safe_load(original)
    expected = deepcopy(before)
    samples = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    record = {
        "tool": "search_nisar_granules",
        "status": "measured",
        "samples_s": samples,
        **latency.summarize(samples),
    }
    latency.apply_budgets(filename, [record])
    expected["breaker_budgets_s"]["search_nisar_granules"] = record["budget_s"]
    assert yaml.safe_load(filename.read_text()) == expected


def test_error_messages_do_not_escape_measurement_worker(monkeypatch):
    class Module:
        def search_nisar_granules(self):
            raise RuntimeError("sensitive diagnostic must not be returned")

    monkeypatch.setattr(latency.importlib, "import_module", lambda name: Module())
    result = latency.measure_raw(
        {"server": "nisar_asf", "tool": "search_nisar_granules", "arguments": {}, "granule_ids": []}
    )
    assert result["failure_type"] == "RuntimeError"
    assert "sensitive diagnostic" not in str(result)
    assert result["budget_s"] is None


def test_inconsistent_budget_cannot_be_applied(tmp_path):
    filename = tmp_path / "bailasar.yaml"
    original = (ROOT / "config/bailasar.yaml").read_text()
    filename.write_text(original)
    samples = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    result = {
        "tool": "search_nisar_granules",
        "status": "measured",
        "samples_s": samples,
        "budget_s": 1,
    }
    with pytest.raises(latency.PlanError, match="does not match"):
        latency.apply_budgets(filename, [result])
    assert filename.read_text() == original


def test_raw_worker_unwraps_cache_and_collects_the_full_call_set(monkeypatch):
    import functools
    from types import SimpleNamespace

    calls, cache_calls = [], []

    def raw():
        calls.append("live-operation")
        return []

    @functools.wraps(raw)
    def cached_wrapper():
        cache_calls.append("unexpected-cache")
        return {"state": "cached", "data": []}

    # Hand-written clock pairs produce exact durations; never a live benchmark.
    readings = iter([0, 1, 1, 3, 3, 6, 6, 10, 10, 15, 15, 21, 21, 28, 28, 36, 36, 45, 45, 55])
    monkeypatch.setattr(latency, "perf_counter", lambda: next(readings))
    monkeypatch.setattr(
        latency.importlib,
        "import_module",
        lambda name: SimpleNamespace(search_nisar_granules=cached_wrapper),
    )
    result = latency.measure_raw(
        {"server": "nisar_asf", "tool": "search_nisar_granules", "arguments": {}, "granule_ids": []}
    )
    assert result["status"] == "measured"
    assert result["samples_s"] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert len(calls) == len(result["samples_s"])
    assert cache_calls == []
