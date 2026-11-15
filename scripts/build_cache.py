"""Unified NISAR and GEE data cache builder for BailaSAR AOIs.

Supports all three hackathon AOIs:
  1. Eje Cafetero (Quake DPM: Track 11 R/C/K coherence & damage proxy)
  2. Aburrá Valley (Landslide kinematics: InSAR phase & rain trigger)
  3. La Mojana (Flood dynamics: Track 47 Frame 5 GCOV dual-pol, HAND & water)

Outputs:
  - local_cache/<aoi>/cogs/*.tif (Cloud-Optimized GeoTIFFs)
  - local_cache/<aoi>/<aoi>_sar_cube.zarr (Zarr v3 cube)
  - local_cache/<aoi>/manifest.json (Band provenance and acquisition IDs)

Rules:
  - No synthetic or fabricated data.
  - Missing bands stay all-NaN float32 and are recorded as 'missing'.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import fsspec
import h5py
import numpy as np
import xarray as xr
import yaml
from rasterio.enums import Resampling
from rasterio.transform import from_bounds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gee_math.ee_session import init_ee  # noqa: E402

CONFIG_PATH = ROOT / "config" / "bailasar.yaml"
CATALOG_PATH = ROOT / "nisar_colombia_granules_2026.json"
LOCAL_CACHE_DIR = ROOT / "local_cache"

DST_CRS = "EPSG:4326"
GEE_NODATA_SENTINEL = -9999.0
DEFAULT_WIDTH = 512
DEFAULT_HEIGHT = 512
MERIT_HYDRO_ASSET = "MERIT/Hydro/v1_0_1"
MERIT_HAND_BAND = "hnd"
MERIT_HYDRO_VERSION = "v1_0_1"
HAND_BAND_NAME = "hand_m"
HAND_PROVENANCE_KEYS = ("band", "version", "grid", "source")

NAME_RE = re.compile(
    r"NISAR_L2_(?P<stream>[A-Z]{2})_(?P<product>[A-Z]{4})_.*?_(?P<pol>[A-Z]{2,4})_(?:[A-Z]_)?"
    r"(?P<t1>\d{8})T\d{6}_\d{8}T\d{6}(?:_(?P<t2>\d{8})T\d{6}_\d{8}T\d{6})?"
)

AOI_ALIASES = {
    "aburra": "1_aburra_medellin_bello",
    "1_aburra_medellin_bello": "1_aburra_medellin_bello",
    "eje_cafetero": "2_eje_cafetero_quake",
    "2_eje_cafetero_quake": "2_eje_cafetero_quake",
    "mojana": "3_la_mojana_caregato",
    "la_mojana": "3_la_mojana_caregato",
    "3_la_mojana_caregato": "3_la_mojana_caregato",
}

SHORT_NAMES = {
    "1_aburra_medellin_bello": "aburra",
    "2_eje_cafetero_quake": "eje_cafetero",
    "3_la_mojana_caregato": "mojana",
}


def load_env_credentials() -> None:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_aois(config_path: Path = CONFIG_PATH) -> dict[str, list[float]]:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    aois = data.get("aois", {})
    if not aois:
        raise ValueError(f"No aois found in {config_path}")
    return aois


def resolve_aoi(aoi_input: str, config_path: Path = CONFIG_PATH) -> tuple[str, str, list[float]]:
    aois = load_aois(config_path)
    canonical = AOI_ALIASES.get(aoi_input)
    if not canonical or canonical not in aois:
        valid = list(AOI_ALIASES.keys())
        raise ValueError(f"Unknown AOI '{aoi_input}'. Valid options: {valid}")
    short_name = SHORT_NAMES[canonical]
    return canonical, short_name, aois[canonical]


def _iso(s: str | None) -> str | None:
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if s else None


def parse_nisar_scene_name(scene_name: str) -> dict[str, Any]:
    m = NAME_RE.search(scene_name)
    if not m:
        return {
            "stream": None,
            "product": None,
            "polarization": None,
            "date_1": None,
            "date_2": None,
        }
    d = m.groupdict()
    return {
        "stream": d["stream"],
        "product": d["product"],
        "polarization": d["pol"],
        "date_1": _iso(d["t1"]),
        "date_2": _iso(d["t2"]),
    }


def make_missing_band(shape: tuple[int, int]) -> np.ndarray:
    return np.full(shape, np.nan, dtype=np.float32)


def check_array_coverage(arr: np.ndarray, min_ratio: float = 0.05) -> bool:
    if arr is None or arr.size == 0:
        return False
    finite_px = np.count_nonzero(np.isfinite(arr))
    return bool(finite_px >= (arr.size * min_ratio))


@dataclass(frozen=True)
class SampleGrid:
    """Affine passed to ee.data.computePixels. Taken from a cube, not hardcoded."""

    crs: str
    width: int
    height: int
    scale_x: float
    scale_y: float
    translate_x: float
    translate_y: float
    clip_bbox: tuple[float, float, float, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "crs": self.crs,
            "width": self.width,
            "height": self.height,
            "scale_x": self.scale_x,
            "scale_y": self.scale_y,
            "translate_x": self.translate_x,
            "translate_y": self.translate_y,
        }


def _is_geographic_bbox(bbox: list[float] | tuple[float, ...]) -> bool:
    west, south, east, north = (float(value) for value in bbox)
    return -180.0 <= west < east <= 180.0 and -90.0 <= south < north <= 90.0


def _edges_match_bbox(
    x_vals: np.ndarray,
    y_vals: np.ndarray,
    bbox: tuple[float, float, float, float],
) -> bool:
    west, south, east, north = bbox
    return bool(
        np.isclose(x_vals[0], west)
        and np.isclose(x_vals[-1], east)
        and np.isclose(y_vals[0], north)
        and np.isclose(y_vals[-1], south)
    )


def grid_from_cube_coords(
    y: np.ndarray,
    x: np.ndarray,
    crs: str,
    bbox: list[float] | tuple[float, ...] | None = None,
) -> SampleGrid:
    """Build the computePixels affine from stored cube coordinates.

    This builder writes an inclusive linspace of the outer edges and samples
    with scale = edge span / pixel count. When the coordinates sit on a
    geographic bbox, that is the affine. Otherwise the coordinates are cell
    centers and the scale is their spacing.
    """
    y_vals = np.asarray(y, dtype=np.float64)
    x_vals = np.asarray(x, dtype=np.float64)
    height = int(y_vals.size)
    width = int(x_vals.size)
    if height < 2 or width < 2:
        raise ValueError("cube grid needs at least 2 samples on each axis")
    if not crs:
        raise ValueError("cube has no crs")

    clip_bbox: tuple[float, float, float, float] | None = None
    edge_aligned = False
    if bbox is not None and len(bbox) == 4 and _is_geographic_bbox(bbox):
        clip_bbox = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        edge_aligned = _edges_match_bbox(x_vals, y_vals, clip_bbox)

    if edge_aligned:
        scale_x = (float(x_vals[-1]) - float(x_vals[0])) / width
        scale_y = (float(y_vals[-1]) - float(y_vals[0])) / height
        translate_x = float(x_vals[0])
        translate_y = float(y_vals[0])
    else:
        dx = float(np.median(np.diff(x_vals)))
        dy = float(np.median(np.diff(y_vals)))
        if not np.isfinite(dx) or not np.isfinite(dy) or dx == 0.0 or dy == 0.0:
            raise ValueError("cube coordinates are not a regular grid")
        scale_x = dx
        scale_y = dy
        translate_x = float(x_vals[0]) - dx / 2.0
        translate_y = float(y_vals[0]) - dy / 2.0

    if clip_bbox is None:
        x_far = translate_x + scale_x * width
        y_far = translate_y + scale_y * height
        clip_bbox = (
            min(translate_x, x_far),
            min(translate_y, y_far),
            max(translate_x, x_far),
            max(translate_y, y_far),
        )
    return SampleGrid(
        crs=str(crs),
        width=width,
        height=height,
        scale_x=scale_x,
        scale_y=scale_y,
        translate_x=translate_x,
        translate_y=translate_y,
        clip_bbox=clip_bbox,
    )


def grid_from_dataset(dataset: xr.Dataset) -> SampleGrid:
    crs = dataset.attrs.get("crs")
    if not crs:
        raise ValueError("cube attributes have no crs")
    return grid_from_cube_coords(
        dataset.y.values,
        dataset.x.values,
        str(crs),
        dataset.attrs.get("bbox"),
    )


def sample_grid_from_bbox(
    bbox: list[float],
    width: int,
    height: int,
    crs: str = DST_CRS,
) -> SampleGrid:
    """Affine for a full cache build: outer edges, scale = span / pixel count."""
    west, south, east, north = (float(value) for value in bbox)
    return SampleGrid(
        crs=crs,
        width=width,
        height=height,
        scale_x=(east - west) / width,
        scale_y=-(north - south) / height,
        translate_x=west,
        translate_y=north,
        clip_bbox=(west, south, east, north),
    )


def merit_hand_source_id(grid: SampleGrid) -> str:
    return (
        f"GEE {MERIT_HYDRO_ASSET} band {MERIT_HAND_BAND} "
        f"version {MERIT_HYDRO_VERSION} "
        f"grid {grid.crs} {grid.width}x{grid.height}"
    )


def hand_band_meta(grid: SampleGrid) -> dict[str, Any]:
    return {
        "band": MERIT_HAND_BAND,
        "version": MERIT_HYDRO_VERSION,
        "grid": grid.as_dict(),
        "source": MERIT_HYDRO_ASSET,
    }


def structured_band(structured: np.ndarray, band_name: str) -> np.ndarray:
    """Pick one computePixels field. A mask field is not the measurement."""
    names = getattr(structured.dtype, "names", None)
    if not names:
        return np.asarray(structured)
    if band_name in names:
        return np.asarray(structured[band_name])
    matches = [
        name for name in names if band_name.lower() in name.lower() and "mask" not in name.lower()
    ]
    if len(matches) == 1:
        return np.asarray(structured[matches[0]])
    raise KeyError(f"computePixels fields {list(names)} do not include {band_name}")


def init_earthaccess() -> str | None:
    load_env_credentials()
    token = os.environ.get("EARTHDATA_TOKEN")
    if token:
        return token
    # Try reading from ~/.netrc
    netrc = Path.home() / ".netrc"
    if netrc.exists():
        for line in netrc.read_text(encoding="utf-8").splitlines():
            if "password" in line:
                parts = line.strip().split()
                if len(parts) >= 2:
                    return parts[-1]
    return None


def init_gee_session() -> bool:
    load_env_credentials()
    try:
        init_ee(high_volume=False)
        return True
    except Exception as exc:
        print(
            f"[WARN] GEE initialization failed ({type(exc).__name__}: {exc}). GEE bands marked missing."
        )
        return False


def stream_nisar_h5_subdataset(
    url: str,
    h5_path: str,
    dst_bbox: list[float],
    dst_shape: tuple[int, int],
    token: str,
    resampling: Resampling = Resampling.bilinear,
) -> np.ndarray | None:
    """Streams NISAR subdataset via fsspec/h5py, clips to bbox, and warps to EPSG:4326."""
    try:
        from pyproj import Transformer

        fs = fsspec.filesystem(
            "https",
            client_kwargs={"headers": {"Authorization": f"Bearer {token}"}},
        )
        with fs.open(url, block_size=2 * 2**20, cache_type="blockcache") as f:
            with h5py.File(f, "r") as h:
                # Prefer 80m multi-looked frequencyB grid when available for optimal I/O throughput
                if "/frequencyA/" in h5_path:
                    alt_path = h5_path.replace("/frequencyA/", "/frequencyB/")
                    if alt_path in h:
                        h5_path = alt_path
                elif h5_path not in h:
                    alt_path = h5_path.replace("/frequencyB/", "/frequencyA/")
                    if alt_path in h:
                        h5_path = alt_path

                if h5_path not in h:
                    print(f"   [WARN] Subdataset {h5_path} not found in HDF5.")
                    return None

                dset = h[h5_path]
                grp_path = h5_path.rsplit("/", 1)[0]
                grp = h[grp_path]

                # Check coordinates and projection
                if "xCoordinates" in grp and "yCoordinates" in grp:
                    x_coords = grp["xCoordinates"][:]
                    y_coords = grp["yCoordinates"][:]
                elif "xCoordinates" in h[grp_path.rsplit("/", 1)[0]]:
                    parent_grp = h[grp_path.rsplit("/", 1)[0]]
                    x_coords = parent_grp["xCoordinates"][:]
                    y_coords = parent_grp["yCoordinates"][:]
                else:
                    print(f"   [WARN] Coordinate grids not found for {h5_path}.")
                    return None

                epsg = 32618
                if "projection" in grp and "epsg_code" in grp["projection"].attrs:
                    try:
                        epsg = int(grp["projection"].attrs["epsg_code"])
                    except Exception:
                        pass

                # Convert WGS84 bbox [W, S, E, N] to native UTM bounds
                transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
                utm_min_x, utm_min_y = transformer.transform(dst_bbox[0], dst_bbox[1])
                utm_max_x, utm_max_y = transformer.transform(dst_bbox[2], dst_bbox[3])

                x_min_val, x_max_val = min(utm_min_x, utm_max_x), max(utm_min_x, utm_max_x)
                y_min_val, y_max_val = min(utm_min_y, utm_max_y), max(utm_min_y, utm_max_y)

                # Find index bounding box with a 5% margin
                dx = abs(x_coords[1] - x_coords[0]) if len(x_coords) > 1 else 80.0
                dy = abs(y_coords[1] - y_coords[0]) if len(y_coords) > 1 else 80.0

                margin_x = dx * 10
                margin_y = dy * 10

                x_mask = (x_coords >= (x_min_val - margin_x)) & (x_coords <= (x_max_val + margin_x))
                y_mask = (y_coords >= (y_min_val - margin_y)) & (y_coords <= (y_max_val + margin_y))

                x_indices = np.where(x_mask)[0]
                y_indices = np.where(y_mask)[0]

                if len(x_indices) == 0 or len(y_indices) == 0:
                    print(
                        "   [WARN] AOI bounding box does not intersect granule swath coordinates."
                    )
                    return None

                x_start, x_end = int(x_indices.min()), int(x_indices.max()) + 1
                y_start, y_end = int(y_indices.min()), int(y_indices.max()) + 1

                # Read only spatial slice
                sub_arr = dset[y_start:y_end, x_start:x_end]
                sub_x = x_coords[x_start:x_end]
                sub_y = y_coords[y_start:y_end]

        sub_arr = sub_arr.astype(np.float32)
        da = xr.DataArray(sub_arr, dims=("y", "x"), coords={"y": sub_y, "x": sub_x})
        da.rio.write_crs(f"EPSG:{epsg}", inplace=True)

        dst_height, dst_width = dst_shape
        dst_transform = from_bounds(*dst_bbox, dst_width, dst_height)
        da_warped = da.rio.reproject(
            dst_crs=DST_CRS,
            shape=(dst_height, dst_width),
            transform=dst_transform,
            resampling=resampling,
        )
        arr = da_warped.values.astype(np.float32)
        arr[~np.isfinite(arr)] = np.nan
        return arr
    except Exception as exc:
        print(f"   [WARN] Failed streaming {h5_path} from {url}: {exc}")
        return None


def gee_nodata_to_nan(arr: np.ndarray) -> np.ndarray:
    """Map the GEE nodata sentinel and non-finite values to NaN (missing stays missing)."""
    out = np.array(arr, dtype=np.float32, copy=True)
    out[out == GEE_NODATA_SENTINEL] = np.nan
    out[~np.isfinite(out)] = np.nan
    return out


def hand_array_from_sample(values: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Float32 HAND. Sentinel and non-finite samples stay NaN. 0 m is kept.

    Nothing is zero-filled.
    """
    arr = gee_nodata_to_nan(np.asarray(values))
    if arr.shape != shape:
        raise ValueError(f"HAND sample shape {arr.shape} != grid {shape}")
    return arr


