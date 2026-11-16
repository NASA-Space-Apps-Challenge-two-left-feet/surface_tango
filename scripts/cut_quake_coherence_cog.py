"""Cut one AOI's co-event coherence grid to a COG.

The grid is the AOI's own ``dpm_track<N>.zarr`` ``coh_C`` band. A missing
pixel stays NaN. A measured 0 stays 0. This script does not read another
AOI's store and does not call Earth Engine.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.bailasar.config import get_config  # noqa: E402

AOI_CONFIG_KEY = {
    "choco_epicenter": "4_choco_epicenter_quake",
    "valle_del_cauca": "5_valle_del_cauca_quake",
}


def bboxes_match(recorded, expected, tolerance: float = 1e-4) -> bool:
    """True when two [W, S, E, N] boxes agree within ``tolerance`` degrees."""
    if not isinstance(recorded, list | tuple) or len(recorded) != 4:
        return False
    if not isinstance(expected, list | tuple) or len(expected) != 4:
        return False
    try:
        got = [float(value) for value in recorded]
        want = [float(value) for value in expected]
    except (TypeError, ValueError):
        return False
    if not all(math.isfinite(value) for value in got + want):
        return False
    return all(abs(left - right) <= tolerance for left, right in zip(got, want, strict=True))


def coherence_transform(xs: np.ndarray, ys: np.ndarray) -> Affine:
    """Affine for pixel-center coordinates. X increases, Y decreases down the rows."""
    if xs.ndim != 1 or ys.ndim != 1 or xs.size < 2 or ys.size < 2:
        raise ValueError("coherence grid needs at least 2 x and 2 y centers")
    posting_x = float(xs[1] - xs[0])
    posting_y = float(ys[0] - ys[1])
    if not math.isfinite(posting_x) or not math.isfinite(posting_y):
        raise ValueError("coherence posting is not finite")
    if posting_x <= 0 or posting_y <= 0:
        raise ValueError("x must increase and y must decrease")
    if not np.allclose(np.diff(xs), posting_x) or not np.allclose(np.diff(ys), -posting_y):
        raise ValueError("coherence coordinates are not a regular grid")
    return Affine(
        posting_x,
        0.0,
        float(xs[0]) - posting_x / 2.0,
        0.0,
        -posting_y,
        float(ys[0]) + posting_y / 2.0,
    )


def write_coherence_cog(
    values: np.ndarray,
    xs: np.ndarray,
    ys: np.ndarray,
    epsg: int,
    out_path: Path,
) -> None:
    """Write ``values`` unchanged. NaN stays NaN. Nothing is filled."""
    grid = np.array(values, dtype=np.float32, copy=True)
    if grid.shape != (ys.size, xs.size):
        raise ValueError(f"coherence shape {grid.shape} != {(ys.size, xs.size)}")
    grid[~np.isfinite(grid)] = np.nan
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out_path,
        "w",
        driver="COG",
        dtype="float32",
        count=1,
        width=grid.shape[1],
        height=grid.shape[0],
        crs=f"EPSG:{int(epsg)}",
        transform=coherence_transform(xs, ys),
        compress="DEFLATE",
    ) as dataset:
        dataset.write(grid, 1)
        dataset.update_tags(role="coevent_coherence_not_a_damage_class")


def cut_aoi(aoi: str, track: int, cache: Path) -> Path:
    """Cut ``coh_C`` for ``aoi`` after checking the stored window."""
    key = AOI_CONFIG_KEY.get(aoi)
    if key is None:
        raise ValueError(f"{aoi} is not a coverage AOI this cutter serves")
    store = cache / aoi / f"dpm_track{int(track)}.zarr"
    zarr_json = store / "zarr.json"
    if not zarr_json.is_file():
        raise FileNotFoundError(f"{zarr_json} is not on disk")
    attrs = json.loads(zarr_json.read_text(encoding="utf-8")).get("attributes") or {}
    provenance = json.loads(attrs["provenance"])
    expected = get_config().aoi_bbox(key)
    if not bboxes_match(provenance.get("aoi"), expected):
        raise ValueError(f"{aoi} zarr window does not match {key}")
    granule = (provenance.get("pairs") or {}).get("C", {}).get("granule_id")
    if not isinstance(granule, str) or not granule:
        raise ValueError(f"{aoi} zarr has no co-event granule id")
    import xarray as xr

    dataset = xr.open_zarr(store)
    try:
        values = np.asarray(dataset["coh_C"].values)
        xs = np.asarray(dataset["x"].values, dtype=np.float64)
        ys = np.asarray(dataset["y"].values, dtype=np.float64)
    finally:
        dataset.close()
    out_path = cache / aoi / "cogs" / f"{aoi}_coherence_coseismic.tif"
    write_coherence_cog(values, xs, ys, int(provenance["grid"]["epsg"]), out_path)
    manifest_path = cache / aoi / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    if not isinstance(manifest, dict):
        manifest = {}
    bands = manifest.get("bands")
    if not isinstance(bands, dict):
        bands = {}
    finite = int(np.count_nonzero(np.isfinite(values)))
    bands["coherence_coseismic"] = {
        "source_id": granule,
        "status": "cached",
        "asset_type": "NISAR_GUNW",
        "finite_pixel_count": finite,
        "pixel_count": int(values.size),
    }
    manifest["aoi"] = aoi
    manifest["bands"] = bands
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {out_path.relative_to(cache.parent)} finite={finite}/{int(values.size)}",
        flush=True,
    )
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cut an AOI co-event coherence COG")
    parser.add_argument("--aoi", required=True, choices=sorted(AOI_CONFIG_KEY))
    parser.add_argument("--track", type=int, default=11)
    parser.add_argument("--cache", type=Path, default=ROOT / "local_cache")
    args = parser.parse_args(argv)
    try:
        cut_aoi(args.aoi, args.track, args.cache)
    except (OSError, ValueError, KeyError, FileNotFoundError) as exc:
        print(f"FAILED {type(exc).__name__}: {exc}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
