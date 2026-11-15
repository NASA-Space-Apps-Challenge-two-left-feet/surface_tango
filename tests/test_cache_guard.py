"""Offline contract and latency regression checks; no remote data is created."""

import json
from threading import Event

import pytest

from mcp_servers import cache_guard as guard


def configure(monkeypatch, tmp_path, offline=False):
    monkeypatch.setattr(guard, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("OFFLINE_DEMO_MODE", "1" if offline else "0")
    monkeypatch.setattr(
        guard, "operational_config", lambda: {"breaker_budgets_s": {"default": 0.02}}
    )


def test_offline_miss_never_calls_live(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path, offline=True)

    @guard.with_offline_zarr_fallback()
    def tool(region):
        pytest.fail("offline mode invoked live tool")

    assert tool("aburra")["state"] == "not cached"


def test_timeout_returns_before_worker_and_blocks_repeat(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    release = Event()
    calls = []

    @guard.with_offline_zarr_fallback()
    def tool():
        calls.append("started")
        release.wait(timeout=2)
        return None

    try:
        assert tool()["state"] == "not cached"
        assert not release.is_set()
        assert tool()["state"] == "not cached"
        assert calls == ["started"]
    finally:
        release.set()


def test_cache_matches_arguments_and_requires_provenance(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path, offline=True)

    def source(region="aburra"):
        return None

    key = guard.request_key(source, (), {})
    assert key == guard.request_key(source, (), {"region": "aburra"})
    directory = tmp_path / "source"
    directory.mkdir()
    record = {"request_key": key, "tool": "source", "data": {"status": "missing"}, "provenance": {}}
    output = directory / f"{key}.json"
    output.write_text(json.dumps(record))
    assert guard.cached_output("source", key)["state"] == "not cached"
    # Test metadata describes a missing observation, not a generated scene.
    record["provenance"] = {
        "source": "tests/test_cache_guard.py",
        "granule_ids": ["missing"],
        "cache_build_time": "2026-11-14T00:00:00Z",
    }
    output.write_text(json.dumps(record))
    tool = guard.with_offline_zarr_fallback()(source)
    assert tool()["data"] == {"status": "missing"}
    assert tool("mojana")["state"] == "not cached"


def test_live_failure_redacts_exception(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)

    @guard.with_offline_zarr_fallback()
    def tool():
        raise RuntimeError("private remote error")

    assert tool() == {"state": "error", "error": "live tool failed", "tool": "tool"}


def test_budget_and_live_null(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)

    @guard.with_offline_zarr_fallback()
    def tool():
        return None

    assert tool() == {"state": "live", "data": None}
    monkeypatch.setattr(
        guard, "operational_config", lambda: {"breaker_budgets_s": {"default": False}}
    )
    with pytest.raises(ValueError):
        tool()


def test_sse_ports_come_from_config(monkeypatch):
    calls = []

    class Server:
        def run(self, **kwargs):
            calls.append(kwargs)

    for name in ("nisar_asf", "gee_fusion"):
        guard.run_server(Server(), name)
    config = guard.operational_config()["mcp"]
    assert [call["port"] for call in calls] == list(config["ports"].values())
    assert all(call["transport"] == "sse" for call in calls)


def test_malformed_provenance_is_a_miss(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path, offline=True)
    directory = tmp_path / "tool"
    directory.mkdir()
    (directory / "key.json").write_text(
        json.dumps({"tool": "tool", "request_key": "key", "provenance": "broken", "data": None})
    )
    assert guard.cached_output("tool", "key")["state"] == "not cached"


def test_registered_tools_return_offline_envelopes(monkeypatch, tmp_path):
    import asyncio

    from fastmcp import Client

    from mcp_servers.gee_fusion_mcp import mcp as gee
    from mcp_servers.nisar_asf_mcp import mcp as asf

    configure(monkeypatch, tmp_path, offline=True)

    async def check():
        for server, name, arguments in (
            (asf, "search_nisar_granules", {"bbox": [], "start_date": "", "end_date": ""}),
            (
                gee,
                "analyze_earthquake_dpm",
                {
                    "coh_pre_gcs": "",
                    "coh_coseismic_gcs": "",
                    "goff_range_gcs": "",
                    "goff_azimuth_gcs": "",
                    "bbox": [],
                },
            ),
        ):
            async with Client(server) as client:
                tools = await client.list_tools()
                assert name in {tool.name for tool in tools}
                result = await client.call_tool(name, arguments)
                assert not result.is_error
                assert "not cached" in str(result)

    asyncio.run(check())