def fetch_gee_layer(
    image: Any,
    band_name: str,
    bbox: list[float],
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    grid: SampleGrid | None = None,
) -> np.ndarray | None:
    try:
        import ee

        sample = grid if grid is not None else sample_grid_from_bbox(bbox, width, height, DST_CRS)
        region = ee.Geometry.Rectangle(list(sample.clip_bbox))
        # Masked pixels become the sentinel, then NaN. Do not unmask(0).
        # Do not call image.resample(): nearest is the computePixels default,
        # and "nearest" is not a legal resample() mode.
        params = {
            "expression": image.clip(region).unmask(GEE_NODATA_SENTINEL),
            "fileFormat": "NPY",
            "grid": {
                "dimensions": {"width": sample.width, "height": sample.height},
                "affineTransform": {
                    "scaleX": sample.scale_x,
                    "shearX": 0,
                    "translateX": sample.translate_x,
                    "shearY": 0,
                    "scaleY": sample.scale_y,
                    "translateY": sample.translate_y,
                },
                "crsCode": sample.crs,
            },
        }
        raw_bytes = ee.data.computePixels(params)
        structured = np.load(io.BytesIO(raw_bytes))
        arr = structured_band(structured, band_name)
        return gee_nodata_to_nan(arr)
    except Exception as exc:
        print(f"   [WARN] GEE computePixels failed for {band_name}: {exc}")
        return None


