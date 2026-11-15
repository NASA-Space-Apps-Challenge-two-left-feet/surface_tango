# mcp_servers/gee_fusion_mcp.py
from typing import Any

import ee
from fastmcp import FastMCP

from gee_math.biomass_polarimetric_math import compute_biomass_and_carbon_flux
from gee_math.earthquake_dpm_math import compute_earthquake_dpm_and_rupture
from gee_math.ee_session import init_ee
from gee_math.flood_polarimetric_math import compute_flood_scattering_decomposition
from gee_math.landslide_insar_math import compute_landslide_insar_kinematics
from mcp_servers.cache_guard import with_offline_zarr_fallback

mcp = FastMCP(name="gee-hazard-fusion-engine")

init_ee()  # ADC identity + GCP_PROJECT_ID (gee_math/ee_session.py)


def _extract_zonal_stats_and_hotspot(
    metric_stack: ee.Image,
    primary_band: str,
    hotspot_threshold: float,
    aoi: ee.Geometry,
    scale: int = 30,
) -> dict[str, Any]:
    """
    Executes a single-pass GEE High-Volume reduction to compute [p50, p95, p99] percentiles
    across all bands in `metric_stack` AND extracts the [lon, lat] coordinates of the
    peak anomaly where `primary_band >= hotspot_threshold`.
    """
    # Attach pixel coordinates masked to the severe anomaly zone
    hotspot_mask = metric_stack.select(primary_band).gte(hotspot_threshold)
    lon_lat_hotspots = (
        ee.Image.pixelLonLat().updateMask(hotspot_mask).rename(["hotspot_lon", "hotspot_lat"])
    )

    # Combine percentiles for physical metrics + mean for hotspot centroid in one pass
    pct_stats = metric_stack.reduceRegion(
        reducer=ee.Reducer.percentile([50, 95, 99]),
        geometry=aoi,
        scale=scale,
        maxPixels=1e8,
        bestEffort=True,
    )

    coord_stats = lon_lat_hotspots.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=aoi,
        scale=scale,
        maxPixels=1e8,
        bestEffort=True,
    )

    # Evaluate both dictionaries in a singleee.List(...).getInfo() round-trip
    combined_info = ee.List([pct_stats, coord_stats]).getInfo()
    metrics_dict = combined_info[0] or {}
    coords_dict = combined_info[1] or {}

    # Fallback to AOI center if no pixels exceed threshold
    lon = coords_dict.get("hotspot_lon")
    lat = coords_dict.get("hotspot_lat")
    if lon is None or lat is None:
        center = aoi.centroid(10).coordinates().getInfo()
        lon, lat = center[0], center[1]

    # Clean up None values and round floats for clean LLM consumption
    clean_metrics = {k: round(float(v), 3) for k, v in metrics_dict.items() if v is not None}
    return {
        "zonal_percentiles": clean_metrics,
        "hotspot_coordinates": [round(float(lon), 5), round(float(lat), 5)],
    }


# Continuation of mcp_servers/gee_fusion_mcp.py


