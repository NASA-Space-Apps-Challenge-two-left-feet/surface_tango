"""Display tiles for the visor context composite.

The composite is geographic context. It is not a hazard measurement.
A masked or failed input stays alpha 0. Nothing here zero-fills a
reflectance value into an unobserved pixel.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject

from scripts.prestage_tiles import bboxes_intersect, tile_lonlat_bounds

CONTEXT_DIR = "context-basemap"
TILE_SIZE = 256


def stretch_reflectance(stack: np.ndarray, visual_max_dn: float) -> np.ndarray:
    """Map a (3, H, W) reflectance DN stack to (4, H, W) uint8.

    ``visual_max_dn`` is a display clip. It is not a physical threshold.
    A pixel with any non-finite band gets alpha 0. Its RGB bytes stay 0
    and are not a measured reflectance of zero.
    """
    if stack.ndim != 3 or stack.shape[0] != 3:
        raise ValueError("stack must be 3, height, width")
    scale = float(visual_max_dn)
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("visual_max_dn must be a positive finite number")
    height, width = stack.shape[1], stack.shape[2]
    rgba = np.zeros((4, height, width), dtype=np.uint8)
    valid = np.isfinite(stack).all(axis=0)
    if not np.any(valid):
        return rgba
    scaled = np.clip(np.asarray(stack[:, valid], dtype=np.float64) / scale, 0.0, 1.0)
    rgba[:3, valid] = np.rint(scaled * 255.0).astype(np.uint8)
    rgba[3, valid] = 255
    return rgba


def composite_layers(layers: list[np.ndarray]) -> np.ndarray:
    """Paint context layers from coarsest to finest.

    A later pixel replaces an earlier one only where its alpha is non-zero.
    A transparent pixel does not erase a coarser real observation, and it
    does not invent one.
    """
    if not layers:
        raise ValueError("composite_layers needs at least one layer")
    out = np.zeros_like(layers[0])
    for layer in layers:
        if layer.shape != out.shape or layer.shape[-1] != 4:
            raise ValueError("each layer must be height, width, 4")
        cover = layer[..., 3] > 0
        out[cover] = layer[cover]
    return out


def pad_bbox(bbox: list[float], fraction: float) -> list[float]:
    """Expand [W, S, E, N] by ``fraction`` of its own width and height."""
    west, south, east, north = (float(value) for value in bbox)
    pad = float(fraction)
    if not math.isfinite(pad) or pad < 0:
        raise ValueError("pad fraction must be finite and >= 0")
    dx = (east - west) * pad
    dy = (north - south) * pad
    padded = [
        max(-180.0, west - dx),
        max(-90.0, south - dy),
        min(180.0, east + dx),
        min(90.0, north + dy),
    ]
    if padded[0] >= padded[2] or padded[1] >= padded[3]:
        raise ValueError("padded frame is empty")
    return padded


def frame_dimensions(bbox: list[float], meters: float) -> tuple[int, int]:
    """Pixel size for a geographic frame. ``meters`` is the target posting."""
    west, south, east, north = (float(value) for value in bbox)
    posting = float(meters)
    if not math.isfinite(posting) or posting <= 0:
        raise ValueError("meters must be a positive finite number")
    mid_lat = (south + north) / 2.0
    meters_per_degree = 111_320.0
    meters_lon = meters_per_degree * math.cos(math.radians(mid_lat))
    width = max(1, int(round((east - west) * meters_lon / posting)))
    height = max(1, int(round((north - south) * meters_per_degree / posting)))
    return width, height


def _manifest_path(cache_root: Path) -> Path:
    return cache_root / CONTEXT_DIR / "manifest.json"


def load_context_frames(cache_root: Path) -> list[dict]:
    """Cached frames, coarse posting first. Missing files are skipped."""
    path = _manifest_path(cache_root)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    frames = manifest.get("frames")
    if not isinstance(frames, dict):
        return []
    loaded: list[dict] = []
    root = cache_root / CONTEXT_DIR
    for name, frame in frames.items():
        if not isinstance(frame, dict) or frame.get("status") != "cached":
            continue
        cog = frame.get("cog")
        bbox = frame.get("bbox")
        meters = frame.get("meters")
        if not isinstance(cog, str) or not isinstance(bbox, list) or len(bbox) != 4:
            continue
        try:
            posting = float(meters)
            bounds = [float(value) for value in bbox]
        except (TypeError, ValueError):
            continue
        raster = root / cog
        if not raster.is_file():
            continue
        loaded.append({"id": str(name), "path": raster, "bbox": bounds, "meters": posting})
    loaded.sort(key=lambda item: (-item["meters"], item["id"]))
    return loaded


def sample_rgba(path: Path, dst_transform, size: int, dst_crs: str = "EPSG:3857") -> np.ndarray:
    """Nearest-sample one context COG onto a destination grid.

    Pixels outside the file stay alpha 0. Nearest keeps a masked source
    pixel masked. It does not blend a clear neighbor into a cloudy one.
    """
    bands = np.zeros((4, size, size), dtype=np.uint8)
    with rasterio.open(path) as source:
        count = min(int(source.count), 4)
        for index in range(1, count + 1):
            reproject(
                source=rasterio.band(source, index),
                destination=bands[index - 1],
                src_transform=source.transform,
                src_crs=source.crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=Resampling.nearest,
            )
    return np.moveaxis(bands, 0, -1)


def mercator_tile_transform(z: int, x: int, y: int, size: int = TILE_SIZE):
    half_world = math.pi * 6_378_137.0
    span = 2.0 * half_world / 2**z
    left = -half_world + x * span
    top = half_world - y * span
    return from_bounds(left, top - span, left + span, top, size, size)


def render_context_tile(
    cache_root: Path, z: int, x: int, y: int, size: int = TILE_SIZE
) -> np.ndarray:
    """One XYZ tile. No cached frame returns a fully transparent image."""
    frames = load_context_frames(cache_root)
    empty = np.zeros((size, size, 4), dtype=np.uint8)
    if not frames:
        return empty
    tile_bounds = tile_lonlat_bounds(z, x, y)
    transform = mercator_tile_transform(z, x, y, size)
    layers = []
    for frame in frames:
        if not bboxes_intersect(tile_bounds, frame["bbox"]):
            continue
        layers.append(sample_rgba(frame["path"], transform, size))
    if not layers:
        return empty
    return composite_layers(layers)
