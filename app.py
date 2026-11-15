# app.py
import asyncio
import json
import os
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path

import ee
import numpy as np
import rasterio
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
from video.report_facts import ReportFactError, load_pitch_facts

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
    "jost-500.woff2": "node_modules/@fontsource/jost/files/jost-latin-500-normal.woff2",
    "jost-600.woff2": "node_modules/@fontsource/jost/files/jost-latin-600-normal.woff2",
    "caslon-400.woff2": "node_modules/@fontsource/libre-caslon-text/files/libre-caslon-text-latin-400-normal.woff2",
    "caslon-400-italic.woff2": "node_modules/@fontsource/libre-caslon-text/files/libre-caslon-text-latin-400-italic.woff2",
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
    media = "font/woff2" if name.endswith(".woff2") else None
    return FileResponse(asset, media_type=media)


SENTINEL_AOIS = {"aburra", "eje_cafetero", "mojana"}
SENTINEL_LAYERS = {"s1": "cband_s1", "s2": "optical_s2"}


def sentinel_manifest(aoi: str) -> tuple[Path, dict]:
    if aoi not in SENTINEL_AOIS:
        raise HTTPException(404, "Unknown Sentinel tile area")
    tiles = CACHE_ROOT / aoi / "tiles"
    path = tiles / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if manifest and manifest.get("aoi") != aoi:
        raise HTTPException(500, "Sentinel manifest does not match the area")
    return tiles, manifest


def cached_sentinel_layer(manifest: dict, layer: str) -> dict | None:
    entry = manifest.get("layers", {}).get(SENTINEL_LAYERS[layer], {})
    scene_ids = entry.get("scene_ids")
    if (
        entry.get("status") == "cached"
        and isinstance(scene_ids, list)
        and scene_ids
        and all(isinstance(scene, str) and scene.strip() for scene in scene_ids)
        and entry.get("tiles", {}).get("written", 0) > 0
    ):
        return entry
    return None


@app.get("/api/sentinel-tiles/{aoi}")
def sentinel_tile_status(aoi: str):
    tiles, manifest = sentinel_manifest(aoi)
    panels = {}
    for layer in SENTINEL_LAYERS:
        entry = cached_sentinel_layer(manifest, layer)
        if entry is None or not next((tiles / layer).glob("*/*/*.png"), None):
            panels[layer] = {"state": "not cached"}
            continue
        panels[layer] = {
            "state": "cached",
            "source": "cache",
            "scene_ids": entry["scene_ids"],
            "date": entry.get("date"),
            # Share of the AOI the mosaic imaged, as measured by the tile prestage.
            "coverage_pct": entry.get("coverage_pct"),
            "cache_built_at": manifest.get("generated_utc"),
            "tile_url": f"/api/sentinel-tiles/{aoi}/{layer}/{{z}}/{{x}}/{{y}}.png",
            "bounds": manifest["bbox_wsen"],
            "minzoom": manifest["zoom"]["min"],
            "maxzoom": manifest["zoom"]["max"],
        }
    return panels


@app.get("/api/sentinel-tiles/{aoi}/{layer}/{z}/{x}/{y}.png")
def serve_sentinel_tile(aoi: str, layer: str, z: int, x: int, y: int):
    if layer not in SENTINEL_LAYERS or not valid_xyz(z, x, y):
        raise HTTPException(404, "Invalid Sentinel tile")
    tiles, manifest = sentinel_manifest(aoi)
    tile = tiles / layer / str(z) / str(x) / f"{y}.png"
    entry = cached_sentinel_layer(manifest, layer)
    if entry is None or not tile.is_file():
        raise HTTPException(404, "Sentinel tile not cached")
    zoom = manifest["zoom"]
    failed = entry["tiles"].get("failed", [])
    # A failed restage can leave an older PNG at the same path.
    if not zoom["min"] <= z <= zoom["max"] or any(
        (failure["z"], failure["x"], failure["y"]) == (z, x, y) for failure in failed
    ):
        raise HTTPException(404, "Sentinel tile not cached")
    return FileResponse(tile, media_type="image/png")


