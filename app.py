# app.py
import asyncio
import json
import os
import re
import threading
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
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from rasterio.warp import reproject

from agents.state import MultiHazardGraphState
from gee_math.ee_session import init_ee
from mcp_servers.decision import DecisionConfigError, product_for_aoi, roster
from mcp_servers.flood_display import display_legend, paint_open_water
from scripts.prestage_tiles import (
    bboxes_intersect,
    layer_data_bbox,
    nodata_hatch_rgba,
    pixels_inside_frame,
    read_png_rgba,
    render_frame_tile,
    rgba_to_png,
    shared_frame,
    tile_lonlat_bounds,
)
from src.bailasar.config import get_config
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
NISAR_AOIS = {
    "mojana",
    "aburra",
    "eje_cafetero",
    "la_picacha",
    "choco_epicenter",
    "valle_del_cauca",
}


@app.get("/assets/{name}")
def frontend_asset(name: str):
    if name not in ASSET_PATHS:
        raise HTTPException(404, "Unknown frontend asset")
    asset = OFFLINE_ASSETS / ASSET_PATHS[name]
    if not asset.is_file():
        raise HTTPException(404, "Frontend asset not staged")
    media = "font/woff2" if name.endswith(".woff2") else None
    return FileResponse(asset, media_type=media)


SENTINEL_AOIS = {"aburra", "eje_cafetero", "mojana", "la_picacha"}
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


_FRAME_LOCK = threading.Lock()
_LAYER_BBOX_CACHE: dict[tuple[str, str], list | None] = {}
_CURTAIN_FRAME_CACHE: dict[str, list | None] = {}
NODATA_MARK = "no-data"


def _hazard_for_aoi(aoi_id: str) -> str | None:
    for item in AOI_REGISTRY:
        if item["id"] == aoi_id:
            return item["hazard"]
    return None


def sentinel_layer_bbox(aoi: str, layer: str) -> list | None:
    """Observed lon/lat bbox of one staged Sentinel layer. None when it has no pixels."""
    key = (aoi, layer)
    with _FRAME_LOCK:
        if key in _LAYER_BBOX_CACHE:
            return _LAYER_BBOX_CACHE[key]
    bbox = layer_data_bbox(CACHE_ROOT / aoi / "tiles" / layer)
    with _FRAME_LOCK:
        _LAYER_BBOX_CACHE[key] = bbox
    return bbox


def aoi_curtain_frame(aoi: str) -> list | None:
    """Shared curtain frame for one AOI, or None when it has no tile manifest.

    The frame is the intersection of the optical, C-band and NISAR footprints
    that actually contain observations. It is never the config AOI by itself.
    """
    with _FRAME_LOCK:
        if aoi in _CURTAIN_FRAME_CACHE:
            return _CURTAIN_FRAME_CACHE[aoi]
    manifest_path = CACHE_ROOT / aoi / "tiles" / "manifest.json"
    if not manifest_path.is_file():
        with _FRAME_LOCK:
            _CURTAIN_FRAME_CACHE[aoi] = None
        return None
    hazard = _hazard_for_aoi(aoi)
    nisar = aoi_coverage_footprint(aoi, hazard).get("footprint_bbox") if hazard else None
    frame = shared_frame(
        {
            "optical": sentinel_layer_bbox(aoi, "s2"),
            "cband": sentinel_layer_bbox(aoi, "s1"),
            "nisar": nisar,
        }
    )
    with _FRAME_LOCK:
        _CURTAIN_FRAME_CACHE[aoi] = frame
    return frame


def _png_response(rgba: np.ndarray) -> Response:
    return Response(
        rgba_to_png(rgba),
        media_type="image/png",
        headers={"X-Bailasar-Nodata": NODATA_MARK, "Cache-Control": "no-cache"},
    )


def _hatch_tile(z: int, x: int, y: int, frame: list) -> Response:
    """A labeled hatch for an XYZ tile, clipped to the shared frame."""
    size = 256
    rgba = nodata_hatch_rgba(size, size)
    inside = pixels_inside_frame(z, x, y, frame, size)
    rgba[~inside, 3] = 0
    return _png_response(rgba)


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


@app.get("/api/nodata-hatch.png")
def nodata_hatch_png():
    """Labeled hatch for a curtain panel that has no observation inside the frame."""
    return _png_response(nodata_hatch_rgba(256, 256))