@mcp.tool
@with_offline_zarr_fallback(timeout_sec=1.8)
def analyze_landslide_kinematics(
    gunw_unw_gcs: str,
    gunw_iono_gcs: str,
    gunw_coh_gcs: str,
    gunw_conncomp_gcs: str,
    bbox: list[float],
    rain_start_date: str,
    rain_end_date: str,
    temporal_baseline_days: float,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Executes Module 1 (compute_landslide_insar_kinematics):
    Removes equatorial ionospheric & stratified tropospheric phase delays, projects L-band LOS
    displacement onto the 3D bare-earth FABDEM steepest downslope vector, and couples with 15-day CHIRPS rain.
    """
    if params is None:
        return {
            "status": "error",
            "reason": "landslide params not in config/preregistered.yaml yet",
        }
    aoi = ee.Geometry.Rectangle(bbox)

    # 1. Build the server-side GEE mathematical expression graph
    landslide_stack = compute_landslide_insar_kinematics(
        gunw_unw_gcs=gunw_unw_gcs,
        gunw_iono_gcs=gunw_iono_gcs,
        gunw_coh_gcs=gunw_coh_gcs,
        gunw_conncomp_gcs=gunw_conncomp_gcs,
        aoi=aoi,
        rain_start_date=rain_start_date,
        rain_end_date=rain_end_date,
        temporal_baseline_days=temporal_baseline_days,
        params=params,
    )

    # 2. Render Primary Hazard Tile: Downslope Velocity (mm/yr) masked to active creep (>10 mm/yr)
    vel_viz = (
        landslide_stack.select("v_downslope_mm_yr")
        .updateMask(landslide_stack.select("v_downslope_mm_yr").gte(10.0))
        .getMapId(
            {
                "min": 10.0,
                "max": 120.0,
                "palette": ["00ff87", "facc15", "f97316", "dc2626", "7f1d1d"],
            }
        )
    )

    # 3. Render Multi-Band Diagnostic RGB Composite Tile:
    # Red = Downslope Velocity, Green = 15-day CHIRPS Rainfall, Blue = FABDEM Slope
    rgb_diag_map = landslide_stack.select(["v_downslope_mm_yr", "rain_15d_mm", "slope"]).getMapId(
        {"min": [0, 50, 15], "max": [100, 220, 45]}
    )

    # 4. Single-pass Zonal Percentiles [p50, p95, p99] + Peak Hotspot [lon, lat]
    summary = _extract_zonal_stats_and_hotspot(
        metric_stack=landslide_stack.select(
            [
                "d_los_mm",
                "v_downslope_mm_yr",
                "slope",
                "rain_15d_mm",
                "coherence",
                "landslide_hazard_index",
            ]
        ),
        primary_band="landslide_hazard_index",
        hotspot_threshold=0.65,
        aoi=aoi,
        scale=30,
    )

    p99_vel = summary["zonal_percentiles"].get("v_downslope_mm_yr_p99", 0.0)
    alert = (
        "RED"
        if p99_vel > 80.0
        else "ORANGE"
        if p99_vel > 35.0
        else "YELLOW"
        if p99_vel > 15.0
        else "GREEN"
    )

    return {
        "domain": "landslide",
        "alert_level": alert,
        "key_quantitative_metrics": summary["zonal_percentiles"],
        "hotspot_coordinates": summary["hotspot_coordinates"],
        "gee_xyz_tile_url": vel_viz["tile_fetcher"].url_format,
        "diagnostic_rgb_tile_url": rgb_diag_map["tile_fetcher"].url_format,
        "physical_radar_driver": (
            "NISAR L-band (24.0 cm) penetrates tropical hillside canopy to maintain phase coherence "
            "(gamma >= 0.35), projecting ionosphere/troposphere-corrected LOS phase onto the 3D "
            "bare-earth FABDEM downslope unit vector coupled with 15-day CHIRPS pore-pressure rainfall."
        ),
    }


@mcp.tool
@with_offline_zarr_fallback(timeout_sec=1.8)
def analyze_flood_inundation(
    gcov_hhhh_post_gcs: str,
    gcov_hvhv_post_gcs: str,
    bbox: list[float],
    post_date: str,
    has_baseline: bool,
    gcov_hhhh_pre_gcs: str | None = None,
    gcov_hvhv_pre_gcs: str | None = None,
    s1_post_start: str | None = None,
    s1_post_end: str | None = None,
) -> dict[str, Any]:
    """
    Executes Module 2 (compute_flood_scattering_decomposition):
    Decomposes NISAR L2 GCOV polarimetric covariance into Specular Open-Water Flooding (Class 1)
    and Sub-Canopy Dihedral Double-Bounce Flooding (Class 2), returning flooded hectares and percentiles.
    """
    from gee_math.flood_polarimetric_math import load_params

    params = load_params("flood")
    aoi = ee.Geometry.Rectangle(bbox)

    # 1. Build the server-side GEE polarimetric decomposition graph
    flood_stack = compute_flood_scattering_decomposition(
        gcov_hhhh_pre_gcs=gcov_hhhh_pre_gcs,
        gcov_hvhv_pre_gcs=gcov_hvhv_pre_gcs,
        gcov_hhhh_post_gcs=gcov_hhhh_post_gcs,
        gcov_hvhv_post_gcs=gcov_hvhv_post_gcs,
        aoi=aoi,
        post_date=post_date,
        has_baseline=has_baseline,
        s1_post_start=s1_post_start,
        s1_post_end=s1_post_end,
        params=params,
    )

    # 2. Render Categorical Flood Regime Tile (Cyan = Specular Open Water, Magenta = Sub-Canopy Double-Bounce)
    flood_class = flood_stack.select("flood_regime_class")
    class_viz = flood_class.updateMask(flood_class.gt(0)).getMapId(
        {"min": 1, "max": 2, "palette": ["00b4d8", "ff007f"]}
    )

    # 3. Render Polarimetric Pauli/Freeman False-Color RGB Tile:
    # Red = HH Post (dB, Double-Bounce), Green = HV Post (dB, Canopy Volume), Blue = Delta HH (dB)
    pol_rgb_map = (
        flood_stack.select(["hh_post_db", "hv_post_db", "delta_hh_db"]).getMapId(
            {"min": [-18, -24, -8], "max": [-2, -8, 6]}
        )
        if has_baseline
        else None
    )

    # 4. Compute exact inundated area (hectares) + radiometric percentiles in one GEE pass
    pixel_ha = ee.Image.pixelArea().divide(1e4)
    area_bands = ee.Image.cat(
        [
            flood_stack.select("specular_open_flood")
            .multiply(pixel_ha)
            .rename("open_water_flood_ha"),
            flood_stack.select("subcanopy_double_bounce_flood")
            .multiply(pixel_ha)
            .rename("subcanopy_double_bounce_ha"),
        ]
    )

    area_totals = area_bands.reduceRegion(
        reducer=ee.Reducer.sum(), geometry=aoi, scale=20, maxPixels=1e8, bestEffort=True
    )
    summary = _extract_zonal_stats_and_hotspot(
        metric_stack=flood_stack.select(
            ["hh_post_db", "hv_post_db", "flood_regime_class"]
            + (["delta_hh_db", "delta_hv_hh_db"] if has_baseline else [])
        ),
        primary_band="flood_regime_class",
        hotspot_threshold=0.60,
        aoi=aoi,
        scale=20,
    )
    area_dict = area_totals.getInfo() or {}

    open_area = area_dict.get("open_water_flood_ha")
    subcanopy_area = area_dict.get("subcanopy_double_bounce_ha") if has_baseline else None
    open_ha = round(float(open_area), 2) if open_area is not None else None
    subcanopy_ha = round(float(subcanopy_area), 2) if subcanopy_area is not None else None

    metrics = summary["zonal_percentiles"]
    metrics["subcanopy_double_bounce_flood_ha"] = subcanopy_ha
    class2_reason = None
    if not has_baseline:
        class2_reason = "no acceptable dry baseline"
        metrics["water_extent_ha"] = open_ha
        metrics["water_extent_label"] = f"water extent on date {post_date}"
        alert = "not computed: no acceptable dry baseline"
    else:
        metrics["open_water_flood_ha"] = open_ha
        total_ha = (
            round(open_ha + subcanopy_ha, 2)
            if open_ha is not None and subcanopy_ha is not None
            else None
        )
        metrics["total_inundated_ha"] = total_ha
        alert = (
            "not computed: missing inundated area"
            if total_ha is None
            else "RED"
            if total_ha > 150.0
            else "ORANGE"
            if total_ha > 50.0
            else "YELLOW"
            if total_ha > 10.0
            else "GREEN"
        )

    return {
        "domain": "flood",
        "alert_level": alert,
        "class2_reason": class2_reason,
        "key_quantitative_metrics": metrics,
        "hotspot_coordinates": summary["hotspot_coordinates"],
        "gee_xyz_tile_url": class_viz["tile_fetcher"].url_format,
        "diagnostic_rgb_tile_url": pol_rgb_map["tile_fetcher"].url_format if pol_rgb_map else None,
        "physical_radar_driver": (
            "High dielectric constant (epsilon_r ~ 80) causes specular mirror reflection over open water "
            "(-5.5 dB drop in L-band HH & C-band VV) while water beneath flooded riparian trees creates "
            "a dihedral trunk-water corner reflector (+3.0 dB L-band HH surge & >55% double-bounce power)."
        ),
    }


@mcp.tool
@with_offline_zarr_fallback(timeout_sec=1.8)
def analyze_earthquake_dpm(
    coh_pre_gcs: str,
    coh_coseismic_gcs: str,
    goff_range_gcs: str,
    goff_azimuth_gcs: str,
    bbox: list[float],
) -> dict[str, Any]:
    """
    Executes Module 3 (compute_earthquake_dpm_and_rupture):
    Computes Z-score normalized ARIA Coherence Loss Damage Proxy Map (DPM), 3D fault rupture slip
    from NISAR L2 GOFF pixel offsets, and building/population exposure using VIDA & WorldPop.
    """
    aoi = ee.Geometry.Rectangle(bbox)

    # 1. Build the server-side GEE seismic DPM & fault offset graph
    eq_outputs = compute_earthquake_dpm_and_rupture(
        coh_pre_gcs=coh_pre_gcs,
        coh_coseismic_gcs=coh_coseismic_gcs,
        goff_range_gcs=goff_range_gcs,
        goff_azimuth_gcs=goff_azimuth_gcs,
        aoi=aoi,
    )
    eq_stack = eq_outputs["raster_stack"]
    damaged_buildings_fc = eq_outputs["damaged_buildings_fc"]

    # 2. Render Primary DPM Tile (masked to significant structural decorrelation DPM >= 0.18)
    dpm_viz = (
        eq_stack.select("dpm")
        .updateMask(eq_stack.select("dpm").gte(0.18))
        .getMapId(
            {
                "min": 0.18,
                "max": 0.65,
                "palette": ["fef08a", "f97316", "dc2626", "7f1d1d"],
            }
        )
    )

    # 3. Render Near-Fault 3D Pixel Offset Magnitude Tile (NISAR L2 GOFF)
    goff_viz = (
        eq_stack.select("fault_rupture_disp_m")
        .updateMask(eq_stack.select("fault_rupture_disp_m").gte(0.15))
        .getMapId({"min": 0.15, "max": 2.5, "palette": ["38bdf8", "a855f7", "ec4899"]})
    )

    # 4. Extract Zonal Percentiles + Exposed Population + Damaged VIDA Building Count
    summary = _extract_zonal_stats_and_hotspot(
        metric_stack=eq_stack.select(["dpm", "dpm_zscore", "fault_rupture_disp_m"]),
        primary_band="dpm",
        hotspot_threshold=0.28,
        aoi=aoi,
        scale=30,
    )

    pop_sum = eq_stack.select("population").reduceRegion(
        reducer=ee.Reducer.sum(), geometry=aoi, scale=100, maxPixels=1e8, bestEffort=True
    )
    bldg_count = damaged_buildings_fc.size()
    exposure_info = ee.List([pop_sum, bldg_count]).getInfo()

    exposed_pop = int(round(float((exposure_info[0] or {}).get("population", 0.0))))
    damaged_bldgs = int(exposure_info[1] or 0)

    metrics = summary["zonal_percentiles"]
    metrics["exposed_population_count"] = float(exposed_pop)
    metrics["damaged_vida_buildings_count"] = float(damaged_bldgs)

    alert = (
        "RED"
        if damaged_bldgs > 100
        else "ORANGE"
        if damaged_bldgs > 15
        else "YELLOW"
        if metrics.get("dpm_p99", 0) > 0.25
        else "GREEN"
    )

    return {
        "domain": "earthquake",
        "alert_level": alert,
        "key_quantitative_metrics": metrics,
        "hotspot_coordinates": summary["hotspot_coordinates"],
        "gee_xyz_tile_url": dpm_viz["tile_fetcher"].url_format,
        "diagnostic_rgb_tile_url": goff_viz["tile_fetcher"].url_format,
        "physical_radar_driver": (
            "Co-seismic urban building collapse alters sub-resolution dihedral scatterer geometry, causing "
            "a sudden Z-score drop in L-band interferometric coherence (Delta_gamma >= 0.28) across VIDA "
            "building footprints, while GOFF slant-range/azimuth pixel offsets resolve near-fault slip."
        ),
    }


@mcp.tool
@with_offline_zarr_fallback(timeout_sec=1.8)
def analyze_biomass_disturbance(
    gcov_hhhh_gcs: str,
    gcov_hvhv_gcs: str,
    bbox: list[float],
    s1_start: str = "2026-09-01",
    s1_end: str = "2026-11-13",
) -> dict[str, Any]:
    """
    Executes Module 4 (compute_biomass_and_carbon_flux):
    Fuses NISAR L-band GCOV (HHHH, HVHV) with Sentinel-1 C-band (WFR_L/C), trains an in-situ GEE
    Gradient Boosted Regressor against GEDI L4A shots, and quantifies net carbon loss vs ESA CCI AGB v6.0.
    """
    aoi = ee.Geometry.Rectangle(bbox)

    # 1. Build the server-side GEE allometric GBDT & polarimetric index graph
    bio_stack = compute_biomass_and_carbon_flux(
        gcov_hhhh_gcs=gcov_hhhh_gcs,
        gcov_hvhv_gcs=gcov_hvhv_gcs,
        aoi=aoi,
        s1_start=s1_start,
        s1_end=s1_end,
    )

    # 2. Render Primary Tile: Current NISAR+GEDI Aboveground Biomass Density (Mg/ha)
    agb_viz = bio_stack.select("agb_current_mgha").getMapId(
        {
            "min": 10.0,
            "max": 260.0,
            "palette": ["f7fcb9", "addd8e", "41ab5d", "006837", "004529"],
        }
    )

    # 3. Render Multi-Band Polarimetric Structural RGB Composite Tile:
    # Red = RFDI (Degradation), Green = RVI_dual (Canopy Volume), Blue = WFR_L/C (Woody-to-Foliage Ratio)
    struct_rgb_map = bio_stack.select(["rfdi", "rvi_dual", "wfr_lc_db"]).getMapId(
        {"min": [0.1, 0.2, -4.0], "max": [0.75, 0.9, 6.0]}
    )

    # 4. Extract Zonal Percentiles + Total Carbon Loss (Tons C) where Delta Carbon < -15 Mg C/ha
    summary = _extract_zonal_stats_and_hotspot(
        metric_stack=bio_stack.select(
            [
                "l_hv_db",
                "rfdi",
                "rvi_dual",
                "wfr_lc_db",
                "agb_current_mgha",
                "agb_baseline_mgha",
                "delta_carbon_mgha",
            ]
        ),
        primary_band="rfdi",
        hotspot_threshold=0.55,
        aoi=aoi,
        scale=30,
    )

    # Integrate net carbon loss (tons of Carbon) across disturbed forest pixels
    delta_c = bio_stack.select("delta_carbon_mgha")
    carbon_loss_img = (
        delta_c.multiply(-1.0)
        .updateMask(delta_c.lt(-15.0).And(bio_stack.select("agb_baseline_mgha").gt(80.0)))
        .multiply(ee.Image.pixelArea().divide(1e4))
        .rename("carbon_loss_tons")
    )
    loss_dict = (
        carbon_loss_img.reduceRegion(
            reducer=ee.Reducer.sum(), geometry=aoi, scale=30, maxPixels=1e8, bestEffort=True
        ).getInfo()
        or {}
    )

    carbon_lost_tons = round(float(loss_dict.get("carbon_loss_tons", 0.0)), 1)
    metrics = summary["zonal_percentiles"]
    metrics["aboveground_carbon_disturbed_tons"] = carbon_lost_tons

    alert = (
        "RED"
        if carbon_lost_tons > 2500.0
        else "ORANGE"
        if carbon_lost_tons > 500.0
        else "YELLOW"
        if carbon_lost_tons > 100.0
        else "GREEN"
    )

    return {
        "domain": "biomass",
        "alert_level": alert,
        "key_quantitative_metrics": metrics,
        "hotspot_coordinates": summary["hotspot_coordinates"],
        "gee_xyz_tile_url": agb_viz["tile_fetcher"].url_format,
        "diagnostic_rgb_tile_url": struct_rgb_map["tile_fetcher"].url_format,
        "physical_radar_driver": (
            "NISAR L-band (24.0 cm) HV cross-polarized backscatter penetrates upper foliage to measure "
            "woody branch/trunk volume scattering up to 250 Mg/ha without saturating. Fused with Sentinel-1 "
            "C-band (WFR_L/C) and calibrated in-situ against GEDI L4A laser shots and ESA CCI AGB v6.0."
        ),
    }


if __name__ == "__main__":
    mcp.run()
