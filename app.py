# app.py
import asyncio
import json
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path

import ee
import numpy as np
import xarray as xr
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from rasterio.warp import reproject

from agents.state import MultiHazardGraphState
from gee_math.ee_session import init_ee

app = FastAPI(title="Dancing with the SARs - NISAR Multi-Agent SSE API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CACHE_ROOT = Path(
    os.environ.get("BAILASAR_CACHE_DIR", Path(__file__).resolve().parent / "local_cache")
)
ABURRA_CACHE = CACHE_ROOT / "aburra"
LEGACY_ABURRA_CACHE = CACHE_ROOT / "antioquia_aburra"
STORY_RESULTS = CACHE_ROOT / "story-results.json"
OFFLINE_ASSETS = CACHE_ROOT / "frontend-assets"
ASSET_PATHS = {
    "mission-control.css": "mission-control.css",
    "maplibre-gl.css": "node_modules/maplibre-gl/dist/maplibre-gl.css",
    "maplibre-gl.js": "node_modules/maplibre-gl/dist/maplibre-gl.js",
    "deck.gl.js": "node_modules/deck.gl/dist.min.js",
}
HAZARD_DOMAINS = {"landslide", "flood", "earthquake"}
LANDSLIDE_BAND = "los_disp_mm"


@app.get("/assets/{name}")
def frontend_asset(name: str):
    if name not in ASSET_PATHS:
        raise HTTPException(404, "Unknown frontend asset")
    asset = OFFLINE_ASSETS / ASSET_PATHS[name]
    if not asset.is_file():
        raise HTTPException(404, "Frontend asset not staged")
    return FileResponse(asset)


@app.get("/api/story-results")
def story_results():
    if not STORY_RESULTS.is_file():
        raise HTTPException(404, "Approved story results not staged")
    return FileResponse(STORY_RESULTS, media_type="application/json")


@app.get("/api/panel-gate/{domain}")
def panel_gate(domain: str):
    if domain not in HAZARD_DOMAINS:
        raise HTTPException(404, "Unknown tile domain")
    for cache_dir in (ABURRA_CACHE, LEGACY_ABURRA_CACHE):
        results_path = cache_dir / "gate-panel-results.json"
        if results_path.is_file():
            break
    else:
        return Response(status_code=204)
    results = json.loads(results_path.read_text(encoding="utf-8"))
    statement = results.get(domain)
    if not isinstance(statement, str) or not statement.strip():
        return Response(status_code=204)
    return {"statement": statement.strip()}


@dataclass(frozen=True)
class LandslideTileCache:
    cube: Path
    bbox: list[float]
    granule_id: str
    built_at: str | None


def find_landslide_tile_cache() -> LandslideTileCache | None:
    layouts = (
        (ABURRA_CACHE, "aburra_sar_cube.zarr"),
        (LEGACY_ABURRA_CACHE, "antioquia_sar_cube.zarr"),
    )
    for cache_dir, cube_name in layouts:
        cube_path = cache_dir / cube_name
        manifest_path = cache_dir / "manifest.json"
        if not cube_path.is_dir() or not manifest_path.is_file():
            continue

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source = manifest.get("nisar_granule_provenance", {}).get(LANDSLIDE_BAND)
        if not isinstance(source, str) or source.strip().lower() in {"", "missing"}:
            return None
        band = manifest.get("bands", {}).get(LANDSLIDE_BAND)
        if band is not None and (band.get("status") != "cached" or band.get("source_id") != source):
            return None

        bbox = manifest.get("bbox")
        if (
            not isinstance(bbox, list)
            or len(bbox) != 4
            or not all(isinstance(value, (int, float)) and np.isfinite(value) for value in bbox)
            or not (bbox[0] < bbox[2] and bbox[1] < bbox[3])
        ):
            raise HTTPException(500, "Invalid bounds in the Aburrá cache manifest")

        with xr.open_zarr(cube_path) as cube:
            if LANDSLIDE_BAND not in cube:
                return None
            if set(cube[LANDSLIDE_BAND].dims) != {"x", "y"}:
                raise HTTPException(500, "Invalid dimensions in the Aburrá cache cube")

        built_at = manifest.get("cache_built_at")
        return LandslideTileCache(
            cube_path, bbox, source.strip(), built_at if isinstance(built_at, str) else None
        )
    return None