@app.get("/api/sentinel-tiles/{aoi}")
def sentinel_tile_status(aoi: str):
    tiles, manifest = sentinel_manifest(aoi)
    frame = aoi_curtain_frame(aoi) if manifest else None
    panels = {"frame": frame, "nodata": NODATA_MARK if frame else None}
    for layer in SENTINEL_LAYERS:
        entry = cached_sentinel_layer(manifest, layer)
        if entry is None or not next((tiles / layer).glob("*/*/*.png"), None):
            panels[layer] = {"state": "not cached"}
            continue
        panel = {
            "state": "cached",
            "source": "cache",
            "scene_ids": entry["scene_ids"],
            "date": entry.get("date"),
            # Share of the config AOI the mosaic imaged. Not a claim that the
            # curtain frame covers that AOI.
            "coverage_pct": entry.get("coverage_pct"),
            "cache_built_at": manifest.get("generated_utc"),
            "tile_url": f"/api/sentinel-tiles/{aoi}/{layer}/{{z}}/{{x}}/{{y}}.png",
            "minzoom": manifest["zoom"]["min"],
            "maxzoom": manifest["zoom"]["max"],
        }
        if frame is not None:
            panel["bounds"] = frame
            panel["nodata"] = NODATA_MARK
        panels[layer] = panel
    return panels


@app.get("/api/sentinel-tiles/{aoi}/{layer}/{z}/{x}/{y}.png")
def serve_sentinel_tile(aoi: str, layer: str, z: int, x: int, y: int):
    if layer not in SENTINEL_LAYERS or not valid_xyz(z, x, y):
        raise HTTPException(404, "Invalid Sentinel tile")
    tiles, manifest = sentinel_manifest(aoi)
    tile = tiles / layer / str(z) / str(x) / f"{y}.png"
    entry = cached_sentinel_layer(manifest, layer)
    if entry is None:
        raise HTTPException(404, "Sentinel tile not cached")
    zoom = manifest["zoom"]
    failed = entry["tiles"].get("failed", [])
    stale = not zoom["min"] <= z <= zoom["max"] or any(
        (failure["z"], failure["x"], failure["y"]) == (z, x, y) for failure in failed
    )
    frame = aoi_curtain_frame(aoi)
    # A missing or stale file inside the frame is no observation, not a hole and not a 0.
    if stale or not tile.is_file():
        if frame is not None and bboxes_intersect(tile_lonlat_bounds(z, x, y), frame):
            return _hatch_tile(z, x, y, frame)
        raise HTTPException(404, "Sentinel tile not cached")
    if frame is None:
        return FileResponse(tile, media_type="image/png")
    rgba = read_png_rgba(tile)
    inside = pixels_inside_frame(z, x, y, frame, rgba.shape[0])
    return _png_response(render_frame_tile(rgba, inside))


@app.get("/api/pitch-facts")
def pitch_facts():
    """Measured pitch numbers, parsed from the merged reports with their sources."""
    try:
        return load_pitch_facts()
    except (OSError, ReportFactError) as error:
        raise HTTPException(500, f"Report facts unavailable: {error}") from error


# AOI registry for the mission-control navigator. Each entry carries its bbox
# [W,S,E,N] (EPSG:4326), hazard lane, a measured one-line fact and its source.
# State is computed from cache presence — AOIs without processed tiles report
# "not cached" (never faked), honoring the no-synthetic-data rule.
AOI_REGISTRY = [
    {
        "id": "mojana",
        "hazard": "flood",
        "label": "La Mojana / Caregato",
        "bbox": [-75.40, 7.90, -74.20, 9.20],
        "fact": "NISAR L-band open water; C-band misses a median 0.64 across 10 dates",
        "source": "reports/mojana_lvsc.md",
        "measured": True,
    },
    {
        "id": "aburra",
        "hazard": "landslide",
        "label": "Aburra Valley (overview)",
        "bbox": [-75.70, 6.12, -75.42, 6.45],
        "fact": "InSAR noise-floor null: no motion above 9.105 mm (17 pairs)",
        "source": "reports/aburra.md",
        "measured": True,
    },
    {
        "id": "la_picacha",
        "hazard": "landslide",
        "label": "La Picacha · Comuna 16 (Belen)",
        "bbox": [-75.6404, 6.2313, -75.6191, 6.2367],
        "fact": "Riesgo alto no mitigable (bbox measured, EPSG:3116)",
        "source": "Alcaldia de Medellin Res. 202350105375/2023",
        "measured": True,
    },
    {
        "id": "eje_cafetero",
        "hazard": "earthquake",
        "label": "Eje Cafetero (frozen scorecard)",
        "bbox": [-75.85, 4.40, -75.40, 5.15],
        "fact": "Coherence-loss damage proxy; scorecard uninformative (no verified labels)",
        "source": "reports/quake_dpm_interpretation.md",
        "measured": True,
    },
    {
        "id": "choco_epicenter",
        "hazard": "earthquake",
        "label": "Choco epicenter · San Jose del Palmar",
        "bbox": [-76.70, 4.40, -75.95, 5.25],
        "fact": "M7.4 epicenter, optical/C-band blind; NISAR covers it; damage proxy = measured null",
        "source": "reports/quake_epicenter_dpm.md",
        "measured": True,
    },
    {
        "id": "valle_del_cauca",
        "hazard": "earthquake",
        "label": "Valle del Cauca (west-Andes)",
        "bbox": [-77.10, 3.30, -75.95, 4.95],
        "fact": "Additional coverage; damage proxy null",
        "source": "reports/quake_epicenter_dpm.md",
        "measured": True,
    },
]


