"""Envelope and wiring tests for the three landslide analysts.

Staged JSON and the tiny grids below are hand-written. They are not observations
and they never reach the app, the distributed cache, or the video. The cache-marked
test reads the real local cube and is skipped by ``make test``.
"""

import asyncio
import json
from pathlib import Path

import numpy as np
import pytest
import zarr

from agents.bulletin_runtime import BulletinCache
from agents.orchestrator import (
    _landslide_aoi,
    _with_landslide_placeholders,
    build_and_run_multi_hazard_graph,
)
from agents.run_plan import DOMAIN_TOOLS, TOOL_ARGUMENTS
from gee_math.landslide_geomorphology import slope_summary
from mcp_servers import evidence
from mcp_servers import gee_fusion_mcp as fusion

ENVELOPE_STATES = {"live", "cached", "not cached", "gate result", "error"}
ANALYST_TOOLS = (
    "analyze_landslide_geology",
    "analyze_landslide_geomorphology",
    "analyze_landslide_hydrogeology",
)
# Same closed form as tests/test_landslide_hydrogeology.py.
GREEN_AMPT_SECONDS = 3068.528194400546
SLOPE = np.array([[0.0, 10.0], [20.0, 30.0]])
HAND = np.array([[1.0, 3.0], [5.0, 7.0]])
RAIN = np.array([[2.0, 4.0], [6.0, 8.0]])


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _stage(root: Path) -> None:
    """One countable geology unit, one terrain cube, and one Culmann profile."""
    aoi = root / "aburra"
    cube = aoi / "aburra_sar_cube.zarr"
    for band, values in (("slope_deg", SLOPE), ("hand_m", HAND), ("rain_15d_mm", RAIN)):
        zarr.save_array(cube / band, values)
    _write(
        aoi / "manifest.json",
        {
            "bands": {
                "slope_deg": {"source_id": "fixture-fabdem", "status": "cached"},
                "hand_m": {"source_id": "fixture-merit-hand", "status": "cached"},
                "rain_15d_mm": {
                    "source_id": "fixture-chirps",
                    "status": "cached",
                    "finite_pixel_count": 4,
                },
            }
        },
    )
    _write(
        aoi / "geology.json",
        {
            "source_ids": ["fixture-sgc-geology"],
            "asset_id": "fixture-geology",
            "dates": ["2020-01-01"],
            "command": "hand-written fixture",
            "units": [
                {"name": "Amaga", "lithology": "arenisca", "pixel_count": 9},
                {"name": "Qcal", "lithology": "coluvion", "pixel_count": 2},
            ],
            "structures": [{"kind": "fault", "name": "Falla Norte", "intersects": True}],
        },
    )
    _write(
        aoi / "photogrammetry.json",
        {
            "source_ids": ["fixture-igac-ortho"],
            "command": "hand-written fixture",
            "control_source_xy_m": [[0.0, 0.0], [10.0, 0.0]],
            "control_target_xy_m": [[1.0, 2.0], [12.0, 2.0]],
            "epoch_xy_m": [[0.0, 0.0], [3.0, 4.0], [6.0, 8.0]],
            "gully_head_distance_m": 10.0,
            "gully_head_delta_days": 365.25,
            "downslope_m": 1.2,
        },
    )
    _write(
        aoi / "landslide_evidence.json",
        {
            "schema": "landslide/1",
            "noise_floor_verdict": {
                "outcome": "no_motion",
                "noise_floor_mm": 9.0,
                "n_pairs": 2,
                "text": "fixture noise floor",
            },
            "provenance": {
                "granule_ids": ["GUNW-FIXTURE"],
                "command": "hand-written fixture",
            },
        },
    )
    _write(
        aoi / "hydro_profile.json",
        {
            "source_ids": ["fixture-hydro-profile"],
            "command": "hand-written fixture",
            "spt_n": 8,
            "stroud_factor": 4.5,
            "cohesion_kpa": 10.0,
            "friction_deg": 30.0,
            "unit_weight_kn_m3": 20.0,
            "slope_deg": 60.0,
            "height_m": 5.0,
            "surcharge_kpa": 10.0,
            "water_table_rise_m": 2.0,
            "failure_depth_m": 0.05,
            "rainfall_m": 0.02,
            "green_ampt": {
                "k_m_s": 1e-5,
                "psi_m": 0.5,
                "delta_theta": 0.2,
                "duration_s": GREEN_AMPT_SECONDS,
            },
        },
    )
    _write(
        aoi / "worldcover.json",
        {
            "source_ids": ["fixture-worldcover"],
            "command": "hand-written fixture",
            "built_fraction": 0.25,
            "surcharge_on_built_kpa": 20.0,
        },
    )