@app.get("/api/local-tiles/{domain}")
def local_tile_status(domain: str):
    if domain not in HAZARD_DOMAINS:
        raise HTTPException(404, "Unknown tile domain")
    # Comparative products belong to the validated story tile inputs.
    cache = find_landslide_tile_cache() if domain == "landslide" else None
    if cache is None:
        return {"state": "not cached"}
    return {
        "state": "cached",
        "source": "cache",
        "granule_ids": [cache.granule_id],
        "cache_built_at": cache.built_at,
        "tile_url": f"/api/local-tiles/{domain}/{{z}}/{{x}}/{{y}}.png",
    }


@app.get("/api/local-tiles/aburra/{domain}/{z}/{x}/{y}.png")
@app.get("/api/local-tiles/{domain}/{z}/{x}/{y}.png")
def serve_local_zarr_tile(domain: str, z: int, x: int, y: int):
    if not 0 <= z <= 24 or not (0 <= x < 2**z and 0 <= y < 2**z):
        raise HTTPException(404, "Invalid XYZ tile")
    cache = find_landslide_tile_cache() if domain == "landslide" else None
    if cache is None:
        raise HTTPException(404, "Tile data not cached")

    # XYZ addresses divide the Web Mercator world into equal squares.
    half_world = np.pi * 6378137
    span = 2 * half_world / 2**z
    left, top = -half_world + x * span, half_world - y * span
    size = 256
    transform = from_bounds(left, top - span, left + span, top, size, size)
    with xr.open_zarr(cache.cube) as cube:
        source = cube[LANDSLIDE_BAND].transpose("y", "x").values.astype(np.float32, copy=False)
        values = np.full((size, size), np.nan, dtype=np.float32)
        reproject(
            source,
            values,
            src_transform=from_bounds(*cache.bbox, source.shape[1], source.shape[0]),
            src_crs="EPSG:4326",
            src_nodata=np.nan,
            dst_transform=transform,
            dst_crs="EPSG:3857",
            dst_nodata=np.nan,
        )

    # Color intensity is for display only. Preserve missing pixels in alpha.
    rgba = np.zeros((4, size, size), dtype=np.uint8)
    valid = np.isfinite(values)
    signal = values[valid]
    intensity = (np.arctan(np.abs(signal)) * (2 / np.pi) * 255).astype(np.uint8)
    rgba[0, valid] = np.where(signal > 0, intensity, 0)
    rgba[1, valid] = 80
    rgba[2, valid] = np.where(signal <= 0, intensity, 0)
    rgba[3, valid] = 255
    with MemoryFile() as png:
        with png.open(driver="PNG", width=size, height=size, count=4, dtype="uint8") as image:
            image.write(rgba)
        return Response(png.read(), media_type="image/png")


def get_contextual_reference_tiles(bbox: list[float], start_date: str, end_date: str) -> dict:
    """
    Generate Earth Engine XYZ tile URLs for the Sentinel-2 and Sentinel-1 panels.
    """
    init_ee()
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
    if os.environ.get("OFFLINE_DEMO_MODE") != "1":
        try:
            ref_tiles = await asyncio.to_thread(
                get_contextual_reference_tiles, bbox, start_date, end_date
            )
            yield f"event: reference_layers\ndata: {json.dumps(ref_tiles)}\n\n"
        except Exception:
            yield "event: reference_error\ndata: {}\n\n"

    initial_state: MultiHazardGraphState = {
        "region_name": region_name,
        "bbox": bbox,
        "start_date": start_date,
        "end_date": end_date,
        "staged_nisar_assets": {},
        "hazard_reports": {},
        "final_bulletin": None,
    }

    try:
        from agents.orchestrator import create_compiled_multi_hazard_graph

        graph, _mcp_client = await create_compiled_multi_hazard_graph()
        # 2. Stream each LangGraph node update as it finishes executing
        async for update in graph.astream(initial_state, stream_mode="updates"):
            for node_name, node_payload in update.items():
                event_packet = {
                    "node": node_name,
                    "payload": node_payload,
                }
                yield f"event: agent_update\ndata: {json.dumps(event_packet)}\n\n"
    except Exception:
        yield 'event: error\ndata: {"detail":"The hazard scan failed."}\n\n'
        return
    yield 'event: complete\ndata: {"status":"DAG_FINISHED"}\n\n'


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
