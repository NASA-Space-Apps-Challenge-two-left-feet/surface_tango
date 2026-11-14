# scripts/prewarm_antioquia_cache.py
import io
import json
import math
import os
from pathlib import Path
from typing import Any

import earthaccess
import ee
import numpy as np
import rioxarray
import xarray as xr
from rasterio.enums import Resampling
from rasterio.transform import from_bounds

from gee_math.ee_session import init_ee

CACHE_DIR = Path(__file__).resolve().parent.parent / "local_cache" / "antioquia_aburra"
COG_DIR = CACHE_DIR / "cogs"
ZARR_PATH = CACHE_DIR / "antioquia_sar_cube.zarr"
MANIFEST_PATH = CACHE_DIR / "manifest.json"
DISCOVERED_CATALOG_PATH = CACHE_DIR / "nisar_colombia_granules_2026.json"

# Bounding Box: Valle de Aburra (Medellin, Bello, Copacabana, Oriental/Occidental Slopes)
BBOX = [-75.63, 6.22, -75.50, 6.38]  # [min_lon, min_lat, max_lon, max_lat]
WIDTH, HEIGHT = 512, 512
DST_TRANSFORM = from_bounds(*BBOX, WIDTH, HEIGHT)
DST_CRS = "EPSG:4326"


def init_gee() -> bool:
    try:
        init_ee()
        return True
    except Exception as exc:
        print(f"[WARN] GEE unavailable ({type(exc).__name__}); GEE layers recorded as missing.")
        return False


def init_earthaccess() -> bool:
    try:
        earthaccess.login(strategy="netrc")
        # Configure GDAL environment cookies/headers for NASA Earthdata /vsicurl/ streaming
        os.environ.setdefault("GDAL_HTTP_COOKIEFILE", "/tmp/earthdata_cookies.txt")
        os.environ.setdefault("GDAL_HTTP_COOKIEJAR", "/tmp/earthdata_cookies.txt")
        os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".h5,.tif,.tiff")
        os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
        return True
    except Exception as exc:
        print(f"[WARN] NASA Earthdata .netrc login unavailable ({exc}).")
        return False


def select_best_nisar_pairs_from_catalog(
    aoi_key: str = "1_aburra_medellin_bello",
) -> dict[str, dict[str, Any] | None]:
    """
    Reads nisar_colombia_granules_2026.json and selects the deepest co-registered
    Track/Frame stack for both GCOV (backscatter covariance) and GUNW (unwrapped phase).
    Returns {'gcov_post', 'gcov_pre', 'gunw_post', 'gunw_pre'}.
    """
    selected: dict[str, dict[str, Any] | None] = {
        "gcov_post": None,
        "gcov_pre": None,
        "gunw_post": None,
        "gunw_pre": None,
    }

    if not DISCOVERED_CATALOG_PATH.exists():
        print(f"[INFO] {DISCOVERED_CATALOG_PATH.name} not found. Running discovery script first...")
        try:
            from scripts.discover_nisar_colombia import search_nisar_across_colombia

            search_nisar_across_colombia()
        except Exception as exc:
            print(f"[WARN] Auto-discovery skipped ({exc}).")
            return selected

    if not DISCOVERED_CATALOG_PATH.exists():
        return selected

    catalog = json.loads(DISCOVERED_CATALOG_PATH.read_text())
    stacks = catalog.get(aoi_key, {}).get("track_frame_stacks", {})

    # Sort stacks by number of scenes descending so we pick a Track/Frame with repeat-pass pairs
    gcov_stacks = [(k, v) for k, v in stacks.items() if k.startswith("GCOV_") and len(v) >= 1]
    gunw_stacks = [(k, v) for k, v in stacks.items() if k.startswith("GUNW_") and len(v) >= 1]
    gcov_stacks.sort(key=lambda item: len(item[1]), reverse=True)
    gunw_stacks.sort(key=lambda item: len(item[1]), reverse=True)

    if gcov_stacks:
        stack_id, scenes = gcov_stacks[0]
        selected["gcov_post"] = scenes[0]
        selected["gcov_pre"] = scenes[1] if len(scenes) > 1 else scenes[0]
        print(
            f"📡 Selected GCOV Stack [{stack_id}]: "
            f"Post={selected['gcov_post']['scene_name']} | Pre={selected['gcov_pre']['scene_name']}"
        )

    if gunw_stacks:
        stack_id, scenes = gunw_stacks[0]
        selected["gunw_post"] = scenes[0]
        selected["gunw_pre"] = scenes[1] if len(scenes) > 1 else scenes[0]
        print(
            f"📡 Selected GUNW Stack [{stack_id}]: "
            f"Post={selected['gunw_post']['scene_name']} | Pre={selected['gunw_pre']['scene_name']}"
        )

    return selected