# The NISAR L-band band whose coverage defines each hazard's analysis footprint.
AOI_PRIMARY_BAND = {
    "flood": "gcov_hhhh_post",
    "landslide": "los_disp_mm",
    "earthquake": "coherence_R",
}
_AOI_FOOTPRINT_CACHE: dict[str, dict] = {}


def aoi_coverage_footprint(aoi_id: str, hazard: str) -> dict:
    """Measured NISAR coverage % of the AOI and the data-footprint bbox [W,S,E,N].

    coverage_pct comes from the band's finite_pixel_ratio in the manifest; the
    footprint is the lon/lat bounding box of the valid (finite) pixels, so the
    navigator frames the data — not an oversized empty AOI box. Returns {} when
    no cube is staged. Cached per AOI (one cube read)."""
    if aoi_id in _AOI_FOOTPRINT_CACHE:
        return _AOI_FOOTPRINT_CACHE[aoi_id]
    result: dict = {}
    manifest_path = CACHE_ROOT / aoi_id / "manifest.json"
    cube_glob = sorted((CACHE_ROOT / aoi_id).glob("*_sar_cube.zarr"))
    band = AOI_PRIMARY_BAND.get(hazard)
    if manifest_path.is_file() and cube_glob and band:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            ratio = manifest.get("bands", {}).get(band, {}).get("finite_pixel_ratio")
            if isinstance(ratio, (int, float)):
                result["coverage_pct"] = round(float(ratio) * 100, 1)
            with xr.open_zarr(cube_glob[0]) as cube:
                if band in cube and set(cube[band].dims) == {"x", "y"}:
                    arr = cube[band].transpose("y", "x")
                    finite = np.isfinite(arr.values)
                    if finite.any():
                        ys, xs = np.where(finite)
                        xcoord = cube["x"].values
                        ycoord = cube["y"].values
                        w, e = float(xcoord[xs.min()]), float(xcoord[xs.max()])
                        s, n = float(ycoord[ys.min()]), float(ycoord[ys.max()])
                        result["footprint_bbox"] = [min(w, e), min(s, n), max(w, e), max(s, n)]
        except Exception:
            result = {}
    if "footprint_bbox" not in result and band:
        cog = _single_cog(CACHE_ROOT / aoi_id / "cogs", band)
        if cog is not None:
            try:
                with rasterio.open(cog) as source:
                    grid = source.read(1, masked=True)
                    values = np.array(
                        grid.filled(np.nan) if np.ma.isMaskedArray(grid) else grid,
                        dtype=np.float32,
                    )
                    finite = np.isfinite(values)
                    if finite.any():
                        rows, cols = np.where(finite)
                        left, bottom, right, top = rasterio.windows.bounds(
                            rasterio.windows.Window(
                                int(cols.min()),
                                int(rows.min()),
                                int(cols.max() - cols.min() + 1),
                                int(rows.max() - rows.min() + 1),
                            ),
                            source.transform,
                        )
                        west, south, east, north = rasterio.warp.transform_bounds(
                            source.crs, "EPSG:4326", left, bottom, right, top, densify_pts=21
                        )
                        result["footprint_bbox"] = [west, south, east, north]
                        result["coverage_pct"] = round(
                            100.0 * float(finite.sum()) / float(values.size), 1
                        )
            except (OSError, rasterio.errors.RasterioError):
                pass
    _AOI_FOOTPRINT_CACHE[aoi_id] = result
    return result


def _single_cog(folder: Path, band: str) -> Path | None:
    """The one COG for ``band`` under an AOI. Two matches is not a guess."""
    if not folder.is_dir():
        return None
    matches = sorted(folder.glob(f"*_{band}.tif"))
    if len(matches) != 1:
        return None
    return matches[0]


@app.get("/api/aois")
def aois():
    """AOI navigator registry grouped by hazard. State is computed from cache
    presence; cached AOIs also report measured NISAR coverage % and the
    data-footprint bbox so the navigator frames the data, not an empty AOI box."""
    out: dict[str, list] = {"flood": [], "landslide": [], "earthquake": []}
    for item in AOI_REGISTRY:
        state = nisar_panel(item["id"]).get("state", "not cached")
        entry = {**item, "state": state}
        if state == "cached":
            entry.update(aoi_coverage_footprint(item["id"], item["hazard"]))
        out.setdefault(item["hazard"], []).append(entry)
    return out


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


@app.get("/api/decision")
def decision_board():
    """Evidence-state response postures for every configured AOI. No new numbers."""
    try:
        return roster(cache_root=CACHE_ROOT)
    except DecisionConfigError as exc:
        raise HTTPException(500, str(exc)) from exc


