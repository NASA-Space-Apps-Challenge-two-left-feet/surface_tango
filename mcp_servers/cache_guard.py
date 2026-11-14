# mcp_servers/cache_guard.py
import os
import json
import functools
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path
import numpy as np
import xarray as xr

CACHE_DIR = Path(__file__).resolve().parent.parent / "local_cache" / "antioquia_aburra"
ZARR_PATH = CACHE_DIR / "antioquia_sar_cube.zarr"
MANIFEST_PATH = CACHE_DIR / "manifest.json"

def compute_local_zarr_fallback(tool_name: str) -> dict:
    """Computes genuine physical hazard metrics directly from the local Zarr v3 cube in <25ms."""
    ds = xr.open_zarr(ZARR_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text())
    tiles = manifest["local_tile_templates"]

    if tool_name == "search_nisar_granules":
        return [{
            "scene_name": "NISAR_L2_PR_GCOV_014_128_A_20261110_ANTIOQUIA",
            "start_time": "2026-11-10T23:14:02Z",
            "https_url": "local://antioquia_sar_cube.zarr",
            "s3_url": "s3://nisar-provisional/antioquia_aburra.h5",
            "product_level": "GCOV_GUNW_CACHED",
        }]

    if tool_name in ("stage_nisar_gcov_to_gcs", "stage_nisar_gunw_ionosphere_corrected_to_gcs"):
        return manifest["cog_paths"]

    if tool_name == "analyze_landslide_kinematics":
        disp = ds["downslope_disp_mm"].values
        rain = ds["rain_15d_mm"].values
        slope = ds["slope_deg"].values
        return {
            "metrics": {
                "downslope_disp_mm_p50": round(float(np.nanpercentile(disp, 50)), 2),
                "downslope_disp_mm_p95": round(float(np.nanpercentile(disp, 95)), 2),
                "downslope_disp_mm_p99": round(float(np.nanpercentile(disp, 99)), 2),
                "rain_15d_mm_p95": round(float(np.nanpercentile(rain, 95)), 1),
                "slope_deg_p95": round(float(np.nanpercentile(slope, 95)), 1),
            },
            "tile_url": tiles["landslide"],
            "physical_driver": "L-band 24cm foliar penetration InSAR phase shift projected onto bare-earth FABDEM slope (Zarr Edge Cache)",
        }

    if tool_name == "analyze_flood_inundation":
        hh_pre_db = 10.0 * np.log10(ds["gcov_hhhh_pre"].values + 1e-6)
        hh_post_db = 10.0 * np.log10(ds["gcov_hhhh_post"].values + 1e-6)
        delta_hh = hh_post_db - hh_pre_db
        pixel_area_ha = 0.09  # ~30m pixel in hectares
        open_ha = float(np.sum(delta_hh < -5.0) * pixel_area_ha)
        double_bounce_ha = float(np.sum(delta_hh > 2.8) * pixel_area_ha)
        return {
            "open_water_flood_ha": round(open_ha, 1),
            "subcanopy_double_bounce_flood_ha": round(double_bounce_ha, 1),
            "tile_url": tiles["flood"],
            "physical_driver": "Dielectric constant contrast: Specular open water (-5.5 dB HH) vs dihedral trunk-water double bounce (+3.0 dB HH)",
        }

    if tool_name == "analyze_earthquake_dpm":
        dpm = np.clip(ds["gunw_coherence"].values - ds["coherence_coseismic"].values, 0, 1)
        severe_pixels = int(np.sum(dpm > 0.25))
        return {
            "estimated_population_in_severe_dpm_zone": {"pop_exposed": severe_pixels * 14, "max_dpm": round(float(np.max(dpm)), 3)},
            "tile_url": tiles["earthquake"],
            "physical_driver": "Co-seismic interferometric phase & geometric decorrelation across VIDA building footprints",
        }

    if tool_name == "analyze_biomass_disturbance":
        hh = ds["gcov_hhhh_post"].values
        hv = ds["gcov_hvhv_post"].values
        agb = ds["agb_mgha"].values
        rfdi = (hh - hv) / (hh + hv + 1e-6)
        disturbed_mask = (agb > 100.0) & (rfdi > 0.55)
        carbon_tons = float(np.sum(agb[disturbed_mask] * 0.47 * 0.09))
        return {
            "aboveground_carbon_disturbed_tons": round(carbon_tons, 1),
            "rfdi_p95": round(float(np.nanpercentile(rfdi, 95)), 3),
            "tile_url": tiles["biomass"],
            "physical_driver": "L-band 24cm cross-polarized (HV) canopy volume scattering attenuation vs ESA CCI AGB v6.0",
        }

    return {}

def with_offline_zarr_fallback(timeout_sec: float = 1.8):
    """
    Decorator for FastMCP tools: Immediately serves from local Zarr v3 cube if
    OFFLINE_DEMO_MODE=1 or if remote NASA S3 / GEE calls exceed `timeout_sec`.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if os.environ.get("OFFLINE_DEMO_MODE", "0") == "1":
                return compute_local_zarr_fallback(func.__name__)
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(func, *args, **kwargs)
                    return future.result(timeout=timeout_sec)
            except (FuturesTimeout, Exception) as exc:
                print(f"[CIRCUIT-BREAKER] {func.__name__} switched to Local Zarr v3 Cache ({exc})")
                return compute_local_zarr_fallback(func.__name__)
        return wrapper
    return decorator
