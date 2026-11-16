"""Build a cloud-free Sentinel-2 context composite for each navigator frame.

The result is geographic context for the visor. It is not a measurement.
Clouds removed by Cloud Score+ stay missing (NaN, then alpha 0). They are
not filled with 0 and not borrowed from another frame.

Earth Engine is used here, at build time, through gee_math.ee_session.init_ee.
The running app only reads the COGs this script writes.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
import traceback
from pathlib import Path

import numpy as np
import rioxarray  # noqa: F401 - registers the raster accessor
import xarray as xr
from rasterio.transform import from_bounds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gee_math.ee_session import init_ee  # noqa: E402
from scripts.build_cache import (  # noqa: E402
    GEE_NODATA_SENTINEL,
    gee_nodata_to_nan,
    sample_grid_from_bbox,
    structured_band,
)
from scripts.context_basemap_tiles import (  # noqa: E402
    CONTEXT_DIR,
    frame_dimensions,
    pad_bbox,
    stretch_reflectance,
)
from src.bailasar.config import get_config  # noqa: E402

ENV_PATH = ROOT / ".env"


def load_env(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def probe_nicfi() -> dict:
    """Whether this Earth Engine identity can read Planet NICFI. Not exported."""
    import ee

    asset = "projects/planet-nicfi/assets/basemaps/americas"
    try:
        count = ee.ImageCollection(asset).size().getInfo()
    except Exception as exc:  # noqa: BLE001 - recorded as a class name, not hidden
        return {"asset": asset, "readable": False, "error_type": type(exc).__name__, "used": False}
    return {
        "asset": asset,
        "readable": True,
        "image_count": int(count),
        "used": False,
        "reason": "NICFI mosaics are not copied onto the public visor",
    }


def median_collection(spec: dict, bbox: list[float]):
    """Masked Sentinel-2 median. The mask is applied before the median."""
    import ee

    region = ee.Geometry.Rectangle([float(value) for value in bbox])
    qa_band = str(spec["cloud_score_band"])
    clear_min = float(spec["clear_min"])
    bands = [str(band) for band in spec["bands"]]
    scenes = (
        ee.ImageCollection(str(spec["asset"]))
        .filterBounds(region)
        .filterDate(str(spec["start"]), str(spec["end"]))
        .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", float(spec["cloudy_scene_max"])))
    )
    scores = ee.ImageCollection(str(spec["cloud_score_asset"]))
    linked = scenes.linkCollection(scores, [qa_band])

    def mask_clear(image):
        clear = image.select(qa_band).gte(clear_min)
        return image.updateMask(clear).select(bands)

    count = int(scenes.size().getInfo())
    return linked.map(mask_clear).median(), count


def fetch_stack(image, band_names: list[str], grid) -> np.ndarray:
    """One computePixels window. The sentinel becomes NaN. No unmask(0)."""
    import ee

    region = ee.Geometry.Rectangle(list(grid.clip_bbox))
    params = {
        "expression": image.clip(region).unmask(GEE_NODATA_SENTINEL),
        "fileFormat": "NPY",
        "grid": {
            "dimensions": {"width": grid.width, "height": grid.height},
            "affineTransform": {
                "scaleX": grid.scale_x,
                "shearX": 0,
                "translateX": grid.translate_x,
                "shearY": 0,
                "scaleY": grid.scale_y,
                "translateY": grid.translate_y,
            },
            "crsCode": grid.crs,
        },
    }
    raw = ee.data.computePixels(params)
    structured = np.load(io.BytesIO(raw))
    planes = [gee_nodata_to_nan(structured_band(structured, name)) for name in band_names]
    stack = np.stack(planes, axis=0).astype(np.float32, copy=False)
    expected = (len(band_names), grid.height, grid.width)
    if stack.shape != expected:
        raise ValueError(f"computePixels shape {stack.shape} != {expected}")
    return stack


def chunk_bounds(bbox: list[float], width: int, height: int, col: int, row: int, cw: int, ch: int):
    west, south, east, north = (float(value) for value in bbox)
    span_x = east - west
    span_y = north - south
    chunk_west = west + span_x * (col / width)
    chunk_east = west + span_x * ((col + cw) / width)
    chunk_north = north - span_y * (row / height)
    chunk_south = north - span_y * ((row + ch) / height)
    return [chunk_west, chunk_south, chunk_east, chunk_north]


def pull_frame(
    image, band_names: list[str], bbox: list[float], width: int, height: int, chunk: int, name: str
):
    canvas = np.full((len(band_names), height, width), np.nan, dtype=np.float32)
    failed = 0
    done = 0
    total = math.ceil(height / chunk) * math.ceil(width / chunk)
    row = 0
    while row < height:
        col = 0
        ch = min(chunk, height - row)
        while col < width:
            cw = min(chunk, width - col)
            grid = sample_grid_from_bbox(
                chunk_bounds(bbox, width, height, col, row, cw, ch), cw, ch
            )
            pulled = None
            error = "ok"
            for _attempt in range(2):
                try:
                    pulled = fetch_stack(image, band_names, grid)
                    error = "ok"
                    break
                except Exception as exc:  # noqa: BLE001 - one retry, then the window stays missing
                    error = type(exc).__name__
                    pulled = None
            done += 1
            if pulled is None:
                failed += 1
                print(f"CHUNK_FAIL {name} {done}/{total} {error}", flush=True)
            else:
                canvas[:, row : row + ch, col : col + cw] = pulled
                print(f"CHUNK {name} {done}", flush=True)
            col += chunk
        row += chunk
    return canvas, failed, total


def write_cog(rgba: np.ndarray, path: Path, bbox: list[float]) -> None:
    """4-band uint8 COG. Alpha 0 is unobserved. There is no reflectance nodata value."""
    _bands, height, width = rgba.shape
    path.parent.mkdir(parents=True, exist_ok=True)
    data = xr.DataArray(rgba, dims=("band", "y", "x"))
    data.rio.write_crs("EPSG:4326", inplace=True)
    data.rio.write_transform(
        from_bounds(bbox[0], bbox[1], bbox[2], bbox[3], width, height), inplace=True
    )
    data.rio.to_raster(
        path,
        driver="COG",
        compress="DEFLATE",
        overview_resampling="nearest",
    )


def load_manifest(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"frames": {}}
    if not isinstance(data, dict) or not isinstance(data.get("frames"), dict):
        return {"frames": {}}
    return data


def build(only: set[str] | None, rebuild: bool) -> int:
    load_env()
    project = init_ee(high_volume=True)
    spec = dict(get_config().ops("context_basemap"))
    frames = dict(spec["frames"])
    out_dir = ROOT / "local_cache" / CONTEXT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    manifest = load_manifest(manifest_path)
    manifest.update(
        {
            "role": "geographic_context_not_a_measurement",
            "built_with": "scripts/build_context_basemap.py",
            "gee_project_set": bool(project),
            "asset": spec["asset"],
            "cloud_score_asset": spec["cloud_score_asset"],
            "cloud_score_band": spec["cloud_score_band"],
            "clear_min": spec["clear_min"],
            "cloudy_scene_max": spec["cloudy_scene_max"],
            "start": spec["start"],
            "end": spec["end"],
            "bands": list(spec["bands"]),
            "reflectance_scale": spec["reflectance_scale"],
            "visual_max_dn": spec["visual_max_dn"],
            "stretch": "display clip only; unobserved pixels stay alpha 0",
            "pad_fraction": spec["pad_fraction"],
            "nicfi_probe": probe_nicfi(),
        }
    )
    print(f"NICFI readable={manifest['nicfi_probe'].get('readable')}", flush=True)
    band_names = [str(band) for band in spec["bands"]]
    chunk = int(spec["chunk"])
    max_pixels = int(spec["max_pixels"])
    visual_max = float(spec["visual_max_dn"])
    rebuilt_any = False

    for name, frame in frames.items():
        if only and name not in only:
            continue
        cog_name = f"{name}.tif"
        cog_path = out_dir / cog_name
        previous = manifest["frames"].get(name, {})
        if not rebuild and previous.get("status") == "cached" and cog_path.is_file():
            print(f"FRAME_SKIP {name}", flush=True)
            continue
        aoi_name = str(frame["aoi"])
        bbox = pad_bbox(list(get_config().aoi_bbox(aoi_name)), float(spec["pad_fraction"]))
        meters = float(frame["meters"])
        width, height = frame_dimensions(bbox, meters)
        pixels = width * height
        record = {
            "aoi": aoi_name,
            "bbox": bbox,
            "meters": meters,
            "width": width,
            "height": height,
            "pixel_count": pixels,
            "cog": cog_name,
            "cloudy_scene_max": spec["cloudy_scene_max"],
        }
        if pixels > max_pixels:
            record["status"] = "missing"
            record["reason"] = "frame exceeds context_basemap.max_pixels"
            manifest["frames"][name] = record
            print(f"FRAME_EMPTY {name} exceeds max_pixels {pixels}", flush=True)
            continue
        image, scene_count = median_collection(spec, bbox)
        record["scene_count"] = scene_count
        print(f"FRAME_START {name} {width}x{height} scenes={scene_count}", flush=True)
        if scene_count == 0:
            record["status"] = "missing"
            record["finite_pixel_count"] = 0
            record["reason"] = "no scene passed the cloudy-scene prefilter"
            manifest["frames"][name] = record
            print(f"FRAME_EMPTY {name} scenes=0", flush=True)
            continue
        stack, failed, total = pull_frame(image, band_names, bbox, width, height, chunk, name)
        valid = np.isfinite(stack).all(axis=0)
        finite = int(np.count_nonzero(valid))
        record["failed_chunks"] = failed
        record["chunk_count"] = total
        record["finite_pixel_count"] = finite
        record["finite_pixel_ratio"] = round(finite / pixels, 4) if pixels else 0.0
        if finite == 0:
            record["status"] = "missing"
            record["reason"] = "no finite reflectance after the clear-pixel mask"
            if cog_path.exists():
                cog_path.unlink()
            print(f"FRAME_EMPTY {name} finite=0 failed_chunks={failed}", flush=True)
        else:
            rgba = stretch_reflectance(stack, visual_max)
            write_cog(rgba, cog_path, bbox)
            record["status"] = "cached"
            rebuilt_any = True
            print(
                f"FRAME_DONE {name} finite={finite}/{pixels} failed_chunks={failed}",
                flush=True,
            )
        manifest["frames"][name] = record
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    if rebuilt_any:
        xyz = out_dir / "xyz"
        if xyz.exists():
            import shutil

            shutil.rmtree(xyz)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"DONE {manifest_path}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the visor context composite")
    parser.add_argument("--only", action="append", default=[], help="frame id, repeatable")
    parser.add_argument(
        "--rebuild", action="store_true", help="recompute frames that already exist"
    )
    args = parser.parse_args(argv)
    only = set(args.only) or None
    try:
        return build(only, args.rebuild)
    except Exception:
        traceback.print_exc()
        print("FAILED", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