@app.get("/api/decision/{aoi}")
def decision_aoi(aoi: str):
    """One AOI's posture, copied from its own hazard envelopes."""
    try:
        product = product_for_aoi(aoi, cache_root=CACHE_ROOT)
    except DecisionConfigError as exc:
        raise HTTPException(500, str(exc)) from exc
    if product is None:
        raise HTTPException(404, "Unknown AOI")
    return product


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


def _water_mask_path(date: str) -> Path:
    if not re.fullmatch(r"2026-\d{2}-\d{2}", date):
        raise HTTPException(404, "Invalid date")
    path = CACHE_ROOT / "mojana" / f"water_extent_{date}.tif"
    if not path.is_file():
        raise HTTPException(404, f"No water mask for {date}")
    return path


def _hand_on_water_grid(water_src) -> np.ndarray | None:
    """Nearest-neighbor HAND on the water grid. Missing samples stay NaN.

    The cache stores HAND on its own geographic grid. This display warp does
    not fill gaps and does not treat height above drainage as water depth.
    """
    hand_path = CACHE_ROOT / "mojana" / "cogs" / "mojana_hand_m.tif"
    if not hand_path.is_file():
        return None
    dest = np.full((water_src.height, water_src.width), np.nan, dtype=np.float32)
    with rasterio.open(hand_path) as hand:
        source = hand.read(1).astype(np.float32, copy=False)
        nodata = hand.nodata
        if nodata is not None and np.isfinite(nodata):
            source = np.where(source == nodata, np.nan, source)
        reproject(
            source,
            dest,
            src_transform=hand.transform,
            src_crs=hand.crs,
            src_nodata=np.nan,
            dst_transform=water_src.transform,
            dst_crs=water_src.crs,
            dst_nodata=np.nan,
            resampling=Resampling.nearest,
        )
    return dest


def _flood_legend() -> dict:
    hand_path = CACHE_ROOT / "mojana" / "cogs" / "mojana_hand_m.tif"
    return display_legend(
        hand_cached=hand_path.is_file(),
        hand_max_m=get_config().prereg("flood.hand_max_m"),
    )


@app.get("/api/flood-mask/{date}.png")
def flood_mask(date: str):
    """Render one date's measured water mask as a translucent blue overlay.

    The edge is the mask. Interior color is MERIT HAND on wet pixels, not a
    surveyed inundation depth. Every mask value of 1 stays visible.
    """
    path = _water_mask_path(date)
    with rasterio.open(path) as src:
        grid = src.read(1)
        hand = _hand_on_water_grid(src)
        height, width = src.height, src.width
    rgba = paint_open_water(grid == 1, hand, get_config().prereg("flood.hand_max_m"))
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
    """Bounds and the legend for one date's mask. The legend text is copied as-is."""
    path = _water_mask_path(date)
    with rasterio.open(path) as src:
        west, south, east, north = rasterio.warp.transform_bounds(
            src.crs, "EPSG:4326", *src.bounds, densify_pts=21
        )
    return {"date": date, "bounds": [west, south, east, north], "legend": _flood_legend()}


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


@dataclass(frozen=True)
class NisarPanel:
    """One AOI-owned L-band display product and its serialized evidence."""

    aoi: str
    label: str
    raster: Path
    style: str
    bounds: list[float]
    granule_ids: list[str]
    evidence_artifacts: list[str]
    detail: str
    tracks: list[int] | None = None


def _load_cached_evidence(path: Path, schema: str) -> dict | None:
    """Return a well-formed, cache-local evidence artifact, never a fallback."""
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(artifact, dict) or artifact.get("schema") != schema:
        return None
    provenance = artifact.get("provenance")
    if not isinstance(provenance, dict):
        return None
    granules = provenance.get("granule_ids")
    if not isinstance(granules, list) or not all(
        isinstance(item, str) and item for item in granules
    ):
        return None
    return artifact


def _cached_band(manifest: dict, name: str) -> str | None:
    band = manifest.get("bands", {}).get(name)
    if not isinstance(band, dict) or band.get("status") != "cached":
        return None
    source = band.get("source_id")
    if not isinstance(source, str) or not source.strip() or source == "missing":
        return None
    return source.strip()


def _granule_id(source: str) -> str:
    """Drop a human provenance qualifier while retaining the immutable granule ID."""
    return source.split(" (", 1)[0]


def _panel_bounds(path: Path) -> list[float] | None:
    try:
        with rasterio.open(path) as source:
            west, south, east, north = rasterio.warp.transform_bounds(
                source.crs, "EPSG:4326", *source.bounds, densify_pts=21
            )
    except rasterio.errors.RasterioError:
        return None
    values = [west, south, east, north]
    if not all(np.isfinite(values)) or west >= east or south >= north:
        return None
    return values


def _artifact_name(path: Path) -> str:
    """A stable cache-relative name for display provenance, never a host path."""
    return str(path.relative_to(CACHE_ROOT))