def _invoke(tool, aoi: str) -> dict:
    """Call the wrapped function. FastMCP exposes it as a FunctionTool."""
    function = getattr(tool, "fn", tool)
    return function(aoi)


def _assert_envelope(payload: dict, tool: str) -> None:
    assert set(payload) == set(evidence.ENVELOPE_FIELDS)
    assert payload["tool"] == tool
    assert payload["domain"] == "landslide"
    assert payload["state"] in ENVELOPE_STATES
    assert payload["calibrated"] is False
    json.dumps(payload, allow_nan=False)


def _client_payload(result) -> dict:
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict) and "state" in structured:
        return structured
    data = getattr(result, "data", None)
    if isinstance(data, dict) and "state" in data:
        return data
    raise AssertionError(f"client result has no envelope: {result!r}")


def _requests():
    def arguments(name):
        required, _, _ = TOOL_ARGUMENTS[name]
        return {
            key: [-75.70, 6.12, -75.42, 6.45]
            if key == "bbox"
            else "2026-11-14"
            if key.endswith("_date") or key.endswith("_start") or key.endswith("_end")
            else "transport-check"
            for key in required
        }

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
        "tool_requests": {domain: arguments(tool) for domain, tool in DOMAIN_TOOLS.items()},
        "hazard_reports": {},
    }


class _RecordingTools:
    """Transport stand-in. It records names and returns no measured hazard number."""

    def __init__(self):
        self.calls = []

    async def call(self, server, name, arguments):
        self.calls.append((server, name, arguments))
        if server == "nisar_asf":
            return {"state": "cached", "data": [{"https_url": "transport-check"}]}
        return {"state": "cached", "data": {"contract": "transport-check"}}


def test_staged_fixture_returns_measured_envelopes(monkeypatch, tmp_path):
    monkeypatch.setattr(fusion, "CACHE_ROOT", tmp_path)
    _stage(tmp_path)
    geology = _invoke(fusion.analyze_landslide_geology, "aburra")
    terrain = _invoke(fusion.analyze_landslide_geomorphology, "aburra")
    hydro = _invoke(fusion.analyze_landslide_hydrogeology, "aburra")
    _assert_envelope(geology, "analyze_landslide_geology")
    _assert_envelope(terrain, "analyze_landslide_geomorphology")
    _assert_envelope(hydro, "analyze_landslide_hydrogeology")
    assert geology["state"] == "cached"
    assert geology["data"]["dominant_unit"]["name"] == "Amaga"
    assert geology["data"]["dominant_unit"]["engineering_class"] == "rock"
    assert terrain["state"] == "cached"
    assert terrain["data"]["slope"]["median_deg"] == 15.0
    assert terrain["data"]["slope"]["n_pixels"] == 4
    assert terrain["data"]["hand_m"]["median_m"] == 4.0
    assert terrain["data"]["derivatives"] is None
    assert terrain["data"]["photogrammetry"]["epoch_path"]["path_m"] == 10.0
    assert terrain["data"]["photogrammetry"]["gully_head_retreat_m_per_yr"] == 10.0
    assert terrain["data"]["photo_insar_sign_agreement"] is None
    assert "photo_insar_sign_agreement" in terrain["unavailable"]
    assert hydro["state"] == "cached"
    assert hydro["data"]["wetting_front"]["wetting_front_m"] == pytest.approx(0.1)
    assert hydro["data"]["wetting_front_reaches_failure"] is True
    assert hydro["data"]["effective_stress_change_kpa"] == pytest.approx(-19.62)
    assert hydro["data"]["phi_deg_spt"] == pytest.approx(29.46544)
    assert hydro["data"]["cu_kpa_spt"] == 36.0
    assert hydro["data"]["culmann"]["critical_height_m"] == pytest.approx(11.196152422706637)
    assert hydro["data"]["culmann"]["measurement"] == "estimate"
    assert hydro["data"]["built_up_load"]["surcharge_kpa"] == 5.0
    for aoi_tool in ANALYST_TOOLS:
        missing = _invoke(getattr(fusion, aoi_tool), "la_picacha")
        _assert_envelope(missing, aoi_tool)
        assert missing["state"] == "not cached"
        assert missing["data"] is None
    unknown = _invoke(fusion.analyze_landslide_geology, "mojana")
    _assert_envelope(unknown, "analyze_landslide_geology")
    assert unknown["state"] == "error"


