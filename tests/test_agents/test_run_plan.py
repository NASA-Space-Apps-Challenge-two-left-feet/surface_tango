"""Run-plan routing tests contain transport markers, never hazard observations."""

import asyncio
import json

import pytest

from agents.bulletin import BulletinContractError
from agents.bulletin_runtime import BulletinCache
from agents.orchestrator import DOMAIN_TOOLS, build_and_run_multi_hazard_graph
from agents.run_plan import TOOL_ARGUMENTS, load_run_plan, resolve_arguments


def valid_arguments(name, *, references=False):
    required, _, _ = TOOL_ARGUMENTS[name]
    return {
        key: (
            {"from_staged": "reference", "path": [0, "https_url"]}
            if references and key != "bbox"
            else [-75.70, 6.12, -75.42, 6.45]
            if key == "bbox"
            else "2026-11-14"
            if key.endswith("_date") or key.endswith("_start") or key.endswith("_end")
            else "transport-check"
        )
        for key in required
    }


def plan():
    return {
        "context": {
            "bbox": [-75.70, 6.12, -75.42, 6.45],
            "start_date": "2026-11-14",
            "end_date": "2026-11-15",
        },
        "ingestion_requests": [
            {
                "id": "reference",
                "tool": "search_nisar_granules",
                "arguments": {
                    "bbox": [-75.70, 6.12, -75.42, 6.45],
                    "start_date": "2026-11-14",
                    "end_date": "2026-11-15",
                },
            }
        ],
        "tool_requests": {
            domain: valid_arguments(DOMAIN_TOOLS[domain], references=True)
            for domain in DOMAIN_TOOLS
        },
        "placeholders": {},
        "recipe": "routing-contract",
    }


class Tools:
    def __init__(self):
        self.calls = []

    async def call(self, server, name, arguments):
        self.calls.append((server, arguments))
        if server == "gee_fusion":
            assert all(
                value == [-75.70, 6.12, -75.42, 6.45]
                if key == "bbox"
                else value == "transport-check"
                for key, value in arguments.items()
            )
            return {"state": "cached", "data": {"contract": "transport-check"}}
        return {"state": "cached", "data": [{"https_url": "transport-check"}]}


