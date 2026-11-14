# app.py
import asyncio
import json
from collections.abc import AsyncGenerator

import ee
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agents.orchestrator import create_compiled_multi_hazard_graph
from agents.state import MultiHazardGraphState
from gee_math.ee_session import init_ee

app = FastAPI(title="Dancing with the SARs - NISAR Multi-Agent SSE API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_ee()  # ADC identity + GCP_PROJECT_ID (gee_math/ee_session.py)


def get_contextual_reference_tiles(bbox: list[float], start_date: str, end_date: str) -> dict:
    """
    Generates Google Earth Engine XYZ tile URLs for Panel 1 (Sentinel-2 optical, showing cloud
    cover) and Panel 2 (Sentinel-1 C-band 5.6 cm VV/VH, showing canopy attenuation) to contrast
    with Panel 3 (NISAR L-band 24 cm).
    """
    aoi = ee.Geometry.Rectangle(bbox)

    # Panel 1: Sentinel-2 optical RGB, cloudy scenes kept as served
    # TODO(frontend, #37): select scenes by a stated rule (date window + scene IDs), not to
    # favour SAR; a cherry-picked cloudy scene would misrepresent the comparison.
    s2_optical = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .median()
        .clip(aoi)
    )
    s2_map = s2_optical.getMapId({"bands": ["B4", "B3", "B2"], "min": 200, "max": 3200})

    # Panel 2: Sentinel-1 C-band (5.6 cm wavelength) VV backscatter
    s1_cband = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .select("VV")
        .median()
        .clip(aoi)
    )
    s1_map = s1_cband.getMapId(
        {"min": -22, "max": -2, "palette": ["0b132b", "1c2541", "3a506b", "5bc0be", "ffffff"]}
    )

    return {
        "optical_s2_tile_url": s2_map["tile_fetcher"].url_format,
        "cband_s1_tile_url": s1_map["tile_fetcher"].url_format,
    }


async def stream_agent_dag_events(
    region_name: str,
    bbox: list[float],
    start_date: str,
    end_date: str,
) -> AsyncGenerator[str, None]:
    """Streams real-time LangGraph node completions and GEE tile URLs via SSE."""
    # 1. Immediately stream baseline Optical & C-band reference tiles for the 3-panel slider
    ref_tiles = await asyncio.to_thread(get_contextual_reference_tiles, bbox, start_date, end_date)
    yield f"event: reference_layers\ndata: {json.dumps(ref_tiles)}\n\n"

    initial_state: MultiHazardGraphState = {
        "region_name": region_name,
        "bbox": bbox,
        "start_date": start_date,
        "end_date": end_date,
        "staged_nisar_assets": {},
        "hazard_reports": {},
        "final_bulletin": None,
    }

    graph, mcp_client = await create_compiled_multi_hazard_graph()

    try:
        # 2. Stream each LangGraph node update as it finishes executing
        async for update in graph.astream(initial_state, stream_mode="updates"):
            for node_name, node_payload in update.items():
                event_packet = {
                    "node": node_name,
                    "payload": node_payload,
                }
                yield f"event: agent_update\ndata: {json.dumps(event_packet)}\n\n"
    except Exception as exc:
        yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
    finally:
        yield f"event: complete\ndata: {json.dumps({'status': 'DAG_FINISHED'})}\n\n"


@app.get("/api/stream-hazards")
async def stream_hazards(
    region_name: str = Query("Valle de Aburrá - Bello & Medellín Northern Slopes"),
    min_lon: float = Query(-75.63),
    min_lat: float = Query(6.22),
    max_lon: float = Query(-75.50),
    max_lat: float = Query(6.38),
    start_date: str = Query("2026-09-01"),
    end_date: str = Query("2026-11-13"),
):
    bbox = [min_lon, min_lat, max_lon, max_lat]
    return StreamingResponse(
        stream_agent_dag_events(region_name, bbox, start_date, end_date),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def serve_ui():
    return FileResponse("static/index.html")