def test_geology_without_source_ids_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(fusion, "CACHE_ROOT", tmp_path)
    _write(tmp_path / "aburra" / "geology.json", {"units": [], "structures": []})
    payload = _invoke(fusion.analyze_landslide_geology, "aburra")
    _assert_envelope(payload, "analyze_landslide_geology")
    assert payload["state"] == "error"


def test_client_serves_aburra_and_la_picacha(monkeypatch, tmp_path):
    monkeypatch.setattr(fusion, "CACHE_ROOT", tmp_path)
    _stage(tmp_path)

    async def check():
        from fastmcp import Client

        async with Client(fusion.mcp) as client:
            names = {tool.name for tool in await client.list_tools()}
            assert set(ANALYST_TOOLS) <= names
            served = {}
            for aoi in ("aburra", "la_picacha"):
                for name in ANALYST_TOOLS:
                    result = await client.call_tool(name, {"aoi": aoi})
                    assert not result.is_error
                    payload = _client_payload(result)
                    _assert_envelope(payload, name)
                    served[(aoi, name)] = payload["state"]
            return served

    served = asyncio.run(check())
    assert served[("aburra", "analyze_landslide_geology")] == "cached"
    assert served[("aburra", "analyze_landslide_geomorphology")] == "cached"
    assert served[("aburra", "analyze_landslide_hydrogeology")] == "cached"
    assert all(served[("la_picacha", name)] == "not cached" for name in ANALYST_TOOLS)


def test_configured_bboxes_resolve_to_their_own_aois():
    assert _landslide_aoi({"bbox": [-75.70, 6.12, -75.42, 6.45]}) == "aburra"
    assert _landslide_aoi({"bbox": [-75.6404, 6.2313, -75.6191, 6.2367]}) == "la_picacha"
    assert _landslide_aoi({"aoi": "la_picacha"}) == "la_picacha"
    assert _landslide_aoi({"bbox": [-70.0, 0.0, -69.0, 1.0]}) == ""