@app.get("/api/pitch-facts")
def pitch_facts():
    """Measured pitch numbers, parsed from the merged reports with their sources."""
    try:
        return load_pitch_facts()
    except (OSError, ReportFactError) as error:
        raise HTTPException(500, f"Report facts unavailable: {error}") from error


BULLETIN_REPORT = Path(__file__).resolve().parent / "reports" / "bulletin_demo.md"
BULLETIN_SECTIONS = {
    "es": "## ES — Historia ciudadana",
    "en": "## EN — Decision-maker brief",
}


def parse_bulletin_report(text):
    """Split the merged live-run report into its ES/EN sections and serving metadata."""
    sections = {}
    for language, header in BULLETIN_SECTIONS.items():
        start = text.find(header)
        if start == -1:
            continue
        start += len(header)
        end = text.find("\n## ", start)
        sections[language] = text[start : end if end != -1 else len(text)].strip()
    model_line = next(
        (line.strip() for line in text.splitlines() if line.startswith("**Serving model:**")),
        None,
    )
    sections["serving_model"] = model_line
    return sections


@app.get("/api/bulletin")
def bulletin():
    """The bilingual bulletin from the recorded live graph run (reports/bulletin_demo.md)."""
    try:
        text = BULLETIN_REPORT.read_text(encoding="utf-8")
    except OSError as error:
        raise HTTPException(404, "Bulletin report unavailable") from error
    sections = parse_bulletin_report(text)
    if "es" not in sections or "en" not in sections:
        raise HTTPException(500, "Bulletin report malformed")
    return {
        "state": "cached",
        "badge": "SI-Assisted Analytics",
        "citizen_story_es": sections["es"],
        "decision_maker_brief_en": sections["en"],
        "serving_model": sections.get("serving_model"),
        "provenance": "reports/bulletin_demo.md (live LangGraph run, #162)",
    }


FLOOD_EVIDENCE = CACHE_ROOT / "mojana" / "flood_evidence.json"