def find_nisar_panel(aoi: str) -> NisarPanel | None:
    """Find only the analysis product owned by *aoi*.

    This deliberately does not look in any other AOI directory: lack of a local
    product is a ``not cached`` panel state rather than a visual substitute.
    """
    if aoi not in NISAR_AOIS:
        return None
    root = CACHE_ROOT / aoi
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if manifest.get("aoi") != aoi:
        return None

    if aoi == "mojana":
        evidence_path = root / "flood_evidence.json"
        evidence = _load_cached_evidence(evidence_path, "flood/1")
        water = evidence.get("water_extent") if evidence else None
        if not isinstance(water, dict):
            return None
        date = water.get("reference_date")
        granules = water.get("source_ids")
        raster = root / f"water_extent_{date}.tif"
        if (
            not isinstance(date, str)
            or not isinstance(granules, list)
            or not all(isinstance(item, str) and item for item in granules)
            or not raster.is_file()
        ):
            return None
        bounds = _panel_bounds(raster)
        if bounds is None:
            return None
        return NisarPanel(
            aoi=aoi,
            label="GCOV open water",
            raster=raster,
            style="water",
            bounds=bounds,
            granule_ids=granules,
            evidence_artifacts=[_artifact_name(evidence_path), _artifact_name(raster)],
            detail=f"GCOV open-water mask · {date}",
        )

    if aoi == "aburra":
        evidence_path = root / "landslide_evidence.json"
        evidence = _load_cached_evidence(evidence_path, "landslide/1")
        source = _cached_band(manifest, LANDSLIDE_BAND)
        raster = root / "cogs" / "aburra_los_disp_mm.tif"
        granules = evidence.get("provenance", {}).get("granule_ids", []) if evidence else []
        granule = _granule_id(source) if source else None
        if granule is None or granule not in granules or not raster.is_file():
            return None
        bounds = _panel_bounds(raster)
        if bounds is None:
            return None
        return NisarPanel(
            aoi=aoi,
            label="GUNW landslide kinematics",
            raster=raster,
            style="los",
            bounds=bounds,
            granule_ids=[granule],
            evidence_artifacts=[_artifact_name(evidence_path), _artifact_name(raster)],
            detail="GUNW LOS kinematics · ionosphere screen applied",
        )

    if aoi == "eje_cafetero":
        evidence_paths = [
            root / "quake_evidence_track11.json",
            root / "quake_evidence_track47.json",
        ]
        evidence = [_load_cached_evidence(path, "quake/1") for path in evidence_paths]
        source = _cached_band(manifest, "coherence_coseismic")
        raster = root / "cogs" / "eje_cafetero_coherence_coseismic.tif"
        if source is None or not raster.is_file() or any(item is None for item in evidence):
            return None
        track11 = evidence[0]
        coevent = track11.get("pairs", {}).get("C", {})
        if coevent.get("granule_id") != source:
            return None
        # Track 47 has an evidence window but no display raster. It remains an
        # explicit artifact in provenance; do not render track 11 in its place.
        granules = [source]
        bounds = _panel_bounds(raster)
        if bounds is None:
            return None
        return NisarPanel(
            aoi=aoi,
            label="GUNW DPM window",
            raster=raster,
            style="coherence",
            bounds=bounds,
            granule_ids=granules,
            evidence_artifacts=[_artifact_name(path) for path in evidence_paths]
            + [_artifact_name(raster)],
            detail="Co-event GUNW coherence · DPM windows tracks 11 and 47",
            tracks=[11, 47],
        )

    if aoi == "la_picacha":
        evidence_path = root / "landslide_evidence.json"
        evidence = _load_cached_evidence(evidence_path, "landslide/1")
        source = _cached_band(manifest, LANDSLIDE_BAND)
        raster = root / "cogs" / "la_picacha_los_disp_mm.tif"
        granules = evidence.get("provenance", {}).get("granule_ids", []) if evidence else []
        granule = _granule_id(source) if source else None
        verdict = evidence.get("noise_floor_verdict") if evidence else None
        if (
            granule is None
            or granule not in granules
            or not raster.is_file()
            or not isinstance(verdict, dict)
            or verdict.get("outcome") != "not_retested"
        ):
            return None
        bounds = _panel_bounds(raster)
        if bounds is None:
            return None
        return NisarPanel(
            aoi=aoi,
            label="GUNW LOS window",
            raster=raster,
            style="los",
            bounds=bounds,
            granule_ids=[granule],
            evidence_artifacts=[_artifact_name(evidence_path), _artifact_name(raster)],
            detail=(
                "Native-grid window of the Aburrá LOS raster. "
                "The valley noise-floor test was not repeated."
            ),
        )

    return None