def test_landslide_node_calls_analysts_and_keeps_the_kinematics_state(tmp_path):
    tools = _RecordingTools()

    async def prose(outputs, schema):
        report = outputs["hazards"]["landslide"]
        assert report["state"] == "cached"
        assert report["data"]["contract"] == "transport-check"
        for text in report["interpretation"].values():
            assert not any(character.isdigit() for character in text)
        for item in report["grounding"].values():
            assert item["method"] == "local"
            assert item["state"] in {"unavailable", "live", "error"}
        return {"es": "Sin observaciones disponibles.", "en": "No observations available."}

    result = asyncio.run(
        build_and_run_multi_hazard_graph(
            _requests(),
            tool_client=tools,
            prose_provider=prose,
            cache=BulletinCache(tmp_path),
            recipe="landslide-analysts",
        )
    )
    called = [name for _server, name, _arguments in tools.calls]
    assert "search_nisar_granules" in called
    for name in ANALYST_TOOLS:
        assert ("gee_fusion", name, {"aoi": "aburra"}) in tools.calls
    report = result["hazard_reports"]["landslide"]
    assert report["state"] == "cached"
    assert set(report["analysts"]) == {"geology", "geomorphology", "hydrogeology"}
    assert result["final_bulletin"]["state"] in {"cached", "live"}


def test_placeholders_require_a_finite_scalar_and_a_source():
    key = "hazards.landslide.analysts.geomorphology.data.slope.median_deg"
    sourced = {
        "landslide": {
            "analysts": {
                "geomorphology": {
                    "data": {"slope": {"median_deg": 15.0, "source_ids": ["fixture-fabdem"]}}
                }
            }
        }
    }
    merged = _with_landslide_placeholders({}, sourced)
    assert merged[key].unit == "deg"
    assert merged[key].evidence == "measured"
    assert merged[key].source == "fixture-fabdem"
    bare = {"landslide": {"analysts": {"geomorphology": {"data": {"slope": {"median_deg": 15.0}}}}}}
    assert key not in _with_landslide_placeholders({}, bare)
    missing = {
        "landslide": {
            "analysts": {
                "hydrogeology": {
                    "data": {
                        "wetting_front": {
                            "wetting_front_m": None,
                            "source_ids": ["fixture-hydro-profile"],
                        }
                    }
                }
            }
        }
    }
    front = "hazards.landslide.analysts.hydrogeology.data.wetting_front.wetting_front_m"
    assert front not in _with_landslide_placeholders({}, missing)


@pytest.mark.cache
def test_real_cache_states_match_the_staged_cube():
    """Honest states for the worktree cache. CI does not run this test."""
    slope_path = fusion.CACHE_ROOT / "aburra" / "aburra_sar_cube.zarr" / "slope_deg"
    if not (slope_path / "zarr.json").is_file():
        pytest.skip("aburra slope array is not in this worktree cache")
    geology = _invoke(fusion.analyze_landslide_geology, "aburra")
    terrain = _invoke(fusion.analyze_landslide_geomorphology, "aburra")
    hydro = _invoke(fusion.analyze_landslide_hydrogeology, "aburra")
    for payload, tool in (
        (geology, "analyze_landslide_geology"),
        (terrain, "analyze_landslide_geomorphology"),
        (hydro, "analyze_landslide_hydrogeology"),
    ):
        _assert_envelope(payload, tool)
    assert geology["state"] == "not cached"
    assert terrain["state"] == "cached"
    expected = slope_summary(np.asarray(zarr.open_array(slope_path, mode="r")[:], dtype=np.float64))
    assert terrain["data"]["slope"]["n_pixels"] == expected["n_pixels"]
    assert terrain["data"]["slope"]["n_finite"] == expected["n_finite"]
    assert terrain["data"]["slope"]["median_deg"] == pytest.approx(expected["median_deg"])
    assert terrain["data"]["derivatives"] is None
    assert terrain["data"]["photo_insar_sign_agreement"] is None
    assert hydro["state"] == "gate result"
    assert hydro["data"]["wetting_front"] is None
    assert hydro["data"]["culmann"] is None
    assert hydro["data"]["rainfall"]["n_finite"] == 0
    assert hydro["data"]["rainfall"]["median_mm"] is None
    for name in ANALYST_TOOLS:
        missing = _invoke(getattr(fusion, name), "la_picacha")
        _assert_envelope(missing, name)
        assert missing["state"] == "not cached"
