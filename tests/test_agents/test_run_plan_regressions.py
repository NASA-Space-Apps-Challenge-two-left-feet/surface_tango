"""Regression checks use transport markers, never hazard observations."""

import asyncio
import json

import pytest

from agents.orchestrator import build_and_run_multi_hazard_graph
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


@pytest.mark.parametrize("location", ["plan", "state"])
@pytest.mark.parametrize(
    "defect", ["duplicate", "unknown", "empty_id", "arguments", "domain", "domain_type"]
)
def test_invalid_requests_are_rejected_before_any_tool_effect(tmp_path, location, defect):
    # Regression QA-001, found 2026-11-14: validate all requests before first effect.
    # Value: protects=no tool effect for invalid plans; seam=none.
    document = {
        "context": {"bbox": [], "start_date": "", "end_date": ""},
        "ingestion_requests": [
            {"id": "first", "tool": "search_nisar_granules", "arguments": {}},
            {"id": "second", "tool": "search_nisar_granules", "arguments": {}},
        ],
        "tool_requests": {},
        "placeholders": {},
        "recipe": "invalid-plan-contract",
    }
    state = {**document["context"], "hazard_reports": {}}
    target = document
    if location == "state":
        target = {
            "ingestion_requests": [dict(item) for item in document["ingestion_requests"]],
            "tool_requests": {},
        }
        state.update(target)
    request = target["ingestion_requests"][-1]
    if defect == "duplicate":
        request["id"] = "first"
    elif defect == "unknown":
        request["tool"] = "unapproved-operation"
    elif defect == "empty_id":
        request["id"] = ""
    elif defect == "arguments":
        request["arguments"] = []
    elif defect == "domain":
        target["tool_requests"]["earthquake"] = {"tool": "unapproved-operation", "arguments": {}}
    else:
        target["tool_requests"]["earthquake"] = {"tool": [], "arguments": {}}
    filename = tmp_path / "plan.json"
    filename.write_text(json.dumps(document))

    class Tools:
        calls = []

        async def call(self, server, name, arguments):
            self.calls.append(name)
            return {"state": "cached", "data": {"contract": "transport-check"}}

    tools = Tools()
    result = asyncio.run(
        build_and_run_multi_hazard_graph(state, tool_client=tools, plan_path=filename)
    )
    assert result["final_bulletin"]["state"] == "error"
    assert tools.calls == []


def test_legacy_model_change_cannot_reuse_previous_model_prose(tmp_path, monkeypatch):
    # Regression QA-003, found 2026-11-14: model selection belongs in cache identity.
    from agents import llm
    from agents.bulletin_runtime import BulletinCache
    from agents.run_plan import DOMAIN_TOOLS

    class Model:
        def __init__(self, *, model):
            pass

        def with_structured_output(self, schema):
            self.schema = schema
            return self

        async def ainvoke(self, messages):
            return self.schema(es="Prueba de contrato.", en="Contract check.")

    class Tools:
        async def call(self, server, name, arguments):
            return {"state": "cached", "data": {"contract": "transport-check"}}

    monkeypatch.setattr(
        llm,
        "load_llm_config",
        lambda: {
            "providers": {},
            "chain": [
                {"model": "first-contract-model"},
                {"model": "changed-contract-model"},
            ],
        },
    )
    monkeypatch.setattr(
        llm, "build_models", lambda config: [Model(model=config["chain"][0]["model"])]
    )
    document = {
        "context": {"bbox": [], "start_date": "", "end_date": ""},
        "ingestion_requests": [
            {
                "tool": "search_nisar_granules",
                "arguments": valid_arguments("search_nisar_granules"),
            }
        ],
        "tool_requests": {domain: valid_arguments(tool) for domain, tool in DOMAIN_TOOLS.items()},
        "placeholders": {},
        "recipe": "model-cache-contract",
        "model": "first-contract-model",
    }
    filename = tmp_path / "plan.json"

    def run():
        filename.write_text(json.dumps(document))
        return asyncio.run(
            build_and_run_multi_hazard_graph(
                {**document["context"], "hazard_reports": {}},
                tool_client=Tools(),
                plan_path=filename,
                cache=BulletinCache(tmp_path / "prose"),
            )
        )["final_bulletin"]

    monkeypatch.setenv("OFFLINE_DEMO_MODE", "0")
    assert run()["state"] == "cached"
    monkeypatch.setenv("OFFLINE_DEMO_MODE", "1")
    assert run()["state"] == "cached"
    document["model"] = "changed-contract-model"
    assert run()["state"] == "not cached"