def flood_series_entry():
    """Per-date measured water-pixel counts from the serialized flood evidence artifact."""
    try:
        artifact = json.loads(FLOOD_EVIDENCE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    dates = []
    for entry in artifact.get("dates", []):
        if not isinstance(entry, dict) or not isinstance(entry.get("date"), str):
            continue
        if not isinstance(entry.get("n_water"), int) or not isinstance(entry.get("n_valid"), int):
            continue
        if entry["n_valid"] <= 0:
            continue  # a date with no valid pixels carries no measured area
        dates.append(
            {
                "date": entry["date"],
                "n_water": entry["n_water"],
                "n_valid": entry["n_valid"],
                "granule_ids": entry.get("granule_ids", []),
            }
        )
    display = artifact.get("water_extent", {})
    return {
        "state": "live" if artifact.get("baseline", {}).get("accepted") else "gate result",
        "dates": dates,
        "display_date": display.get("reference_date"),
        "display_ha": display.get("value_ha"),
        "pixel_area_m2": display.get("pixel_area_m2"),
        "granule_ids": artifact.get("provenance", {}).get("granule_ids", []),
    }


@app.get("/api/flood-series")
def flood_series():
    """The measured La Mojana open-water series, per date, from the evidence artifact."""
    series = flood_series_entry()
    if series is None:
        raise HTTPException(404, "Flood evidence artifact unavailable")
    return series


@app.get("/api/flood-mask/{date}.png")
def flood_mask(date: str):
    """Render one date's measured water mask as an RGBA image overlay."""
    if not re.fullmatch(r"2026-\d{2}-\d{2}", date):
        raise HTTPException(404, "Invalid date")
    path = CACHE_ROOT / "mojana" / f"water_extent_{date}.tif"
    if not path.is_file():
        raise HTTPException(404, f"No water mask for {date}")
    with rasterio.open(path) as src:
        grid = src.read(1)
    water = grid == 1
    height, width = grid.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[water] = [53, 196, 181, 200]
    png = MemoryFile()
    with rasterio.open(
        png,
        "w",
        driver="PNG",
        width=width,
        height=height,
        count=4,
        dtype="uint8",
    ) as dst:
        dst.write(rgba.transpose(2, 0, 1))
    return Response(png.read(), media_type="image/png", headers={"Cache-Control": "no-cache"})


@app.get("/api/flood-mask")
def flood_mask_bounds(date: str = Query(...)):
    """Bounds and pixel posting for one date's mask, for the image overlay."""
    if not re.fullmatch(r"2026-\d{2}-\d{2}", date):
        raise HTTPException(404, "Invalid date")
    path = CACHE_ROOT / "mojana" / f"water_extent_{date}.tif"
    if not path.is_file():
        raise HTTPException(404, f"No water mask for {date}")
    with rasterio.open(path) as src:
        west, south, east, north = rasterio.warp.transform_bounds(
            src.crs, "EPSG:4326", *src.bounds, densify_pts=21
        )
    return {"date": date, "bounds": [west, south, east, north]}


LANDSLIDE_EVIDENCE = CACHE_ROOT / "aburra" / "landslide_evidence.json"


@app.get("/api/landslide-verdict")
def landslide_verdict():
    """The Aburrá calibrated verdict, from the serialized evidence artifact."""
    try:
        artifact = json.loads(LANDSLIDE_EVIDENCE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise HTTPException(404, "Landslide evidence artifact unavailable") from error
    verdict = artifact.get("noise_floor_verdict")
    if not isinstance(verdict, dict) or "outcome" not in verdict:
        raise HTTPException(500, "Landslide artifact malformed")
    provenance = artifact.get("provenance", {})
    return {
        "outcome": verdict.get("outcome"),
        "text": verdict.get("text"),
        "noise_floor_mm": verdict.get("noise_floor_mm"),
        "n_pairs": verdict.get("n_pairs"),
        "test": verdict.get("test"),
        "calibration": [
            {
                "stack": entry.get("stack"),
                "n_pairs": entry.get("n_pairs"),
                "eligible_pixels": entry.get("eligible_pixels"),
                "exceeds_null": entry.get("exceeds_null"),
            }
            for entry in verdict.get("calibration", [])
            if isinstance(entry, dict)
        ],
        "granule_ids": provenance.get("granule_ids", [])[:1] + ["…"],
        "command": provenance.get("command"),
    }


@app.get("/api/cache-bands/{aoi}")
def cache_bands(aoi: str):
    """Band states from the AOI manifest. Withheld co-event bands map to `not cached`."""
    if aoi not in SENTINEL_AOIS:
        raise HTTPException(404, "Unknown cache area")
    path = CACHE_ROOT / aoi / "manifest.json"
    if not path.is_file():
        return {"state": "not cached", "bands": {}}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise HTTPException(500, "Cache manifest unreadable") from error
    bands = {}
    for name, band in manifest.get("bands", {}).items():
        status = band.get("status")
        source = band.get("source_id")
        cached = status == "cached" and isinstance(source, str) and source not in {"", "missing"}
        bands[name] = {
            "state": "cached" if cached else "not cached",
            "status": status if status in {"cached", "missing", "withheld"} else "missing",
            "source_id": source if cached else None,
        }
    return {"state": "cached", "bands": bands}


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


def valid_xyz(z: int, x: int, y: int) -> bool:
    return 0 <= z <= 24 and 0 <= x < 2**z and 0 <= y < 2**z


@app.get("/api/local-tiles/aburra/{domain}/{z}/{x}/{y}.png")
@app.get("/api/local-tiles/{domain}/{z}/{x}/{y}.png")
def serve_local_zarr_tile(domain: str, z: int, x: int, y: int):
    if not valid_xyz(z, x, y):
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
