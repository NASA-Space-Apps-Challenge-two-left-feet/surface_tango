"""Package extracted regional rasters into a separate, native-grid Zarr v3 store.

Run: uv run python scripts/build_regional_cube.py --aoi mojana
No network requests, resampling, overwrite, or modification of science caches.
"""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import rasterio
import xarray as xr
import yaml
import zarr
from rasterio.warp import transform_bounds

ROOT = Path(__file__).resolve().parents[1]


def regions():
    config = yaml.safe_load((ROOT / "config/bailasar.yaml").read_text())
    return {key.split("_", 1)[1]: bbox for key, bbox in config["aois"].items()}


def build(cache: Path, aoi: str) -> dict:
    # Names come from existing manifests; detailed AOIs without a manifest remain missing.
    source = cache / aoi
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    rasters = sorted(source.glob("*.tif")) + sorted((source / "cogs").glob("*.tif"))
    target = cache / "regional-cubes" / f"{aoi}.zarr"
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite {target}")
    if not rasters:
        return {"aoi": aoi, "state": "not cached"}
    target.parent.mkdir(parents=True, exist_ok=True)
    group = zarr.open_group(target, mode="w", zarr_format=3)
    layers = []
    for raster in rasters:
        name = raster.stem.removeprefix(f"{aoi}_")
        band = manifest.get("bands", {}).get(name, {})
        # A present file can contain only nodata. Manifest missing/withheld wins.
        if band and band.get("status") != "cached":
            continue
        with rasterio.open(raster) as src:
            if src.crs is None or src.transform.b or src.transform.d:
                raise ValueError(f"Unsupported or missing spatial grid: {raster.name}")
            data = src.read(1, masked=True).astype("float32").filled(np.nan)
            finite = int(np.isfinite(data).sum())
            if not finite:
                continue
            transform = src.transform
            x = transform.c + (np.arange(src.width) + 0.5) * transform.a
            y = transform.f + (np.arange(src.height) + 0.5) * transform.e
            bounds = list(transform_bounds(src.crs, "EPSG:4326", *src.bounds))
            provenance = {"source_id": band.get("source_id"), "dates": band.get("dates")}
            evidence_file = source / "flood_evidence.json"
            if name.startswith(("water_extent_", "change_class_")) and evidence_file.is_file():
                evidence = json.loads(evidence_file.read_text())
                date = name[-10:]
                entry = next((d for d in evidence.get("dates", []) if d["date"] == date), {})
                provenance = {"source_ids": entry.get("granule_ids", []), "date": date}
            metadata = {
                "id": name,
                "source_file": str(raster.relative_to(cache)),
                "crs": src.crs.to_string(),
                "bounds": bounds,
                "shape": list(data.shape),
                "finite_pixels": finite,
                "total_pixels": int(data.size),
                "provenance": provenance,
                "minimum": float(np.nanmin(data)),
                "maximum": float(np.nanmax(data)),
                "measurement": "measured",
                "command": f"uv run python scripts/build_regional_cube.py --aoi {aoi}",
            }
            dataset = xr.Dataset(
                {"value": (("y", "x"), data)}, coords={"x": x, "y": y}, attrs=metadata
            )
            dataset.to_zarr(
                target,
                group=name,
                mode="a",
                consolidated=False,
                encoding={"value": {"chunks": (256, 256)}},
            )
            layers.append(metadata)
    catalog = {
        "aoi": aoi,
        "state": "cached" if layers else "not cached",
        "format": "Zarr v3",
        "grid_policy": "native grids; no resampling",
        "built_at": datetime.now(UTC).isoformat(),
        "layers": layers,
        "related_artifacts": [str(p.relative_to(cache)) for p in sorted(source.glob("*.json"))]
        + [str(p.relative_to(cache)) for p in sorted(source.glob("*.parquet"))],
    }
    group.attrs.update(catalog)
    (target / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n")
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", required=True)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(os.environ.get("BAILASAR_CACHE_DIR", ROOT / "local_cache")),
    )
    args = parser.parse_args()
    if not args.aoi.replace("_", "").isalnum() or not any(
        f"_{args.aoi}_" in f"_{key}_" for key in regions()
    ):
        parser.error("AOI must be an existing project region")
    result = build(args.cache_dir, args.aoi)
    print(
        json.dumps(
            {"aoi": args.aoi, "state": result["state"], "layers": len(result.get("layers", []))}
        )
    )


if __name__ == "__main__":
    main()