def test_unconfigured_explicit_model_has_no_tool_effects(tmp_path, monkeypatch):
    from agents import llm

    monkeypatch.setattr(llm, "load_llm_config", lambda: {"chain": [], "providers": {}})
    document = {
        "context": {"bbox": [], "start_date": "", "end_date": ""},
        "ingestion_requests": [
            {
                "tool": "search_nisar_granules",
                "arguments": valid_arguments("search_nisar_granules"),
            }
        ],
        "tool_requests": {},
        "placeholders": {},
        "recipe": "invalid-model-contract",
        "model": "unconfigured-contract-model",
    }
    filename = tmp_path / "plan.json"
    filename.write_text(json.dumps(document))

    class Tools:
        async def call(self, *args):
            pytest.fail("unconfigured model selection must fail before tool effects")

    result = asyncio.run(
        build_and_run_multi_hazard_graph(
            {**document["context"], "hazard_reports": {}},
            tool_client=Tools(),
            plan_path=filename,
        )
    )
    assert result["final_bulletin"]["state"] == "error"


@pytest.mark.parametrize(
    "defect",
    [
        "unknown_id",
        "unknown_path",
        "wrong_type",
        "unsafe_url",
        "unsafe_host",
        "unsafe_extension",
        "unsafe_scene",
        "unsafe_pol",
    ],
)
def test_invalid_later_request_prevents_earlier_tool_effect(tmp_path, defect):
    required, _, _ = TOOL_ARGUMENTS["search_nisar_granules"]
    first_arguments = {
        key: [-75.70, 6.12, -75.42, 6.45] if key == "bbox" else "2026-11-14" for key in required
    }
    document = {
        "context": {
            "bbox": [-75.70, 6.12, -75.42, 6.45],
            "start_date": "2026-11-14",
            "end_date": "2026-11-15",
        },
        "ingestion_requests": [
            {"id": "first", "tool": "search_nisar_granules", "arguments": first_arguments},
            {
                "id": "second",
                "tool": (
                    "stage_nisar_gcov_to_gcs"
                    if defect == "unsafe_pol"
                    else "stage_nisar_gunw_ionosphere_corrected_to_gcs"
                ),
                "arguments": {
                    "https_url": {
                        "from_staged": "unknown" if defect == "unknown_id" else "first",
                        "path": [0, "unknown_field"] if defect == "unknown_path" else ["https_url"],
                    }
                    if defect not in {"unsafe_url", "unsafe_host", "unsafe_extension"}
                    else {
                        "unsafe_url": "http://127.0.0.1/private.h5",
                        "unsafe_host": "https://evil.example/private.h5",
                        "unsafe_extension": "https://nisar.asf.earthdatacloud.nasa.gov/not.h5.tif",
                    }[defect],
                    "scene_name": "../escape" if defect == "unsafe_scene" else "scene-from-owner",
                    "bbox": "bad" if defect == "wrong_type" else {"from_context": "bbox"},
                    **({"polarizations": ["../../outside"]} if defect == "unsafe_pol" else {}),
                },
            },
        ],
        "tool_requests": {},
        "placeholders": {},
        "recipe": "preflight-side-effect-regression",
    }
    filename = tmp_path / "plan.json"
    filename.write_text(json.dumps(document))

    class Tools:
        calls = []

        async def call(self, server, name, arguments):
            self.calls.append((server, name))
            return {"state": "live", "data": {"contract": "transport-check"}}

    tools = Tools()
    result = asyncio.run(
        build_and_run_multi_hazard_graph(
            {**document["context"], "hazard_reports": {}},
            tool_client=tools,
            plan_path=filename,
        )
    )
    assert result["final_bulletin"]["state"] == "error"
    assert tools.calls == []


def test_untrusted_staged_url_is_rejected_before_staging_effect(tmp_path):
    document = {
        "context": {
            "bbox": [-75.70, 6.12, -75.42, 6.45],
            "start_date": "2026-11-14",
            "end_date": "2026-11-15",
        },
        "ingestion_requests": [
            {
                "id": "search",
                "tool": "search_nisar_granules",
                "arguments": {
                    "bbox": [-75.70, 6.12, -75.42, 6.45],
                    "start_date": "2026-11-14",
                    "end_date": "2026-11-15",
                },
            },
            {
                "id": "stage",
                "tool": "stage_nisar_gunw_ionosphere_corrected_to_gcs",
                "arguments": {
                    "https_url": {"from_staged": "search", "path": [0, "https_url"]},
                    "scene_name": {"from_staged": "search", "path": [0, "scene_name"]},
                    "bbox": {"from_context": "bbox"},
                },
            },
        ],
        "tool_requests": {},
        "placeholders": {},
        "recipe": "post-resolution-security-check",
    }
    filename = tmp_path / "plan.json"
    filename.write_text(json.dumps(document))

    class MaliciousSearchResult:
        calls = []

        async def call(self, server, name, arguments):
            self.calls.append(name)
            return {
                "state": "live",
                "data": [{"https_url": "https://127.0.0.1/private.h5", "scene_name": "safe"}],
            }

    tools = MaliciousSearchResult()
    result = asyncio.run(
        build_and_run_multi_hazard_graph(
            {**document["context"], "hazard_reports": {}},
            tool_client=tools,
            plan_path=filename,
        )
    )
    assert result["final_bulletin"]["state"] == "error"
    assert tools.calls == ["search_nisar_granules"]
