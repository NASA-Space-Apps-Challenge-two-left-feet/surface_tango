"""Graph control-flow checks using missing-data envelopes only."""

import asyncio

from agents.bulletin import BADGE
from agents.bulletin_runtime import BulletinCache
from agents.orchestrator import DOMAIN_TOOLS, build_and_run_multi_hazard_graph
from agents.run_plan import TOOL_ARGUMENTS


def valid_arguments(name):
    required, _, _ = TOOL_ARGUMENTS[name]
    return {
        key: [-75.70, 6.12, -75.42, 6.45]
        if key == "bbox"
        else "2026-11-14"
        if key.endswith("_date") or key.endswith("_start") or key.endswith("_end")
        else "transport-check"
        for key in required
    }


class MissingTools:
    def __init__(self):
        self.calls = []

    async def call(self, server, name, arguments):
        self.calls.append(name)
        return {"state": "not cached", "error": "not cached"}


class ContractTools(MissingTools):
    async def call(self, server, name, arguments):
        self.calls.append(name)
        # Non-numeric transport marker only, never a hazard measurement.
        if server == "nisar_asf":
            return {"state": "cached", "data": [{"https_url": "transport-check"}]}
        return {"state": "cached", "data": {"contract": "transport-check"}}


def requests():
    return {
        "bbox": [-75.70, 6.12, -75.42, 6.45],
        "start_date": "2026-11-14",
        "end_date": "2026-11-15",
        "ingestion_requests": [
            {
                "tool": "search_nisar_granules",
                "arguments": {
                    "bbox": [-75.70, 6.12, -75.42, 6.45],
                    "start_date": "2026-11-14",
                    "end_date": "2026-11-15",
                },
            }
        ],
        "tool_requests": {domain: valid_arguments(tool) for domain, tool in DOMAIN_TOOLS.items()},
        "hazard_reports": {},
    }


def test_missing_ingestion_skips_downstream_calls_and_prose():
    tools = MissingTools()

    async def prose(*args):
        raise AssertionError("missing observations must not reach prose")

    result = asyncio.run(
        build_and_run_multi_hazard_graph(requests(), tool_client=tools, prose_provider=prose)
    )
    assert tools.calls == ["search_nisar_granules"]
    assert set(result["hazard_reports"]) == set(DOMAIN_TOOLS)
    assert result["final_bulletin"]["state"] == "not cached"


def test_fanin_checks_generation_and_reuses_cached_prose(tmp_path, monkeypatch):
    tools = ContractTools()
    calls = []

    async def prose(outputs, schema):
        assert set(outputs["hazards"]) == set(DOMAIN_TOOLS)
        assert all(name in tools.calls for name in DOMAIN_TOOLS.values())
        calls.append("prose")
        return {"es": "Sin observaciones disponibles.", "en": "No observations available."}

    async def run():
        return await build_and_run_multi_hazard_graph(
            requests(),
            tool_client=tools,
            prose_provider=prose,
            cache=BulletinCache(tmp_path),
            recipe="contract-prose",
        )

    first = asyncio.run(run())
    assert first["final_bulletin"]["badge"] == BADGE
    monkeypatch.setenv("OFFLINE_DEMO_MODE", "1")
    second = asyncio.run(run())
    assert second["final_bulletin"]["state"] == "cached"
    assert calls == ["prose"]
    assert "biomass_agent" not in first