def nisar_panel(aoi: str) -> dict:
    """Serialize one local L-band panel or its intentional ``not cached`` state."""
    if aoi not in NISAR_AOIS:
        raise HTTPException(404, "Unknown NISAR analysis area")
    panel = find_nisar_panel(aoi)
    if panel is None:
        return {"state": "not cached", "aoi": aoi}
    frame = aoi_curtain_frame(aoi)
    return {
        "state": "cached",
        "source": "cache",
        "aoi": panel.aoi,
        "label": panel.label,
        "detail": panel.detail,
        "granule_ids": panel.granule_ids,
        "evidence_artifacts": panel.evidence_artifacts,
        "tracks": panel.tracks,
        "bounds": frame or panel.bounds,
        "nodata": NODATA_MARK if frame else None,
        "tile_url": f"/api/nisar-panel/{aoi}/{{z}}/{{x}}/{{y}}.png",
    }


@app.get("/api/nisar-panel/{aoi}")
def nisar_panel_status(aoi: str):
    """Cached L-band primary product and provenance for the selected AOI."""
    return nisar_panel(aoi)


def _panel_rgba(style: str, values: np.ndarray) -> np.ndarray:
    """Color cached data while leaving unavailable pixels transparent."""
    rgba = np.zeros((4, *values.shape), dtype=np.uint8)
    valid = np.isfinite(values)
    if style == "water":
        water = valid & (values == 1)
        rgba[:, water] = np.array([53, 196, 181, 200], dtype=np.uint8)[:, None]
        return rgba
    if not valid.any():
        return rgba
    signal = values[valid]
    if style == "los":
        scale = float(np.percentile(np.abs(signal), 95)) or 1.0
        norm = np.clip(signal / (2 * scale) + 0.5, 0.0, 1.0)
        red, green, blue = _los_diverging_rgb(norm)
    else:  # coherence is an observed 0..1 ratio, never an imputed value.
        norm = np.clip(signal, 0.0, 1.0)
        red = (35 + norm * 220).astype(np.uint8)
        green = (30 + norm * 185).astype(np.uint8)
        blue = (75 + norm * 145).astype(np.uint8)
    rgba[0, valid] = red
    rgba[1, valid] = green
    rgba[2, valid] = blue
    rgba[3, valid] = 255
    return rgba


@app.get("/api/nisar-panel/{aoi}/{z}/{x}/{y}.png")
def serve_nisar_panel_tile(aoi: str, z: int, x: int, y: int):
    """Render only the selected AOI's cached L-band raster as an XYZ PNG."""
    if not valid_xyz(z, x, y):
        raise HTTPException(404, "Invalid XYZ tile")
    panel = find_nisar_panel(aoi)
    if panel is None:
        raise HTTPException(404, "NISAR analysis product not cached")
    half_world = np.pi * 6378137
    span = 2 * half_world / 2**z
    left, top = -half_world + x * span, half_world - y * span
    transform = from_bounds(left, top - span, left + span, top, 256, 256)
    try:
        with rasterio.open(panel.raster) as source:
            source_values = source.read(1, masked=True).astype(np.float32).filled(np.nan)
            values = np.full((256, 256), np.nan, dtype=np.float32)
            reproject(
                source_values,
                values,
                src_transform=source.transform,
                src_crs=source.crs,
                src_nodata=np.nan,
                dst_transform=transform,
                dst_crs="EPSG:3857",
                dst_nodata=np.nan,
                resampling=Resampling.nearest,
            )
    except rasterio.errors.RasterioError as error:
        raise HTTPException(500, "Cached NISAR raster unreadable") from error
    # Bands-first color, then height-width-channel. Finite dry pixels stay
    # transparent. Only unobserved pixels inside the shared frame are hatched.
    rgba = np.moveaxis(_panel_rgba(panel.style, values), 0, -1)
    frame = aoi_curtain_frame(aoi)
    if frame is not None:
        missing = ~np.isfinite(values)
        inside = pixels_inside_frame(z, x, y, frame, rgba.shape[0]) & missing
        rgba = render_frame_tile(rgba, inside)
    return _png_response(rgba)


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
    payload = {
        "state": "cached",
        "source": "cache",
        "granule_ids": [cache.granule_id],
        "cache_built_at": cache.built_at,
        "tile_url": f"/api/local-tiles/{domain}/{{z}}/{{x}}/{{y}}.png",
    }
    frame = aoi_curtain_frame("aburra")
    if frame is not None:
        payload["bounds"] = frame
        payload["nodata"] = NODATA_MARK
    return payload


def valid_xyz(z: int, x: int, y: int) -> bool:
    return 0 <= z <= 24 and 0 <= x < 2**z and 0 <= y < 2**z


# ColorBrewer RdBu diverging stops (blue → white → red) for the InSAR LOS tile.
_LOS_STOPS = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
_LOS_R = np.array([33, 103, 247, 239, 178])
_LOS_G = np.array([102, 169, 247, 138, 24])
_LOS_B = np.array([172, 207, 247, 98, 43])


