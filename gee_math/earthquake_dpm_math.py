# gee_math/earthquake_dpm_math.py
import ee

def compute_earthquake_dpm_and_rupture(
    coh_pre_gcs: str,
    coh_coseismic_gcs: str,
    goff_range_gcs: str,
    goff_azimuth_gcs: str,
    aoi: ee.Geometry,
) -> dict:
    """
    Computes ARIA-style Coherence Loss Damage Proxy Map (DPM), 3D fault rupture magnitude from
    NISAR L2 GOFF offsets, and building-level impact on VIDA Combined Footprints & WorldPop.
    """
    coh_pre = ee.Image.loadGeoTIFF(coh_pre_gcs).rename("coh_pre")
    coh_co = ee.Image.loadGeoTIFF(coh_coseismic_gcs).rename("coh_co")
    range_off_m = ee.Image.loadGeoTIFF(goff_range_gcs).rename("range_offset_m")
    azim_off_m = ee.Image.loadGeoTIFF(goff_azimuth_gcs).rename("azimuth_offset_m")

    # 1. Compute Normalized Coherence Drop (DPM) and Z-Score
    raw_diff = coh_pre.subtract(coh_co)
    bg_stats = raw_diff.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.stdDev(), "", True),
        geometry=aoi,
        scale=90,
        maxPixels=1e8,
        bestEffort=True,
    )
    mean_diff = ee.Number(bg_stats.get("coh_pre_mean", 0.0))
    std_diff = ee.Number(bg_stats.get("coh_pre_stdDev", 0.1)).max(0.02)

    dpm = raw_diff.clamp(0.0, 1.0).rename("dpm")
    dpm_zscore = (
        raw_diff.subtract(mean_diff)
        .divide(std_diff)
        .updateMask(coh_pre.gte(0.45))  # Only evaluate pixels that were coherent pre-earthquake
        .rename("dpm_zscore")
    )

    # 2. Near-Field Fault Rupture Magnitude from NISAR L2 GOFF (Slant Range + Azimuth Offsets)
    fault_displacement_m = (
        range_off_m.hypot(azim_off_m).rename("fault_rupture_disp_m")
    )

    # 3. Intersect Severe DPM (dpm >= 0.28 and z >= 2.0) with WorldPop & VIDA Building Footprints
    severe_damage_mask = dpm.gte(0.28).And(dpm_zscore.gte(2.0))

    worldpop = (
        ee.ImageCollection("projects/sat-io/open-datasets/worldpop/pop")
        .filterBounds(aoi)
        .sort("system:time_start", False)
        .first()
        .clip(aoi)
        .rename("population")
    )

    # Awesome GEE Community Catalog: VIDA Combined Building Footprints for Colombia
    vida_buildings = (
        ee.FeatureCollection("projects/sat-io/open-datasets/VIDA_COMBINED/COL")
        .filterBounds(aoi)
    )

    # Stamp mean DPM onto building footprints inside the AOI
    damaged_buildings_fc = dpm.reduceRegions(
        collection=vida_buildings.limit(2500),
        reducer=ee.Reducer.mean(),
        scale=20,
    ).filter(ee.Filter.gte("mean", 0.28))

    return {
        "raster_stack": ee.Image.cat([dpm, dpm_zscore, fault_displacement_m, worldpop.updateMask(severe_damage_mask)]),
        "damaged_buildings_fc": damaged_buildings_fc,
    }