def test_offline_cache_miss_never_calls_prose(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_DEMO_MODE", "1")

    async def prose(*args):
        raise AssertionError("offline must not invoke model")

    result = asyncio.run(
        build_and_run_multi_hazard_graph(
            requests(),
            tool_client=ContractTools(),
            prose_provider=prose,
            cache=BulletinCache(tmp_path),
            recipe="contract-prose",
        )
    )
    assert result["final_bulletin"]["state"] == "not cached"


def test_invalid_generated_prose_is_not_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_DEMO_MODE", "0")

    async def prose(*args):
        return {"es": "M7.4", "en": "M7.4"}

    result = asyncio.run(
        build_and_run_multi_hazard_graph(
            requests(),
            tool_client=ContractTools(),
            prose_provider=prose,
            cache=BulletinCache(tmp_path),
            recipe="contract-prose",
        )
    )
    assert result["final_bulletin"]["state"] == "error"
    assert not list(tmp_path.glob("*.json"))


def test_invalid_tool_state_is_an_explicit_error():
    class InvalidTools(MissingTools):
        async def call(self, *args):
            return {}

    result = asyncio.run(build_and_run_multi_hazard_graph(requests(), tool_client=InvalidTools()))
    assert result["final_bulletin"]["state"] == "error"


def test_model_adapter_returns_only_declared_language_templates():
    from agents.orchestrator import make_prose_provider

    class Model:
        def with_structured_output(self, schema):
            self.schema = schema
            return self

        async def ainvoke(self, messages):
            assert "declared_placeholders" in messages[-1]["content"]
            return self.schema(es="Sin datos.", en="No data.")

    provider = make_prose_provider(Model())
    assert asyncio.run(provider({}, {})) == {"es": "Sin datos.", "en": "No data."}


def test_graph_has_only_the_approved_hazard_nodes():
    from agents.orchestrator import create_compiled_multi_hazard_graph

    graph, _ = asyncio.run(create_compiled_multi_hazard_graph(tool_client=MissingTools()))
    nodes = set(graph.get_graph().nodes)
    assert {"landslide_agent", "earthquake_agent", "flood_caregato_agent"} <= nodes
    assert "biomass_agent" not in nodes


def test_null_payloads_never_reach_prose(tmp_path):
    class NullTools(MissingTools):
        async def call(self, *args):
            return {"state": "cached", "data": None}

    async def prose(*args):
        raise AssertionError("null observations must not reach prose")

    result = asyncio.run(
        build_and_run_multi_hazard_graph(
            requests(),
            tool_client=NullTools(),
            prose_provider=prose,
            cache=BulletinCache(tmp_path),
            recipe="null-contract",
        )
    )
    assert result["final_bulletin"]["state"] == "not cached"
    assert not list(tmp_path.glob("*.json"))


def test_gate_result_survives_the_graph():
    class GateTools(MissingTools):
        async def call(self, *args):
            return {"state": "gate result", "data": {"status": "missing"}}

    result = asyncio.run(build_and_run_multi_hazard_graph(requests(), tool_client=GateTools()))
    assert result["final_bulletin"]["state"] == "gate result"
    assert result["final_bulletin"]["data"] == {"status": "missing"}


def test_graph_reuses_live_warmed_prose_when_tool_delivery_becomes_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFLINE_DEMO_MODE", "0")

    class DeliveryTools(ContractTools):
        mode = "live"

        async def call(self, *args):
            result = await super().call(*args)
            return {**result, "state": self.mode}

    tools = DeliveryTools()
    calls = []

    async def prose(*args):
        calls.append("called")
        return {"es": "Prueba de contrato.", "en": "Contract check."}

    async def run():
        return await build_and_run_multi_hazard_graph(
            requests(),
            tool_client=tools,
            prose_provider=prose,
            cache=BulletinCache(tmp_path),
            recipe="delivery-contract",
        )

    first = asyncio.run(run())
    assert first["final_bulletin"]["state"] == "live"
    tools.mode = "cached"
    monkeypatch.setenv("OFFLINE_DEMO_MODE", "1")
    second = asyncio.run(run())
    assert second["final_bulletin"]["state"] == "cached"
    assert calls == ["called"]


def test_null_domain_payloads_stop_before_prose(tmp_path):
    class DomainNullTools(ContractTools):
        async def call(self, server, name, arguments):
            if server == "gee_fusion":
                return {"state": "live", "data": None}
            return await super().call(server, name, arguments)

    async def prose(*args):
        raise AssertionError("missing domain observations reached prose")

    result = asyncio.run(
        build_and_run_multi_hazard_graph(
            requests(),
            tool_client=DomainNullTools(),
            prose_provider=prose,
            cache=BulletinCache(tmp_path),
            recipe="null-domain",
        )
    )
    assert result["final_bulletin"]["state"] == "not cached"


def test_domain_gate_result_keeps_its_explanation():
    class DomainGateTools(ContractTools):
        async def call(self, server, name, arguments):
            if name == "analyze_earthquake_dpm":
                return {"state": "gate result", "data": {"status": "missing"}}
            return await super().call(server, name, arguments)

    result = asyncio.run(
        build_and_run_multi_hazard_graph(requests(), tool_client=DomainGateTools())
    )
    assert result["final_bulletin"] == {"state": "gate result", "data": {"status": "missing"}}


def test_explicit_scoring_operation_routes_without_rewriting_arguments():
    class ScoringTools(ContractTools):
        async def call(self, server, name, arguments):
            self.calls.append(name)
            if name == "score_against_baseline":
                assert arguments == {"dataset_id": "contract-only"}
                return {"state": "gate result", "reason": "no_evaluated_units"}
            return {"state": "cached", "data": {"contract": "transport-check"}}

    tools = ScoringTools()
    state = requests()
    state["tool_requests"]["earthquake"] = {
        "tool": "score_against_baseline",
        "arguments": {"dataset_id": "contract-only"},
    }
    result = asyncio.run(build_and_run_multi_hazard_graph(state, tool_client=tools))
    assert "score_against_baseline" in tools.calls
    assert "analyze_earthquake_dpm" not in tools.calls
    assert result["final_bulletin"]["reason"] == "no_evaluated_units"


def test_structured_prose_uses_configured_fallback_after_provider_failure():
    from langchain_core.runnables import RunnableLambda

    from agents.orchestrator import make_prose_provider

    attempts = []

    class Model:
        def __init__(self, failing):
            self.failing = failing

        def with_structured_output(self, schema):
            def invoke(messages):
                attempts.append(self.failing)
                if self.failing:
                    raise RuntimeError("provider unavailable")
                return schema(es="Sin datos.", en="No data.")

            return RunnableLambda(invoke)

    provider = make_prose_provider([Model(True), Model(False)])
    assert asyncio.run(provider({}, {})) == {"es": "Sin datos.", "en": "No data."}
    assert attempts == [True, False]