def _los_diverging_rgb(norm: np.ndarray):
    """Map a 0..1 array (0.5 = zero displacement) to an RdBu diverging RGB triple."""
    r = np.interp(norm, _LOS_STOPS, _LOS_R).astype(np.uint8)
    g = np.interp(norm, _LOS_STOPS, _LOS_G).astype(np.uint8)
    b = np.interp(norm, _LOS_STOPS, _LOS_B).astype(np.uint8)
    return r, g, b


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

    # Scientific diverging colormap for LOS displacement (ColorBrewer RdBu):
    # blue = motion away / subsidence, white = no motion, red = motion toward /
    # uplift — the standard InSAR convention. Symmetric about zero on a robust
    # 95th-percentile scale. A measured 0 stays white. Missing pixels inside
    # the shared frame become the no-data hatch. Display only.
    rgba = np.zeros((size, size, 4), dtype=np.uint8)
    valid = np.isfinite(values)
    signal = values[valid]
    if signal.size:
        scale = float(np.percentile(np.abs(signal), 95)) or 1.0
        norm = np.clip(signal / (2 * scale) + 0.5, 0.0, 1.0)  # 0..1, 0.5 = zero
        r, g, b = _los_diverging_rgb(norm)
        rgba[valid, 0] = r
        rgba[valid, 1] = g
        rgba[valid, 2] = b
        rgba[valid, 3] = 255
    frame = aoi_curtain_frame("aburra")
    if frame is not None:
        inside = pixels_inside_frame(z, x, y, frame, size)
        rgba = render_frame_tile(rgba, inside)
    return _png_response(rgba)


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


@app.get("/cube", include_in_schema=False)
def cube_explorer():
    return FileResponse(Path(__file__).resolve().parent / "static/cube.html")


@app.get("/api/cube", tags=["Regional cubes"])
def cube_catalog():
    """Discover AOI-owned cubes. Each region has its own availability state."""
    return {
        "schema": "regional-cube/1",
        "regions": [cube_region(entry["id"]) for entry in AOI_REGISTRY],
    }


@app.get("/api/cube/{aoi}", tags=["Regional cubes"])
def cube_region(aoi: str):
    """Return a region catalog and same-origin URLs for its observations."""
    entry = next((entry for entry in AOI_REGISTRY if entry["id"] == aoi), None)
    if entry is None:
        raise HTTPException(404, "Unknown region")
    path = CACHE_ROOT / "regional-cubes" / f"{aoi}.zarr" / "catalog.json"
    catalog = {"state": "not cached", "layers": []}
    if path.is_file():
        try:
            catalog = json.loads(path.read_text())
            if not isinstance(catalog, dict) or catalog.get("aoi") != aoi:
                raise ValueError("Region mismatch")
            if not isinstance(catalog.get("layers"), list):
                raise ValueError("Missing layers")
            for layer in catalog["layers"]:
                name = layer["id"]
                if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
                    raise ValueError("Invalid layer identifier")
                layer["display"] = cube_display(layer)
                layer["links"] = {
                    "preview": f"/api/cube/{aoi}/{name}/preview.png",
                    "sample": f"/api/cube/{aoi}/{name}/sample",
                }
            catalog["state"] = "cached" if catalog["layers"] else "not cached"
        except (OSError, ValueError, KeyError, TypeError):
            catalog = {"state": "error", "layers": [], "reason": "Regional cube catalog unreadable"}
    return {
        **catalog,
        "aoi": aoi,
        "label": entry["label"],
        "bounds": entry["bbox"],
        "links": {
            "catalog": f"/api/cube/{aoi}",
            "explorer": f"/cube?aoi={aoi}",
            "context": f"/api/sentinel-tiles/{aoi}",
        },
    }


def cube_layer(aoi: str, layer: str):
    catalog = cube_region(aoi)
    store = CACHE_ROOT / "regional-cubes" / f"{aoi}.zarr"
    if catalog["state"] == "error":
        raise HTTPException(503, catalog["reason"])
    if catalog["state"] != "cached":
        raise HTTPException(404, "Regional cube not cached")
    metadata = next((item for item in catalog["layers"] if item["id"] == layer), None)
    if metadata is None:
        raise HTTPException(404, "Layer not cached")
    return store, metadata


def cube_display(metadata):
    name = metadata["id"]
    low, high = metadata["minimum"], metadata["maximum"]
    colors = ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"]
    category, units = "Radar", "source units"
    if name.startswith("water_extent"):
        category, units, low, high = "Open water", "class", 0, 1
        colors = ["#424242", "#46c7e8"]
    elif name.startswith("change_class"):
        category, units, low, high = "Change classes", "class", 0, 2
        colors = ["#424242", "#46c7e8", "#e8b34c"]
    elif "los_disp" in name:
        units = "mm"
        high = max(abs(low), abs(high))
        low = -high
        colors = ["#2166ac", "#67a9cf", "#f7f7f7", "#ef8a62", "#b2182b"]
    elif "coherence" in name:
        units, low, high = "ratio", 0, 1
    elif name in {"slope_deg", "hand_m", "agb_mgha"}:
        category = "Terrain & context"
        units = {"slope_deg": "degrees", "hand_m": "m", "agb_mgha": "Mg/ha"}[name]
    return {
        "category": category,
        "units": units,
        "minimum": low,
        "maximum": high,
        "colors": colors,
        "categorical": category in {"Open water", "Change classes"},
        "label": name.replace("_", " "),
        "provisional": "_PR_" in json.dumps(metadata.get("provenance", {})),
    }