def fetch_merit_hand(grid: SampleGrid) -> np.ndarray | None:
    """Sample MERIT Hydro band hnd onto ``grid``. Missing pixels stay NaN."""
    import ee

    image = ee.Image(MERIT_HYDRO_ASSET).select(MERIT_HAND_BAND)
    sampled = fetch_gee_layer(image, MERIT_HAND_BAND, list(grid.clip_bbox), grid=grid)
    if sampled is None:
        return None
    return hand_array_from_sample(sampled, (grid.height, grid.width))


def save_array_as_cog(
    arr: np.ndarray,
    out_path: Path,
    bbox: list[float],
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    da = xr.DataArray(
        arr.astype(np.float32),
        dims=("y", "x"),
        coords={
            "y": np.linspace(bbox[3], bbox[1], height),
            "x": np.linspace(bbox[0], bbox[2], width),
        },
    )
    da.rio.write_crs(DST_CRS, inplace=True)
    da.rio.write_transform(from_bounds(*bbox, width, height), inplace=True)
    da.rio.to_raster(
        out_path,
        driver="COG",
        compress="DEFLATE",
        predictor=2,
        overview_resampling="AVERAGE",
    )
    return out_path


def assemble_manifest_record(
    aoi_key: str,
    aoi_short: str,
    bbox: list[float],
    bands: dict[str, dict[str, Any]],
    cog_paths: dict[str, str],
    zarr_path: str,
) -> dict[str, Any]:
    provenance: dict[str, str] = {}
    band_records: dict[str, Any] = {}

    for name, data in bands.items():
        arr = data.get("arr")
        src_id = data.get("source_id")
        is_missing = (
            arr is None
            or src_id is None
            or src_id == "missing"
            or not check_array_coverage(arr, 0.05)
        )

        if is_missing:
            provenance[name] = "missing"
            record = {
                "source_id": "missing",
                "status": "missing",
                "asset_type": data.get("asset_type", "UNKNOWN"),
                "stream": data.get("stream"),
                "dates": data.get("dates"),
                "finite_pixel_count": 0,
                "finite_pixel_ratio": 0.0,
            }
        else:
            provenance[name] = cast(str, src_id)
            present_arr = cast(np.ndarray, arr)
            finite_cnt = int(np.count_nonzero(np.isfinite(present_arr)))
            ratio = float(finite_cnt / present_arr.size) if present_arr.size > 0 else 0.0
            record = {
                "source_id": src_id,
                "status": "cached",
                "asset_type": data.get("asset_type", "UNKNOWN"),
                "stream": data.get("stream"),
                "dates": data.get("dates"),
                "finite_pixel_count": finite_cnt,
                "finite_pixel_ratio": round(ratio, 4),
            }
        for key in HAND_PROVENANCE_KEYS:
            if data.get(key) is not None:
                record[key] = data[key]
        band_records[name] = record

    manifest = {
        "aoi": aoi_short,
        "aoi_key": aoi_key,
        "bbox": bbox,
        "zarr_cube_path": str(zarr_path),
        "bands": band_records,
        "nisar_granule_provenance": provenance,
        "cog_paths": cog_paths,
        "local_tile_templates": {
            "landslide": f"http://localhost:8000/api/local-tiles/{aoi_short}/landslide/{{z}}/{{x}}/{{y}}.png",
            "flood": f"http://localhost:8000/api/local-tiles/{aoi_short}/flood/{{z}}/{{x}}/{{y}}.png",
            "earthquake": f"http://localhost:8000/api/local-tiles/{aoi_short}/earthquake/{{z}}/{{x}}/{{y}}.png",
            "biomass": f"http://localhost:8000/api/local-tiles/{aoi_short}/biomass/{{z}}/{{x}}/{{y}}.png",
            "optical_s2": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
            "cband_s1": f"http://localhost:8000/api/local-tiles/{aoi_short}/cband/{{z}}/{{x}}/{{y}}.png",
        },
    }
    return manifest


def build_cache_for_aoi(
    aoi_input: str,
    chirps_start: str | None = None,
    chirps_end: str | None = None,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> Path:
    canonical_key, aoi_short, bbox = resolve_aoi(aoi_input)
    print("\n========================================================")
    print(f"🚀 Building Cache for AOI: {aoi_short} ({canonical_key})")
    print(f"   BBOX: {bbox}")
    print("========================================================")

    out_dir = LOCAL_CACHE_DIR / aoi_short
    cogs_dir = out_dir / "cogs"
    zarr_path = out_dir / f"{aoi_short}_sar_cube.zarr"
    manifest_path = out_dir / "manifest.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    cogs_dir.mkdir(parents=True, exist_ok=True)

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8")) if CATALOG_PATH.exists() else {}
    aoi_granules = catalog.get("aois", {}).get(canonical_key, {}).get("granules", [])
    granule_lookup = {g["scene_name"]: g for g in aoi_granules if g.get("scene_name")}

    earthdata_token = init_earthaccess()
    gee_online = init_gee_session()

    bands: dict[str, dict[str, Any]] = {}

    def fetch_nisar_band(
        scene_name: str | None,
        subdataset: str,
        asset_type: str,
        resampling: Resampling = Resampling.bilinear,
    ) -> tuple[np.ndarray | None, str | None, dict]:
        if not scene_name or not earthdata_token or scene_name not in granule_lookup:
            return None, None, {}
        meta = granule_lookup[scene_name]
        url = meta.get("url")
        if not url:
            return None, None, {}
        print(f"📡 Streaming {meta['scene_name'][:50]}... [{subdataset.split('/')[-1]}]")
        arr = stream_nisar_h5_subdataset(
            url, subdataset, bbox, (height, width), earthdata_token, resampling=resampling
        )
        if arr is not None and check_array_coverage(arr, 0.05):
            return arr, scene_name, meta
        return None, scene_name, meta

    # 1. Fetch GEE layers
    if gee_online:
        import ee

        print("🌍 Querying GEE layers (FABDEM, CHIRPS, ESA CCI AGB)...")
        aoi_geom = ee.Geometry.Rectangle(bbox)
        try:
            fabdem = (
                ee.ImageCollection("projects/sat-io/open-datasets/FABDEM")
                .filterBounds(aoi_geom)
                .mosaic()
            )
            slope_arr = fetch_gee_layer(
                ee.Terrain.slope(fabdem).rename("slope"), "slope", bbox, width, height
            )
        except Exception:
            slope_arr = None

        if chirps_start and chirps_end:
            try:
                chirps = (
                    ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
                    .filterDate(chirps_start, chirps_end)
                    .sum()
                    .rename("rain")
                )
                rain_arr = fetch_gee_layer(chirps, "rain", bbox, width, height)
            except Exception:
                rain_arr = None
        else:
            print("   [INFO] No CHIRPS window given; recording rain_15d_mm as 'missing'.")
            rain_arr = None

        try:
            esa_agb = (
                ee.ImageCollection("projects/sat-io/open-datasets/ESA/ESA_CCI_AGB")
                .sort("system:time_start", False)
                .first()
                .select([0], ["agb"])
            )
            agb_arr = fetch_gee_layer(esa_agb, "agb", bbox, width, height)
        except Exception:
            agb_arr = None
    else:
        slope_arr = rain_arr = agb_arr = None

    bands["slope_deg"] = {
        "arr": slope_arr,
        "source_id": "GEE projects/sat-io/open-datasets/FABDEM" if slope_arr is not None else None,
        "asset_type": "GEE",
    }
    bands["rain_15d_mm"] = {
        "arr": rain_arr,
        "source_id": f"GEE UCSB-CHG/CHIRPS/DAILY {chirps_start}..{chirps_end}"
        if rain_arr is not None
        else None,
        "asset_type": "GEE",
    }
    bands["agb_mgha"] = {
        "arr": agb_arr,
        "source_id": "GEE projects/sat-io/open-datasets/ESA/ESA_CCI_AGB"
        if agb_arr is not None
        else None,
        "asset_type": "GEE",
    }

    # 2. AOI-specific NISAR Granule Selection
    gunw_base = "/science/LSAR/GUNW/grids/frequencyA"
    gcov_base = "/science/LSAR/GCOV/grids/frequencyA"

    if aoi_short == "eje_cafetero":
        # Track 11 Quake Triplet (R, C, K) from catalog
        triplets = catalog.get("quake_triplets", [])
        t11: dict = next((t for t in triplets if t.get("track") == 11), {})
        scene_r = t11.get("R")
        scene_c = t11.get("C")
        scene_k = t11.get("K")

        # Coherence R, C, K
        arr_coh_r, id_r, meta_r = fetch_nisar_band(
            scene_r, f"{gunw_base}/unwrappedInterferogram/HH/coherenceMagnitude", "NISAR_GUNW"
        )
        bands["coherence_R"] = {
            "arr": arr_coh_r,
            "source_id": id_r,
            "asset_type": "NISAR_GUNW",
            "stream": meta_r.get("stream"),
            "dates": [meta_r.get("date_1"), meta_r.get("date_2")],
        }

        arr_coh_c, id_c, meta_c = fetch_nisar_band(
            scene_c, f"{gunw_base}/unwrappedInterferogram/HH/coherenceMagnitude", "NISAR_GUNW"
        )
        bands["coherence_C"] = {
            "arr": arr_coh_c,
            "source_id": id_c,
            "asset_type": "NISAR_GUNW",
            "stream": meta_c.get("stream"),
            "dates": [meta_c.get("date_1"), meta_c.get("date_2")],
        }
        bands["coherence_coseismic"] = bands["coherence_C"]

        arr_coh_k, id_k, meta_k = fetch_nisar_band(
            scene_k, f"{gunw_base}/unwrappedInterferogram/HH/coherenceMagnitude", "NISAR_GUNW"
        )
        bands["coherence_K"] = {
            "arr": arr_coh_k,
            "source_id": id_k,
            "asset_type": "NISAR_GUNW",
            "stream": meta_k.get("stream"),
            "dates": [meta_k.get("date_1"), meta_k.get("date_2")],
        }

        # C-pair phase & screen
        arr_unw, id_unw, _ = fetch_nisar_band(
            scene_c, f"{gunw_base}/unwrappedInterferogram/HH/unwrappedPhase", "NISAR_GUNW"
        )
        arr_iono, id_iono, _ = fetch_nisar_band(
            scene_c, f"{gunw_base}/unwrappedInterferogram/HH/ionospherePhaseScreen", "NISAR_GUNW"
        )
        arr_cc, id_cc, _ = fetch_nisar_band(
            scene_c,
            f"{gunw_base}/unwrappedInterferogram/HH/connectedComponents",
            "NISAR_GUNW",
            resampling=Resampling.nearest,
        )

        bands["gunw_ionosphere"] = {
            "arr": arr_iono,
            "source_id": id_iono,
            "asset_type": "NISAR_GUNW",
        }
        bands["gunw_conncomp"] = {"arr": arr_cc, "source_id": id_cc, "asset_type": "NISAR_GUNW"}

        if arr_unw is not None and arr_iono is not None:
            phase_corr = (arr_unw - arr_iono).astype(np.float32)
            disp_mm = (phase_corr * (-240.0 / (4.0 * math.pi))).astype(np.float32)
            src_corr = f"{id_c} (ionosphere screen applied)"
        else:
            phase_corr = disp_mm = None
            src_corr = None

        bands["gunw_phase_corr"] = {
            "arr": phase_corr,
            "source_id": src_corr,
            "asset_type": "NISAR_GUNW",
        }
        bands["los_disp_mm"] = {"arr": disp_mm, "source_id": src_corr, "asset_type": "NISAR_GUNW"}

        # GCOV for Eje Cafetero: bracket the 2026-08-10 quake event
        gcov_t11 = [
            g for g in aoi_granules if g.get("processing_level") == "GCOV" and g.get("track") == 11
        ]
        gcov_post_list = [g for g in gcov_t11 if (g.get("date_1") or "") >= "2026-08-10"]
        gcov_pre_list = [g for g in gcov_t11 if (g.get("date_1") or "") < "2026-08-10"]
        gcov_post_list.sort(key=lambda x: x.get("start_time") or "")
        gcov_pre_list.sort(key=lambda x: x.get("start_time") or "", reverse=True)
        gcov_post = (
            gcov_post_list[0]["scene_name"]
            if len(gcov_post_list) > 0
            else (gcov_t11[0]["scene_name"] if gcov_t11 else None)
        )
        gcov_pre = gcov_pre_list[0]["scene_name"] if len(gcov_pre_list) > 0 else gcov_post

        arr_hh_post, id_hhp, m_hhp = fetch_nisar_band(gcov_post, f"{gcov_base}/HHHH", "NISAR_GCOV")
        arr_hv_post, id_hvp, m_hvp = fetch_nisar_band(gcov_post, f"{gcov_base}/HVHV", "NISAR_GCOV")
        arr_hh_pre, id_hhpre, m_hhpre = fetch_nisar_band(
            gcov_pre, f"{gcov_base}/HHHH", "NISAR_GCOV"
        )
        arr_hv_pre, id_hvpre, m_hvpre = fetch_nisar_band(
            gcov_pre, f"{gcov_base}/HVHV", "NISAR_GCOV"
        )

        bands["gcov_hhhh_post"] = {
            "arr": arr_hh_post,
            "source_id": id_hhp,
            "asset_type": "NISAR_GCOV",
            "stream": m_hhp.get("stream"),
        }
        bands["gcov_hvhv_post"] = {
            "arr": arr_hv_post,
            "source_id": id_hvp,
            "asset_type": "NISAR_GCOV",
            "stream": m_hvp.get("stream"),
        }
        bands["gcov_hhhh_pre"] = {
            "arr": arr_hh_pre,
            "source_id": id_hhpre,
            "asset_type": "NISAR_GCOV",
            "stream": m_hhpre.get("stream"),
        }
        bands["gcov_hvhv_pre"] = {
            "arr": arr_hv_pre,
            "source_id": id_hvpre,
            "asset_type": "NISAR_GCOV",
            "stream": m_hvpre.get("stream"),
        }

    elif aoi_short == "aburra":
        gunw_list = [g for g in aoi_granules if g.get("processing_level") == "GUNW"]
        gunw_list.sort(key=lambda x: x.get("start_time") or "", reverse=True)
        gunw_post = gunw_list[0]["scene_name"] if len(gunw_list) > 0 else None
        gunw_pre = gunw_list[1]["scene_name"] if len(gunw_list) > 1 else gunw_post

        arr_coh_post, id_cp, m_cp = fetch_nisar_band(
            gunw_post, f"{gunw_base}/unwrappedInterferogram/HH/coherenceMagnitude", "NISAR_GUNW"
        )
        arr_coh_pre, id_cpre, m_cpre = fetch_nisar_band(
            gunw_pre, f"{gunw_base}/unwrappedInterferogram/HH/coherenceMagnitude", "NISAR_GUNW"
        )
        bands["coherence_coseismic"] = {
            "arr": arr_coh_post,
            "source_id": id_cp,
            "asset_type": "NISAR_GUNW",
            "stream": m_cp.get("stream"),
        }
        bands["gunw_coherence"] = {
            "arr": arr_coh_pre,
            "source_id": id_cpre,
            "asset_type": "NISAR_GUNW",
            "stream": m_cpre.get("stream"),
        }
        bands["coherence_R"] = bands["gunw_coherence"]
        bands["coherence_C"] = bands["coherence_coseismic"]
        bands["coherence_K"] = {"arr": None, "source_id": None, "asset_type": "NISAR_GUNW"}

        arr_unw, id_unw, _ = fetch_nisar_band(
            gunw_post, f"{gunw_base}/unwrappedInterferogram/HH/unwrappedPhase", "NISAR_GUNW"
        )
        arr_iono, id_iono, _ = fetch_nisar_band(
            gunw_post, f"{gunw_base}/unwrappedInterferogram/HH/ionospherePhaseScreen", "NISAR_GUNW"
        )
        arr_cc, id_cc, _ = fetch_nisar_band(
            gunw_post,
            f"{gunw_base}/unwrappedInterferogram/HH/connectedComponents",
            "NISAR_GUNW",
            resampling=Resampling.nearest,
        )

        bands["gunw_ionosphere"] = {
            "arr": arr_iono,
            "source_id": id_iono,
            "asset_type": "NISAR_GUNW",
        }
        bands["gunw_conncomp"] = {"arr": arr_cc, "source_id": id_cc, "asset_type": "NISAR_GUNW"}

        if arr_unw is not None and arr_iono is not None:
            phase_corr = (arr_unw - arr_iono).astype(np.float32)
            disp_mm = (phase_corr * (-240.0 / (4.0 * math.pi))).astype(np.float32)
            src_corr = f"{id_cp} (ionosphere screen applied)"
        else:
            phase_corr = disp_mm = None
            src_corr = None

        bands["gunw_phase_corr"] = {
            "arr": phase_corr,
            "source_id": src_corr,
            "asset_type": "NISAR_GUNW",
        }
        bands["los_disp_mm"] = {"arr": disp_mm, "source_id": src_corr, "asset_type": "NISAR_GUNW"}

        gcov_list = [g for g in aoi_granules if g.get("processing_level") == "GCOV"]
        gcov_list.sort(key=lambda x: x.get("start_time") or "", reverse=True)
        gcov_post = gcov_list[0]["scene_name"] if len(gcov_list) > 0 else None
        gcov_pre = gcov_list[1]["scene_name"] if len(gcov_list) > 1 else gcov_post

        arr_hh_post, id_hhp, m_hhp = fetch_nisar_band(gcov_post, f"{gcov_base}/HHHH", "NISAR_GCOV")
        arr_hv_post, id_hvp, m_hvp = fetch_nisar_band(gcov_post, f"{gcov_base}/HVHV", "NISAR_GCOV")
        arr_hh_pre, id_hhpre, m_hhpre = fetch_nisar_band(
            gcov_pre, f"{gcov_base}/HHHH", "NISAR_GCOV"
        )
        arr_hv_pre, id_hvpre, m_hvpre = fetch_nisar_band(
            gcov_pre, f"{gcov_base}/HVHV", "NISAR_GCOV"
        )

        bands["gcov_hhhh_post"] = {
            "arr": arr_hh_post,
            "source_id": id_hhp,
            "asset_type": "NISAR_GCOV",
            "stream": m_hhp.get("stream"),
        }
        bands["gcov_hvhv_post"] = {
            "arr": arr_hv_post,
            "source_id": id_hvp,
            "asset_type": "NISAR_GCOV",
            "stream": m_hvp.get("stream"),
        }
        bands["gcov_hhhh_pre"] = {
            "arr": arr_hh_pre,
            "source_id": id_hhpre,
            "asset_type": "NISAR_GCOV",
            "stream": m_hhpre.get("stream"),
        }
        bands["gcov_hvhv_pre"] = {
            "arr": arr_hv_pre,
            "source_id": id_hvpre,
            "asset_type": "NISAR_GCOV",
            "stream": m_hvpre.get("stream"),
        }

    elif aoi_short == "mojana":
        # Track 47 Frame 5 GCOV dual-pol stack
        gcov_t47 = [
            g
            for g in aoi_granules
            if g.get("processing_level") == "GCOV" and g.get("track") == 47 and g.get("frame") == 5
        ]
        gcov_t47.sort(key=lambda x: x.get("start_time") or "", reverse=True)
        gcov_post = gcov_t47[0]["scene_name"] if len(gcov_t47) > 0 else None
        gcov_pre = gcov_t47[1]["scene_name"] if len(gcov_t47) > 1 else gcov_post

        arr_hh_post, id_hhp, m_hhp = fetch_nisar_band(gcov_post, f"{gcov_base}/HHHH", "NISAR_GCOV")
        arr_hv_post, id_hvp, m_hvp = fetch_nisar_band(gcov_post, f"{gcov_base}/HVHV", "NISAR_GCOV")
        arr_hh_pre, id_hhpre, m_hhpre = fetch_nisar_band(
            gcov_pre, f"{gcov_base}/HHHH", "NISAR_GCOV"
        )
        arr_hv_pre, id_hvpre, m_hvpre = fetch_nisar_band(
            gcov_pre, f"{gcov_base}/HVHV", "NISAR_GCOV"
        )

        bands["gcov_hhhh_post"] = {
            "arr": arr_hh_post,
            "source_id": id_hhp,
            "asset_type": "NISAR_GCOV",
            "stream": m_hhp.get("stream"),
        }
        bands["gcov_hvhv_post"] = {
            "arr": arr_hv_post,
            "source_id": id_hvp,
            "asset_type": "NISAR_GCOV",
            "stream": m_hvp.get("stream"),
        }
        bands["gcov_hhhh_pre"] = {
            "arr": arr_hh_pre,
            "source_id": id_hhpre,
            "asset_type": "NISAR_GCOV",
            "stream": m_hhpre.get("stream"),
        }
        bands["gcov_hvhv_pre"] = {
            "arr": arr_hv_pre,
            "source_id": id_hvpre,
            "asset_type": "NISAR_GCOV",
            "stream": m_hvpre.get("stream"),
        }

        # GUNW track 47 frame 5 if available
        gunw_t47 = [
            g
            for g in aoi_granules
            if g.get("processing_level") == "GUNW" and g.get("track") == 47 and g.get("frame") == 5
        ]
        gunw_t47.sort(key=lambda x: x.get("start_time") or "", reverse=True)
        gunw_post = gunw_t47[0]["scene_name"] if len(gunw_t47) > 0 else None

        arr_coh, id_coh, m_coh = fetch_nisar_band(
            gunw_post, f"{gunw_base}/unwrappedInterferogram/HH/coherenceMagnitude", "NISAR_GUNW"
        )
        bands["coherence_coseismic"] = {
            "arr": arr_coh,
            "source_id": id_coh,
            "asset_type": "NISAR_GUNW",
            "stream": m_coh.get("stream"),
        }
        bands["gunw_coherence"] = bands["coherence_coseismic"]
        bands["coherence_R"] = bands["gunw_coherence"]
        bands["coherence_C"] = bands["coherence_coseismic"]
        bands["coherence_K"] = {"arr": None, "source_id": None, "asset_type": "NISAR_GUNW"}

        arr_unw, id_unw, _ = fetch_nisar_band(
            gunw_post, f"{gunw_base}/unwrappedInterferogram/HH/unwrappedPhase", "NISAR_GUNW"
        )
        arr_iono, id_iono, _ = fetch_nisar_band(
            gunw_post, f"{gunw_base}/unwrappedInterferogram/HH/ionospherePhaseScreen", "NISAR_GUNW"
        )
        arr_cc, id_cc, _ = fetch_nisar_band(
            gunw_post,
            f"{gunw_base}/unwrappedInterferogram/HH/connectedComponents",
            "NISAR_GUNW",
            resampling=Resampling.nearest,
        )

        bands["gunw_ionosphere"] = {
            "arr": arr_iono,
            "source_id": id_iono,
            "asset_type": "NISAR_GUNW",
        }
        bands["gunw_conncomp"] = {"arr": arr_cc, "source_id": id_cc, "asset_type": "NISAR_GUNW"}

        if arr_unw is not None and arr_iono is not None:
            phase_corr = (arr_unw - arr_iono).astype(np.float32)
            disp_mm = (phase_corr * (-240.0 / (4.0 * math.pi))).astype(np.float32)
            src_corr = f"{id_coh} (ionosphere screen applied)"
        else:
            phase_corr = disp_mm = None
            src_corr = None

        bands["gunw_phase_corr"] = {
            "arr": phase_corr,
            "source_id": src_corr,
            "asset_type": "NISAR_GUNW",
        }
        bands["los_disp_mm"] = {"arr": disp_mm, "source_id": src_corr, "asset_type": "NISAR_GUNW"}

        hand_grid = sample_grid_from_bbox(bbox, width, height, DST_CRS)
        hand_arr = fetch_merit_hand(hand_grid) if gee_online else None
        bands[HAND_BAND_NAME] = {
            "arr": hand_arr,
            "source_id": merit_hand_source_id(hand_grid) if hand_arr is not None else None,
            "asset_type": "GEE",
            **hand_band_meta(hand_grid),
        }

    # 3. Save COGs
    print(f"💾 Saving Cloud-Optimized GeoTIFFs (COGs) to {cogs_dir}...")
    cog_files: dict[str, str] = {}
    for name, item in bands.items():
        arr = item.get("arr")
        if arr is None or not check_array_coverage(arr, 0.05):
            arr = make_missing_band((height, width))
            item["arr"] = arr
        cog_path = cogs_dir / f"{aoi_short}_{name}.tif"
        save_array_as_cog(arr, cog_path, bbox, width, height)
        cog_files[name] = str(cog_path)

    # 4. Save Zarr v3 cube
    print(f"📦 Compiling Zarr v3 multi-hazard cube at {zarr_path}...")
    y_coords = np.linspace(bbox[3], bbox[1], height)
    x_coords = np.linspace(bbox[0], bbox[2], width)

    data_vars = {name: (("y", "x"), item["arr"].astype(np.float32)) for name, item in bands.items()}
    encoding = {name: {"chunks": (256, 256)} for name in data_vars}
    ds = xr.Dataset(
        data_vars,
        coords={"y": y_coords, "x": x_coords},
        attrs={
            "aoi": aoi_short,
            "aoi_key": canonical_key,
            "bbox": bbox,
            "crs": DST_CRS,
        },
    )
    ds.to_zarr(zarr_path, mode="w", encoding=encoding)

    # 5. Save Manifest
    print(f"📋 Writing manifest to {manifest_path}...")
    manifest = assemble_manifest_record(
        aoi_key=canonical_key,
        aoi_short=aoi_short,
        bbox=bbox,
        bands=bands,
        cog_paths=cog_files,
        zarr_path=str(zarr_path),
    )
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"✅ Cache built for {aoi_short}: {len(bands)} bands processed.")
    return manifest_path


def hand_manifest_entry(arr: np.ndarray, grid: SampleGrid) -> tuple[dict[str, Any], str]:
    """Manifest record for hand_m. Finite pixels stay cached; an empty sample is missing."""
    meta = hand_band_meta(grid)
    finite = int(np.count_nonzero(np.isfinite(arr)))
    total = int(arr.size)
    if finite == 0 or total == 0:
        record = {
            "source_id": "missing",
            "status": "missing",
            "asset_type": "GEE",
            "stream": None,
            "dates": None,
            "finite_pixel_count": 0,
            "finite_pixel_ratio": 0.0,
            **meta,
        }
        return record, "missing"
    source_id = merit_hand_source_id(grid)
    record = {
        "source_id": source_id,
        "status": "cached",
        "asset_type": "GEE",
        "stream": None,
        "dates": None,
        "finite_pixel_count": finite,
        "finite_pixel_ratio": round(finite / total, 4),
        **meta,
    }
    return record, source_id


def write_hand_variable(
    zarr_path: Path,
    arr: np.ndarray,
    y_vals: np.ndarray,
    x_vals: np.ndarray,
    chunk_shape: tuple[int, int],
    cube_attrs: dict[str, Any],
) -> None:
    """Append hand_m. Cube attributes are written back so mode='a' does not clear them."""
    out = xr.Dataset(
        {HAND_BAND_NAME: (("y", "x"), np.asarray(arr, dtype=np.float32))},
        coords={"y": ("y", y_vals), "x": ("x", x_vals)},
        attrs=cube_attrs,
    )
    out.to_zarr(zarr_path, mode="a", encoding={HAND_BAND_NAME: {"chunks": chunk_shape}})


def append_merit_hand_band(aoi_input: str) -> Path:
    """Add only hand_m to an existing La Mojana cube.

    The sample grid is read from the cube. Other bands, COGs, tiles and
    provenance.json are left untouched.
    """
    _canonical, aoi_short, _bbox = resolve_aoi(aoi_input)
    if aoi_short != "mojana":
        raise ValueError("hand_m is only added to the La Mojana cube")
    out_dir = LOCAL_CACHE_DIR / aoi_short
    zarr_path = out_dir / f"{aoi_short}_sar_cube.zarr"
    manifest_path = out_dir / "manifest.json"
    if not zarr_path.is_dir():
        raise FileNotFoundError(f"existing cube required: {zarr_path}")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"existing manifest required: {manifest_path}")

    with xr.open_zarr(zarr_path, chunks=None, mask_and_scale=False) as dataset:
        if HAND_BAND_NAME in dataset.data_vars:
            raise ValueError("hand_m is already in the cube; refusing to rewrite bands")
        grid = grid_from_dataset(dataset)
        y_vals = np.asarray(dataset.y.values)
        x_vals = np.asarray(dataset.x.values)
        cube_attrs = dict(dataset.attrs)
        chunk_shape = (256, 256)
        for name in dataset.data_vars:
            chunks = dataset[name].encoding.get("chunks")
            if chunks:
                chunk_shape = tuple(int(size) for size in chunks)
                break

    print(
        f"HAND grid read from cube: crs={grid.crs} {grid.width}x{grid.height} "
        f"scale_x={grid.scale_x} scale_y={grid.scale_y} "
        f"translate=({grid.translate_x}, {grid.translate_y})"
    )
    if not init_gee_session():
        raise RuntimeError("Earth Engine did not initialize; hand_m was not written")
    arr = fetch_merit_hand(grid)
    if arr is None:
        raise RuntimeError("MERIT Hydro HAND sample failed; cube left unchanged")
    finite = int(np.count_nonzero(np.isfinite(arr)))
    total = int(arr.size)
    if finite == 0 or total == 0:
        raise RuntimeError("MERIT Hydro HAND sample has no finite pixels; cube left unchanged")

    write_hand_variable(zarr_path, arr, y_vals, x_vals, chunk_shape, cube_attrs)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record, provenance = hand_manifest_entry(arr, grid)
    manifest.setdefault("bands", {})[HAND_BAND_NAME] = record
    manifest.setdefault("nisar_granule_provenance", {})[HAND_BAND_NAME] = provenance
    text = json.dumps(manifest, indent=2)
    if not text.endswith("\n"):
        text += "\n"
    manifest_path.write_text(text, encoding="utf-8")
    print(f"hand_m finite pixels: {finite} of {total} (ratio {finite / total}) *(measured)*")
    print(f"manifest finite_pixel_ratio: {record['finite_pixel_ratio']}")
    print(f"appended {HAND_BAND_NAME} to {zarr_path}")
    return manifest_path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--aoi",
        default="eje_cafetero",
        choices=[
            "eje_cafetero",
            "aburra",
            "mojana",
            "all",
            "1_aburra_medellin_bello",
            "2_eje_cafetero_quake",
            "3_la_mojana_caregato",
        ],
        help="Target AOI to prewarm and build cache for",
    )
    ap.add_argument("--chirps-start", default=None, help="CHIRPS start date (YYYY-MM-DD)")
    ap.add_argument("--chirps-end", default=None, help="CHIRPS end date (YYYY-MM-DD)")
    ap.add_argument(
        "--only-band",
        default=None,
        choices=[HAND_BAND_NAME],
        help="Append this one band onto the existing cube grid. Does not rebuild other bands.",
    )
    args = ap.parse_args()

    if args.only_band:
        if args.aoi == "all":
            raise SystemExit("--only-band cannot be combined with --aoi all")
        append_merit_hand_band(args.aoi)
        return

    if args.aoi == "all":
        # Build in agreed priority order: Eje Cafetero first, then Aburrá, then La Mojana
        for target in ["eje_cafetero", "aburra", "mojana"]:
            build_cache_for_aoi(target, args.chirps_start, args.chirps_end)
    else:
        build_cache_for_aoi(args.aoi, args.chirps_start, args.chirps_end)


if __name__ == "__main__":
    main()