def test_plan_supplies_requests_and_resolves_staged_arguments(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_DEMO_MODE", "0")
    document = plan()
    filename = tmp_path / "plan.json"
    filename.write_text(json.dumps(document))
    tools = Tools()

    async def prose(*args):
        return {"es": "Prueba de contrato.", "en": "Contract check."}

    result = asyncio.run(
        build_and_run_multi_hazard_graph(
            {**document["context"], "hazard_reports": {}},
            tool_client=tools,
            plan_path=filename,
            prose_provider=prose,
            cache=BulletinCache(tmp_path / "prose"),
        )
    )
    assert result["final_bulletin"]["state"] == "cached"
    assert (
        result["staged_nisar_assets"]["data"]["reference"]["data"][0]["https_url"]
        == "transport-check"
    )


def test_plan_context_mismatch_prevents_every_tool_call(tmp_path):
    filename = tmp_path / "plan.json"
    filename.write_text(json.dumps(plan()))
    tools = Tools()
    result = asyncio.run(
        build_and_run_multi_hazard_graph(
            {"hazard_reports": {}}, tool_client=tools, plan_path=filename
        )
    )
    assert result["final_bulletin"]["state"] == "error"
    assert tools.calls == []


def test_missing_reference_is_never_defaulted():
    with pytest.raises(BulletinContractError):
        resolve_arguments({"from_staged": "missing", "path": ["contract"]}, {}, {})
    with pytest.raises(BulletinContractError):
        resolve_arguments({"from_context": "bbox"}, {}, {})


def test_missing_and_invalid_plans(tmp_path):
    assert load_run_plan(tmp_path / "absent.json") is None
    filename = tmp_path / "plan.json"
    filename.write_text("{}")
    with pytest.raises(BulletinContractError):
        load_run_plan(filename)


def test_repeated_tool_calls_require_distinct_ids(tmp_path):
    document = plan()
    document["ingestion_requests"] *= 2
    filename = tmp_path / "plan.json"
    filename.write_text(json.dumps(document))
    tools = Tools()
    result = asyncio.run(
        build_and_run_multi_hazard_graph(
            {**document["context"], "hazard_reports": {}}, tool_client=tools, plan_path=filename
        )
    )
    assert result["final_bulletin"]["state"] == "error"
    assert tools.calls == []


def test_default_app_factory_uses_staged_plan_and_cached_prose(tmp_path, monkeypatch):
    from agents import orchestrator

    monkeypatch.setenv("OFFLINE_DEMO_MODE", "0")
    monkeypatch.setattr(orchestrator, "ROOT", tmp_path)
    tools = Tools()
    monkeypatch.setattr(orchestrator, "SSETools", lambda: tools)
    (tmp_path / "local_cache").mkdir()
    (tmp_path / "validation").mkdir()
    (tmp_path / "validation/event_facts.json").write_text("{}")
    document = plan()
    (tmp_path / "local_cache/agent_run_plan.json").write_text(json.dumps(document))
    initial = {**document["context"], "hazard_reports": {}}

    async def prose(*args):
        return {"es": "Prueba de contrato.", "en": "Contract check."}

    async def run():
        await build_and_run_multi_hazard_graph(initial, prose_provider=prose)
        monkeypatch.setenv("OFFLINE_DEMO_MODE", "1")
        graph, _ = await orchestrator.create_compiled_multi_hazard_graph()
        return await graph.ainvoke(initial)

    result = asyncio.run(run())
    assert result["final_bulletin"]["state"] == "cached"
    assert result["final_bulletin"]["decision_maker_brief_en"] == "Contract check."


def test_malformed_ingestion_plan_is_rejected_before_tool_calls(tmp_path):
    document = plan()
    document["ingestion_requests"] = ["not a request object"]
    filename = tmp_path / "plan.json"
    filename.write_text(json.dumps(document))
    tools = Tools()
    result = asyncio.run(
        build_and_run_multi_hazard_graph(
            {**document["context"], "hazard_reports": {}}, tool_client=tools, plan_path=filename
        )
    )
    assert result["final_bulletin"]["state"] == "error"
    assert tools.calls == []


def test_unapproved_domain_operation_is_rejected_before_any_tool_call(tmp_path):
    document = plan()
    document["tool_requests"]["earthquake"] = {"tool": "unknown", "arguments": {}}
    filename = tmp_path / "plan.json"
    filename.write_text(json.dumps(document))
    tools = Tools()
    result = asyncio.run(
        build_and_run_multi_hazard_graph(
            {**document["context"], "hazard_reports": {}}, tool_client=tools, plan_path=filename
        )
    )
    assert result["final_bulletin"]["state"] == "error"
    assert tools.calls == []


def test_configured_chain_is_lazy_and_offline_cache_tracks_its_recipe(tmp_path, monkeypatch):
    from agents import llm

    document = plan()
    document["llm"] = "configured"
    filename = tmp_path / "plan.json"
    filename.write_text(json.dumps(document))
    configuration = {"chain": [], "providers": {}}
    monkeypatch.setattr(llm, "load_llm_config", lambda: configuration)

    class Model:
        def with_structured_output(self, schema, **kwargs):
            self.schema = schema
            return self

        async def ainvoke(self, messages):
            return self.schema(es="Prueba de contrato.", en="Contract check.")

    monkeypatch.setenv("OFFLINE_DEMO_MODE", "0")
    monkeypatch.setattr(llm, "build_models", lambda config: [Model()])

    def run():
        return asyncio.run(
            build_and_run_multi_hazard_graph(
                {**document["context"], "hazard_reports": {}},
                tool_client=Tools(),
                plan_path=filename,
                cache=BulletinCache(tmp_path / "prose"),
            )
        )

    assert run()["final_bulletin"]["state"] == "cached"
    monkeypatch.setenv("OFFLINE_DEMO_MODE", "1")

    def forbidden(*args):
        pytest.fail("offline synthesis constructed a paid provider")

    monkeypatch.setattr(llm, "build_models", forbidden)
    assert run()["final_bulletin"]["state"] == "cached"
    configuration["chain"].append({"model": "changed-contract"})
    assert run()["final_bulletin"]["state"] == "not cached"


def test_ambiguous_provider_plan_is_rejected(tmp_path):
    document = plan()
    document.update(llm="configured", model="explicit-model")
    filename = tmp_path / "plan.json"
    filename.write_text(json.dumps(document))
    with pytest.raises(BulletinContractError, match="configured LLM"):
        load_run_plan(filename)