def stream_and_warp_nisar_h5_subdataset(
    granule_meta: dict[str, Any] | None,
    h5_subdataset_path: str,
    resampling: Resampling = Resampling.bilinear,
) -> tuple[np.ndarray | None, str | None]:
    """
    Streams ONLY the bounding box byte-range from a remote NASA Earthdata NISAR .h5 URL
    via GDAL /vsicurl/, reprojects from native UTM (e.g., EPSG:32618) to the exact
    512x512 EPSG:4326 Aburra Valley grid, and returns (float32_ndarray, scene_name).
    """
    if not granule_meta or not granule_meta.get("https_url"):
        return None, None

    https_url = granule_meta["https_url"]
    scene_name = granule_meta.get("scene_name", "NISAR_SCENE")
    vsi_uri = f'HDF5:"/vsicurl/{https_url}":{h5_subdataset_path}'

    try:
        print(f"   ↳ Slicing remote HDF5: {scene_name} [{h5_subdataset_path}] ...")
        da = rioxarray.open_rasterio(vsi_uri, masked=True, chunks="auto")
        if da.ndim == 3:
            da = da.isel(band=0)

        # Reproject and clip from native UTM (EPSG:32618) to the 512x512 EPSG:4326 grid
        da_warped = da.rio.reproject(
            dst_crs=DST_CRS,
            shape=(HEIGHT, WIDTH),
            transform=DST_TRANSFORM,
            resampling=resampling,
        )
        arr = da_warped.values.astype(np.float32)
        arr[~np.isfinite(arr)] = np.nan  # missing stays missing (no zero-fill)

        # Verify non-empty swath intersection over AOI
        if np.count_nonzero(np.isfinite(arr)) < (WIDTH * HEIGHT * 0.05):
            print(
                f"   [WARN] Swath coverage <5% over AOI for {scene_name}; band recorded as missing."
            )
            return None, None

        return arr, scene_name
    except Exception as exc:
        print(
            f"   [WARN] Remote HDF5 slice failed for {h5_subdataset_path} ({exc}); "
            "band recorded as missing."
        )
        return None, None


def fetch_gee_layer_as_numpy(image: ee.Image, band_name: str) -> np.ndarray:
    """Uses GEE High-Volume computePixels to pull a 512x512 float32 array in <1s."""
    region = ee.Geometry.Rectangle(BBOX)
    params = {
        "expression": image.clip(region).unmask(0),
        "fileFormat": "NPY",
        "grid": {
            "dimensions": {"width": WIDTH, "height": HEIGHT},
            "affineTransform": {
                "scaleX": (BBOX[2] - BBOX[0]) / WIDTH,
                "shearX": 0,
                "translateX": BBOX[0],
                "shearY": 0,
                "scaleY": -(BBOX[3] - BBOX[1]) / HEIGHT,
                "translateY": BBOX[3],
            },
            "crsCode": DST_CRS,
        },
    }
    raw_bytes = ee.data.computePixels(params)
    structured = np.load(io.BytesIO(raw_bytes))
    return structured[band_name].astype(np.float32)


def save_array_as_cog(arr: np.ndarray, filename: str) -> Path:
    """Writes a 2D float32 numpy array as a Cloud-Optimized GeoTIFF aligned to BBOX."""
    COG_DIR.mkdir(parents=True, exist_ok=True)
    out_path = COG_DIR / filename

    da = xr.DataArray(
        arr.astype(np.float32),
        dims=("y", "x"),
        coords={
            "y": np.linspace(BBOX[3], BBOX[1], HEIGHT),
            "x": np.linspace(BBOX[0], BBOX[2], WIDTH),
        },
    )
    da.rio.write_crs(DST_CRS, inplace=True)
    da.rio.write_transform(DST_TRANSFORM, inplace=True)
    da.rio.to_raster(
        out_path,
        driver="COG",
        compress="DEFLATE",
        predictor=2,
        overview_resampling="AVERAGE",
    )
    return out_path