def cube_colors(values, metadata):
    display = cube_display(metadata)
    valid = np.isfinite(values)
    rgba = np.zeros((4, *values.shape), dtype=np.uint8)
    palette = np.array(
        [[int(color[i : i + 2], 16) for i in (1, 3, 5)] for color in display["colors"]]
    )
    low, high = display["minimum"], display["maximum"]
    norm = np.clip((values[valid] - low) / (high - low or 1), 0, 1)
    for channel in range(3):
        if display["categorical"]:
            rgba[channel, valid] = palette[np.rint(norm * (len(palette) - 1)).astype(int), channel]
        else:
            rgba[channel, valid] = np.interp(
                norm, np.linspace(0, 1, len(palette)), palette[:, channel]
            ).astype("uint8")
    rgba[3, valid] = 255
    return rgba


@app.get("/api/cube/{aoi}/{layer}/sample", tags=["Regional cubes"])
def cube_sample(
    aoi: str,
    layer: str,
    lon: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-85, le=85),
):
    store, metadata = cube_layer(aoi, layer)
    x, y = rasterio.warp.transform("EPSG:4326", metadata["crs"], [lon], [lat])
    with xr.open_zarr(store, group=layer, consolidated=False, chunks=None) as ds:
        xs, ys = ds.x.values, ds.y.values
        dx, dy = abs(xs[1] - xs[0]) / 2, abs(ys[1] - ys[0]) / 2
        if not (xs.min() - dx <= x[0] <= xs.max() + dx and ys.min() - dy <= y[0] <= ys.max() + dy):
            return {
                "state": "cached",
                "availability": "no data",
                "value": None,
                "units": cube_display(metadata)["units"],
                "provenance": metadata["provenance"],
                "reason": "Outside the native grid",
            }
        value = float(
            ds.value.isel(x=int(np.argmin(abs(xs - x[0]))), y=int(np.argmin(abs(ys - y[0])))).values
        )
    return {
        "state": "cached",
        "availability": "observed" if np.isfinite(value) else "no data",
        "value": value if np.isfinite(value) else None,
        "units": cube_display(metadata)["units"],
        "measurement": "measured",
        "method": "nearest native pixel",
        "provenance": metadata["provenance"],
    }


@app.get(
    "/api/cube/{aoi}/{layer}/preview.png",
    tags=["Regional cubes"],
    response_class=Response,
    responses={
        200: {"content": {"image/png": {}}, "description": "Projected scientific display image"}
    },
)
def cube_preview(aoi: str, layer: str):
    store, metadata = cube_layer(aoi, layer)
    with xr.open_zarr(store, group=layer, consolidated=False, chunks=None) as dataset:
        data = dataset.value
        step = max(1, int(np.ceil(max(data.shape) / 768)))
        sampled = data.isel(y=slice(None, None, step), x=slice(None, None, step))
        source = sampled.values.astype("float32")
        # Coordinates describe original pixel centers; stride changes spacing,
        # not the center of the first sampled pixel.
        xs, ys = dataset.x.values, dataset.y.values
        dx, dy = (xs[1] - xs[0]) * step, (ys[1] - ys[0]) * step
        transform = rasterio.Affine(dx, 0, xs[0] - dx / 2, 0, dy, ys[0] - dy / 2)
        bounds = metadata["bounds"]
        mercator = rasterio.warp.transform_bounds("EPSG:4326", "EPSG:3857", *bounds)
        width = 768
        height = max(
            1, min(1536, round(width * (mercator[3] - mercator[1]) / (mercator[2] - mercator[0])))
        )
        values = np.full((height, width), np.nan, dtype="float32")
        reproject(
            source,
            values,
            src_transform=transform,
            src_crs=metadata["crs"],
            src_nodata=np.nan,
            dst_transform=from_bounds(*mercator, width, height),
            dst_crs="EPSG:3857",
            dst_nodata=np.nan,
            resampling=Resampling.nearest,
        )
    rgba = cube_colors(values, metadata)
    with MemoryFile() as png:
        with png.open(
            driver="PNG", width=values.shape[1], height=values.shape[0], count=4, dtype="uint8"
        ) as image:
            image.write(rgba)
        return Response(png.read(), media_type="image/png")


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def serve_ui():
    return FileResponse("static/index.html")
