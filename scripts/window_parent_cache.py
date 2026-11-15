#!/usr/bin/env python3
"""Copy one parent AOI's cached LOS raster and Sentinel tiles onto a child bbox.

The child raster is a native-grid window: each parent pixel is copied, and no
new pixel is interpolated. Sentinel PNGs that intersect the child bbox are
copied byte for byte. The valley noise-floor test is not repeated.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import rasterio
import yaml
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "local_cache"
CHILDREN = {
    "la_picacha": {
        "parent": "aburra",
        "config_key": "6_la_picacha_landslide",
        "band": "los_disp_mm",
    }
}


def config_bbox(config_key: str) -> list[float]:
    """[W, S, E, N] from config/bailasar.yaml. The box is not hardcoded here."""
    document = yaml.safe_load((ROOT / "config" / "bailasar.yaml").read_text(encoding="utf-8"))
    box = document["aois"][config_key]
    if len(box) != 4 or not all(isinstance(value, int | float) for value in box):
        raise SystemExit(f"{config_key} bbox is not four numbers")
    return [float(value) for value in box]


def read_native_window(
    raster_file: Path, bbox: list[float]
) -> tuple[np.ndarray, rasterio.Affine, str]:
    """Return the parent cells whose native pixels meet ``bbox``. No resampling."""
    with rasterio.open(raster_file) as source:
        if source.crs is None:
            raise SystemExit(f"{raster_file} has no CRS")
        west, south, east, north = transform_bounds("EPSG:4326", source.crs, *bbox, densify_pts=21)
        window = from_bounds(west, south, east, north, transform=source.transform)
        window = window.round_offsets().round_lengths()
        if window.width < 1 or window.height < 1:
            raise SystemExit("bbox does not cover a parent pixel")
        clipped = Window(
            max(0, window.col_off),
            max(0, window.row_off),
            window.width,
            window.height,
        )
        band = source.read(1, window=clipped, masked=True)
        values = np.array(
            band.filled(np.nan) if np.ma.isMaskedArray(band) else band, dtype=np.float32
        )
        nodata = source.nodata
        if nodata is not None and np.isfinite(nodata):
            values = np.where(values == nodata, np.nan, values)
        return values, source.window_transform(clipped), source.crs.to_string()


def write_cog(dest: Path, values: np.ndarray, transform: rasterio.Affine, crs: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        dest,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        compress="deflate",
    ) as dataset:
        dataset.write(values, 1)


def _median(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    return float(np.median(finite))


def copy_intersecting_tiles(parent_tiles: Path, child_tiles: Path, bbox: list[float]) -> int:
    """Copy PNG bytes for tiles whose footprint meets the child bbox."""
    from scripts.prestage_tiles import bboxes_intersect, tile_lonlat_bounds

    written = 0
    if not parent_tiles.is_dir():
        return 0
    for source in parent_tiles.rglob("*.png"):
        parts = source.relative_to(parent_tiles).parts
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        z, x, y = int(parts[0]), int(parts[1]), int(source.stem)
        if not bboxes_intersect(tile_lonlat_bounds(z, x, y), bbox):
            continue
        dest = child_tiles / parts[0] / parts[1] / source.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        written += 1
    return written


def observed_fraction(tile_dir: Path, bbox: list[float]) -> dict[str, int] | None:
    """Pixel centers inside ``bbox`` at the finest staged zoom, and how many are observed."""
    from scripts.prestage_tiles import pixels_inside_frame, read_png_rgba

    pngs = [item for item in tile_dir.rglob("*.png") if item.parent.parent.name.isdigit()]
    if not pngs:
        return None
    finest = max(int(item.parent.parent.name) for item in pngs)
    inside_n = 0
    observed_n = 0
    for item in pngs:
        z = int(item.parent.parent.name)
        if z != finest:
            continue
        x, y = int(item.parent.name), int(item.stem)
        rgba = read_png_rgba(item)
        inside = pixels_inside_frame(z, x, y, bbox, rgba.shape[0])
        inside_n += int(inside.sum())
        observed_n += int((inside & (rgba[..., 3] > 0)).sum())
    if inside_n == 0:
        return None
    return {"zoom": finest, "inside": inside_n, "observed": observed_n}


def _layer_manifest(parent_layer: dict, written: int, coverage_pct: float | None) -> dict:
    layer = {
        "collection": parent_layer.get("collection"),
        "selection_rule": (
            "Byte copy of the parent AOI tiles whose Web Mercator footprint "
            "intersects the child bbox. Scene selection is the parent's."
        ),
        "status": "cached" if written else "missing",
        "scene_ids": list(parent_layer.get("scene_ids") or []),
        "date": parent_layer.get("date"),
        "spacecraft": parent_layer.get("spacecraft"),
        "relative_orbit": parent_layer.get("relative_orbit"),
        "platform": parent_layer.get("platform"),
        "coverage_pct": coverage_pct,
        "tiles": {"requested": written, "written": written, "failed": []},
        "parent_aoi": parent_layer.get("parent_aoi"),
    }
    return layer


def build_child(child: str) -> dict:
    spec = CHILDREN[child]
    parent = spec["parent"]
    bbox = config_bbox(spec["config_key"])
    band = spec["band"]
    parent_root = CACHE / parent
    parent_manifest = json.loads((parent_root / "manifest.json").read_text(encoding="utf-8"))
    parent_band = parent_manifest["bands"][band]
    source_id = parent_band["source_id"]
    granule = source_id.split(" (", 1)[0]
    parent_raster = parent_root / "cogs" / f"{parent}_{band}.tif"
    values, transform, crs = read_native_window(parent_raster, bbox)
    finite = int(np.isfinite(values).sum())
    total = int(values.size)
    with rasterio.open(parent_raster) as source:
        parent_values = source.read(1).astype(np.float32)
    child_root = CACHE / child
    raster_dest = child_root / "cogs" / f"{child}_{band}.tif"
    write_cog(raster_dest, values, transform, crs)

    parent_tiles = json.loads((parent_root / "tiles" / "manifest.json").read_text(encoding="utf-8"))
    copied = {}
    coverage = {}
    for layer, folder in (("optical_s2", "s2"), ("cband_s1", "s1")):
        written = copy_intersecting_tiles(
            parent_root / "tiles" / folder, child_root / "tiles" / folder, bbox
        )
        copied[folder] = written
        fraction = observed_fraction(child_root / "tiles" / folder, bbox)
        coverage[folder] = fraction
        pct = None
        if fraction is not None and fraction["inside"]:
            pct = round(100.0 * fraction["observed"] / fraction["inside"], 2)
        parent_entry = dict(parent_tiles["layers"][layer])
        parent_entry["parent_aoi"] = parent
        # filled below
        copied[layer] = _layer_manifest(parent_entry, written, pct)

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    tile_manifest = {
        "aoi": child,
        "parent_aoi": parent,
        "config_key": spec["config_key"],
        "bbox_wsen": bbox,
        "bbox_source": f"config/bailasar.yaml aois.{spec['config_key']}",
        "zoom": parent_tiles["zoom"],
        "tile_scheme": parent_tiles.get("tile_scheme"),
        "generated_utc": now,
        "generator": "scripts/window_parent_cache.py",
        "layers": {
            "optical_s2": copied["optical_s2"],
            "cband_s1": copied["cband_s1"],
        },
    }
    (child_root / "tiles").mkdir(parents=True, exist_ok=True)
    (child_root / "tiles" / "manifest.json").write_text(
        json.dumps(tile_manifest, indent=1) + "\n", encoding="utf-8"
    )

    window_median = _median(values)
    parent_median = _median(parent_values)
    text = (
        f"{finite} of {total} native-grid pixels inside the La Picacha bbox are finite "
        f"on the Aburrá LOS raster. Window median {window_median:.3f} mm; parent median "
        f"{parent_median:.3f} mm (measured). The valley noise-floor test was not repeated "
        "on this window."
    )
    evidence = {
        "schema": "landslide/1",
        "provenance": {
            "source": "cache",
            "granule_ids": [granule],
            "cache_build_time": now,
            "command": "uv run python scripts/window_parent_cache.py la_picacha",
            "parent_aoi": parent,
            "parent_raster": f"{parent}/cogs/{parent}_{band}.tif",
            "window_bbox": bbox,
            "stream": parent_band.get("stream") or "PR",
        },
        "uncalibrated": [
            "spatial window of the Aburrá LOS raster; the valley noise-floor test was not repeated"
        ],
        "noise_floor_verdict": {
            "outcome": "not_retested",
            "evidence_status": "window",
            "text": text,
            "test": "native-grid window of the parent LOS raster; not the sign-flip null",
            "units": "mm",
            "n_finite": finite,
            "n_window": total,
            "parent_n_pixels": int(parent_values.size),
            "window_median_mm": window_median,
            "parent_median_mm": parent_median,
        },
        "pairs": [],
    }
    (child_root / "landslide_evidence.json").write_text(
        json.dumps(evidence, indent=1) + "\n", encoding="utf-8"
    )
    manifest = {
        "aoi": child,
        "parent_aoi": parent,
        "bbox": bbox,
        "bands": {
            band: {
                "source_id": source_id,
                "status": "cached" if finite else "missing",
                "asset_type": parent_band.get("asset_type"),
                "stream": parent_band.get("stream"),
                "finite_pixel_count": finite,
                "finite_pixel_ratio": round(finite / total, 4) if total else 0.0,
                "parent_raster": f"{parent}/cogs/{parent}_{band}.tif",
            }
        },
    }
    (child_root / "manifest.json").write_text(
        json.dumps(manifest, indent=1) + "\n", encoding="utf-8"
    )
    summary = {
        "child": child,
        "parent": parent,
        "granule": granule,
        "n_finite": finite,
        "n_window": total,
        "window_median_mm": window_median,
        "parent_median_mm": parent_median,
        "tiles": {"s2": copied["s2"], "s1": copied["s1"]},
        "coverage": coverage,
        "command": evidence["provenance"]["command"],
    }
    (child_root / "window_summary.json").write_text(
        json.dumps(summary, indent=1) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if len(sys.argv) != 2 or sys.argv[1] not in CHILDREN:
        raise SystemExit(f"usage: window_parent_cache.py <{'|'.join(CHILDREN)}>")
    summary = build_child(sys.argv[1])
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
