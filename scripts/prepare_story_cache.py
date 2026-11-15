"""Stage verified rasters for the local story map."""

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
import xarray as xr
from rasterio.features import bounds, shapes
from rasterio.io import MemoryFile
from rasterio.warp import transform_geom

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from video.report_facts import mojana_facts  # noqa: E402


def open_water_layer(cache_dir: Path, release_manifest: Path) -> dict | None:
    # The expected counts are parsed from reports/mojana.md, not copied by hand.
    evidence = mojana_facts()
    raster_path = cache_dir / "mojana" / f"water_extent_{evidence['date']}.tif"
    if not raster_path.is_file():
        return None
    release = json.loads(release_manifest.read_text(encoding="utf-8"))
    artifact = raster_path.relative_to(cache_dir).as_posix()
    digest = next((row["sha256"] for row in release["provenance"] if row["path"] == artifact), None)
    # Check the file against the verified release manifest before trusting its provenance.
    with raster_path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
            raise ValueError(f"{raster_path} does not match the approved cache release")
    with rasterio.open(raster_path) as raster:
        values = raster.read(1, masked=True)
        water = (values == 1).filled(False)
        if (
            int(water.sum()) != evidence["water_pixels"]["value"]
            or int(values.count()) != evidence["valid_pixels"]
        ):
            raise ValueError(f"{raster_path} does not match the measured report")
        features = [
            {
                "type": "Feature",
                "geometry": transform_geom(raster.crs, "EPSG:4326", geometry, precision=7),
                "properties": {},
            }
            for geometry, _ in shapes(water.astype("uint8"), mask=water, transform=raster.transform)
        ]

    coverage = [bounds(feature) for feature in features]
    return {
        "granule": evidence["granule"],
        "date": evidence["date"],
        "bounds": [
            min(box[0] for box in coverage),
            min(box[1] for box in coverage),
            max(box[2] for box in coverage),
            max(box[3] for box in coverage),
        ],
        "geojson": {"type": "FeatureCollection", "features": features},
    }


def pre_event_coherence(cache_dir: Path) -> dict | None:
    area = cache_dir / "eje_cafetero"
    manifest_path = area / "manifest.json"
    cube_path = area / "eje_cafetero_sar_cube.zarr"
    if not manifest_path.is_file() or not cube_path.is_dir():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    band = manifest["bands"].get("coherence_R", {})
    granule = band.get("source_id")
    if band.get("status") != "cached" or not granule or granule == "missing":
        return None
    # This chapter displays only pre-event coherence, regardless of release contents.
    with xr.open_zarr(cube_path) as cube:
        values = cube["coherence_R"].transpose("y", "x").values
    valid = np.isfinite(values)
    if not valid.any():
        return None
    gray = np.zeros(values.shape, dtype=np.uint8)
    gray[valid] = np.rint(np.clip(values[valid], 0, 1) * 255).astype(np.uint8)
    rgba = np.stack((gray, gray, gray, valid.astype(np.uint8) * 255))
    with MemoryFile() as image:
        height, width = values.shape
        with image.open(driver="PNG", width=width, height=height, count=4, dtype="uint8") as png:
            png.write(rgba)
        encoded = base64.b64encode(image.read()).decode("ascii")
    west, south, east, north = manifest["bbox"]
    return {
        "url": f"data:image/png;base64,{encoded}",
        "corners": [[west, north], [east, north], [east, south], [west, south]],
        "granule": granule,
        "dates": band.get("dates", []),
    }


def stage_story_cache(cache_dir: Path, release_manifest: Path) -> None:
    output = cache_dir / "story-results.json"
    results = json.loads(output.read_text(encoding="utf-8")) if output.is_file() else {}
    water = open_water_layer(cache_dir, release_manifest)
    flood = results.setdefault("flood", {})
    if water:
        flood["open_water"] = water
    else:
        flood.pop("open_water", None)
    coherence = pre_event_coherence(cache_dir)
    quake = results.setdefault("earthquake", {})
    if coherence:
        quake["pre_event_coherence"] = coherence
    else:
        quake.pop("pre_event_coherence", None)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(results, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=Path("local_cache"))
    parser.add_argument(
        "--release-manifest", type=Path, default=Path("dist/cache/cache_manifest.json")
    )
    args = parser.parse_args()
    stage_story_cache(args.cache_dir, args.release_manifest)