def build_antioquia_offline_cube():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    gee_online = init_gee()
    earthdata_online = init_earthaccess()

    y_coords = np.linspace(BBOX[3], BBOX[1], HEIGHT)
    x_coords = np.linspace(BBOX[0], BBOX[2], WIDTH)
    provenance: dict[str, str] = {}

    def missing() -> np.ndarray:
        # No synthetic fallback: a band we could not fetch is all-NaN and marked "missing".
        return np.full((HEIGHT, WIDTH), np.nan, dtype=np.float32)

    def take(arr, name, src):
        if arr is None:
            provenance[name] = "missing"
            return missing()
        provenance[name] = src
        return arr

    # --- STEP 1: Fetch Context Layers from Google Earth Engine (FABDEM, CHIRPS, ESA CCI AGB) ---
    slope_deg = rain_15d_mm = agb_mgha = None
    if gee_online:
        print("1. Pulling bare-earth FABDEM slope, CHIRPS 15d rain & ESA CCI AGB v6.0 via GEE...")
        aoi = ee.Geometry.Rectangle(BBOX)
        fabdem = (
            ee.ImageCollection("projects/sat-io/open-datasets/FABDEM").filterBounds(aoi).mosaic()
        )
        slope_deg = fetch_gee_layer_as_numpy(ee.Terrain.slope(fabdem).rename("slope"), "slope")

        chirps = (
            ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
            .filterDate("2026-10-29", "2026-11-13")
            .sum()
            .rename("rain")
        )
        rain_15d_mm = fetch_gee_layer_as_numpy(chirps, "rain")

        esa_agb = (
            ee.ImageCollection("projects/sat-io/open-datasets/ESA/ESA_CCI_AGB")
            .sort("system:time_start", False)
            .first()
            .select([0], ["agb"])
        )
        agb_mgha = fetch_gee_layer_as_numpy(esa_agb, "agb")
    else:
        print("1. GEE offline: FABDEM slope, CHIRPS and ESA CCI AGB recorded as missing.")
    slope_deg = take(slope_deg, "fabdem_slope", "GEE projects/sat-io/open-datasets/FABDEM")
    rain_15d_mm = take(
        rain_15d_mm, "chirps_15d", "GEE UCSB-CHG/CHIRPS/DAILY 2026-10-29..2026-11-13"
    )
    agb_mgha = take(agb_mgha, "esa_agb", "GEE projects/sat-io/open-datasets/ESA/ESA_CCI_AGB")

    # --- STEP 2: slice real NISAR GCOV and GUNW granules (nisar_colombia_granules_2026.json) ---
    print("2. Inspecting discovered NISAR granules in nisar_colombia_granules_2026.json...")
    pairs = (
        select_best_nisar_pairs_from_catalog("1_aburra_medellin_bello") if earthdata_online else {}
    )

    # 2A. Slice NISAR L2 GCOV (HHHH & HVHV Post-Event and Pre-Event)
    gcov_base = "/science/LSAR/GCOV/grids/frequencyA"
    a, src_id = stream_and_warp_nisar_h5_subdataset(pairs.get("gcov_post"), f"{gcov_base}/HHHH")
    hhhh_post = take(a, "gcov_hhhh_post", src_id)
    a, src_id2 = stream_and_warp_nisar_h5_subdataset(pairs.get("gcov_post"), f"{gcov_base}/HVHV")
    hvhv_post = take(a, "gcov_hvhv_post", src_id2)
    a, pre_id = stream_and_warp_nisar_h5_subdataset(pairs.get("gcov_pre"), f"{gcov_base}/HHHH")
    hhhh_pre = take(a, "gcov_hhhh_pre", pre_id)
    a, pre_id2 = stream_and_warp_nisar_h5_subdataset(pairs.get("gcov_pre"), f"{gcov_base}/HVHV")
    hvhv_pre = take(a, "gcov_hvhv_pre", pre_id2)

    # 2B. Slice NISAR L2 GUNW: unwrappedPhase, ionosphericPhaseScreen, coherenceMagnitude,
    # connectedComponents
    gunw_base = "/science/LSAR/GUNW/grids/frequencyA"
    unw_arr, gunw_id = stream_and_warp_nisar_h5_subdataset(
        pairs.get("gunw_post"), f"{gunw_base}/unwrappedPhase"
    )
    iono_arr, iono_id = stream_and_warp_nisar_h5_subdataset(
        pairs.get("gunw_post"), f"{gunw_base}/ionosphericPhaseScreen"
    )
    coh_post, coh_id = stream_and_warp_nisar_h5_subdataset(
        pairs.get("gunw_post"), f"{gunw_base}/coherenceMagnitude"
    )
    conn_comp, cc_id = stream_and_warp_nisar_h5_subdataset(
        pairs.get("gunw_post"), f"{gunw_base}/connectedComponents", resampling=Resampling.nearest
    )
    coh_pre, gunw_pre_id = stream_and_warp_nisar_h5_subdataset(
        pairs.get("gunw_pre"), f"{gunw_base}/coherenceMagnitude"
    )

    iono_screen = take(iono_arr, "gunw_ionosphere", iono_id)
    if unw_arr is not None and iono_arr is not None:
        gunw_phase_corr = (unw_arr - iono_arr).astype(np.float32)
        provenance["gunw_phase_corr"] = f"{gunw_id} (ionosphere screen applied)"
        # TODO(hazard modeling, design doc Hazard 1): troposphere fit, LOS->downslope
        # projection, noise-floor test.
        downslope_disp_mm = (gunw_phase_corr * (-240.0 / (4.0 * math.pi))).astype(np.float32)
        provenance["los_disp_mm"] = provenance["gunw_phase_corr"]
    else:
        # Missing phase or missing ionosphere screen: no velocity claimed (gate table).
        gunw_phase_corr = take(None, "gunw_phase_corr", None)
        downslope_disp_mm = take(None, "los_disp_mm", None)

    conn_comp = take(conn_comp, "gunw_conncomp", cc_id)
    coherence_coseismic = take(coh_post, "coherence_coseismic", coh_id)
    gunw_coherence = take(coh_pre, "gunw_coherence_pre", gunw_pre_id)

    # --- STEP 3: Save All Reprojected Arrays as Local Cloud-Optimized GeoTIFFs ---
    print("3. Writing aligned 512x512 Cloud-Optimized GeoTIFFs (COGs)...")
    cog_files = {
        "gunw_unw_gcs": save_array_as_cog(gunw_phase_corr, "nisar_gunw_phase_corr.tif"),
        "gunw_iono_gcs": save_array_as_cog(iono_screen, "nisar_gunw_iono.tif"),
        "gunw_coh_gcs": save_array_as_cog(gunw_coherence, "nisar_gunw_coherence.tif"),
        "gunw_conncomp_gcs": save_array_as_cog(conn_comp, "nisar_gunw_conncomp.tif"),
        "coherence_coseismic_gcs": save_array_as_cog(
            coherence_coseismic, "nisar_gunw_coh_coseismic.tif"
        ),
        "gcov_hhhh_pre_gcs": save_array_as_cog(hhhh_pre, "nisar_gcov_hhhh_pre.tif"),
        "gcov_hvhv_pre_gcs": save_array_as_cog(hvhv_pre, "nisar_gcov_hvhv_pre.tif"),
        "gcov_hhhh_post_gcs": save_array_as_cog(hhhh_post, "nisar_gcov_hhhh_post.tif"),
        "gcov_hvhv_post_gcs": save_array_as_cog(hvhv_post, "nisar_gcov_hvhv_post.tif"),
        "fabdem_slope": save_array_as_cog(slope_deg, "gee_fabdem_slope.tif"),
        "chirps_15d": save_array_as_cog(rain_15d_mm, "gee_chirps_15d.tif"),
        "esa_agb": save_array_as_cog(agb_mgha, "gee_esa_cci_agb.tif"),
    }

    # --- STEP 4: Compile Unified Zarr v3 Multi-Hazard Tensor ---
    print("4. Compiling consolidated Zarr v3 Multi-Hazard Data Cube...")
    ds = xr.Dataset(
        {
            "gunw_phase_corr": (("y", "x"), gunw_phase_corr),
            "gunw_coherence": (("y", "x"), gunw_coherence),
            "gunw_conncomp": (("y", "x"), conn_comp),
            "coherence_coseismic": (("y", "x"), coherence_coseismic),
            "los_disp_mm": (("y", "x"), downslope_disp_mm),
            "gcov_hhhh_pre": (("y", "x"), hhhh_pre),
            "gcov_hvhv_pre": (("y", "x"), hvhv_pre),
            "gcov_hhhh_post": (("y", "x"), hhhh_post),
            "gcov_hvhv_post": (("y", "x"), hvhv_post),
            "slope_deg": (("y", "x"), slope_deg),
            "rain_15d_mm": (("y", "x"), rain_15d_mm),
            "agb_mgha": (("y", "x"), agb_mgha),
        },
        coords={"y": y_coords, "x": x_coords},
        attrs={"nisar_provenance": json.dumps(provenance)},
    ).chunk({"y": 256, "x": 256})

    ds.to_zarr(ZARR_PATH, mode="w")

    # --- STEP 5: Write Manifest with Exact Granule Provenance ---
    manifest = {
        "region": "Valle de Aburrá - Bello & Medellín Northern Slopes",
        "bbox": BBOX,
        "zarr_cube_path": str(ZARR_PATH),
        "nisar_granule_provenance": provenance,
        "cog_paths": {k: str(v) for k, v in cog_files.items()},
        "local_tile_templates": {
            "landslide": "http://localhost:8000/api/local-tiles/landslide/{z}/{x}/{y}.png",
            "flood": "http://localhost:8000/api/local-tiles/flood/{z}/{x}/{y}.png",
            "earthquake": "http://localhost:8000/api/local-tiles/earthquake/{z}/{x}/{y}.png",
            "biomass": "http://localhost:8000/api/local-tiles/biomass/{z}/{x}/{y}.png",
            "optical_s2": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
            "cband_s1": "http://localhost:8000/api/local-tiles/cband/{z}/{x}/{y}.png",
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(f"✅ NISAR-Sliced Zarr v3 Cube & COGs ready at: {CACHE_DIR}")
    print(f"📋 Granule Provenance: {json.dumps(provenance, indent=2)}")


if __name__ == "__main__":
    build_antioquia_offline_cube()
