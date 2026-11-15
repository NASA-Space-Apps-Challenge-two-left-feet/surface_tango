# gee_math/landslide_insar_math.py
import math

import ee


def compute_landslide_insar_kinematics(
    gunw_unw_gcs: str,
    gunw_iono_gcs: str,
    gunw_coh_gcs: str,
    gunw_conncomp_gcs: str,
    aoi: ee.Geometry,
    rain_start_date: str = "2026-10-29",
    rain_end_date: str = "2026-11-13",
    temporal_baseline_days: float = 12.0,
    inc_angle_deg: float = 37.5,
    sat_heading_deg: float = -12.0,  # Ascending NISAR orbit over Colombia (~348 deg)
) -> ee.Image:
    """
    Computes ionosphere/troposphere-corrected L-band InSAR downslope velocity (mm/yr)
    and Hydro-Kinematic Landslide Hazard Score using bare-earth FABDEM and CHIRPS.
    """
    # 1. Load NISAR L2 GUNW grids from GCS COGs
    phi_unw = ee.Image.loadGeoTIFF(gunw_unw_gcs).rename("phi_unw")
    phi_iono = ee.Image.loadGeoTIFF(gunw_iono_gcs).rename("phi_iono")
    coh = ee.Image.loadGeoTIFF(gunw_coh_gcs).rename("coherence")
    conn_comp = ee.Image.loadGeoTIFF(gunw_conncomp_gcs).rename("conn_comp")

    # 2. Load Bare-Earth FABDEM (30m tree/building removed DEM from GEE Community Catalog)
    fabdem = (
        ee.ImageCollection("projects/sat-io/open-datasets/FABDEM")
        .filterBounds(aoi)
        .mosaic()
        .clip(aoi)
        .rename("elev_m")
    )
    terrain = ee.Terrain.products(fabdem)
    slope_deg = terrain.select("slope")
    aspect_deg = terrain.select("aspect")

    # 3. Phase Unwrapping Mask & Stratified Tropospheric Delay Removal
    # Quality mask: coherence >= 0.35 and valid non-zero connected component
    valid_insar_mask = coh.gte(0.35).And(conn_comp.gt(0))
    phi_iono_corr = phi_unw.subtract(phi_iono).updateMask(valid_insar_mask)

    # Estimate linear elevation-dependent tropospheric phase ramp (rad/m) over stable flat terrain (<8 deg)
    stable_mask = slope_deg.lt(8.0).And(valid_insar_mask)
    tropo_fit = (
        ee.Image.cat([fabdem, phi_iono_corr])
        .updateMask(stable_mask)
        .reduceRegion(
            reducer=ee.Reducer.linearFit(),
            geometry=aoi,
            scale=90,
            maxPixels=1e8,
            bestEffort=True,
        )
    )
    k_tropo = ee.Number(ee.Dictionary(tropo_fit).get("scale", 0.0))
    c_tropo = ee.Number(ee.Dictionary(tropo_fit).get("offset", 0.0))
    phi_tropo = fabdem.multiply(k_tropo).add(c_tropo)

    # Pure deformation phase -> LOS displacement in millimeters (NISAR L-band lambda = 240.0 mm)
    lambda_mm = 240.0
    d_los_mm = (
        phi_iono_corr.subtract(phi_tropo).multiply(-lambda_mm / (4.0 * math.pi)).rename("d_los_mm")
    )

    # 4. Exact 3D Vector Projection onto Steepest Downslope (u_LOS . u_slope)
    deg2rad = math.pi / 180.0
    projection_img = (
        ee.Image.cat([d_los_mm, slope_deg, aspect_deg])
        .expression(
            """
        // Unit LOS vector (East, North, Up)
        var theta = inc_deg * deg2rad;
        var alpha = heading_deg * deg2rad;
        var los_e = -sin(theta) * cos(alpha);
        var los_n =  sin(theta) * sin(alpha);
        var los_u =  cos(theta);

        // Unit steepest downslope vector (East, North, Up)
        var beta = b('slope') * deg2rad;
        var psi  = b('aspect') * deg2rad;
        var slp_e =  cos(beta) * sin(psi);
        var slp_n =  cos(beta) * cos(psi);
        var slp_u = -sin(beta);

        // Cosine of angle between LOS and downslope vector (regularized against near-orthogonal layover)
        var cos_xi = (los_e * slp_e) + (los_n * slp_n) + (los_u * slp_u);
        var reg_cos_xi = abs(cos_xi) < 0.20 ? (cos_xi >= 0 ? 0.20 : -0.20) : cos_xi;

        var d_downslope_mm = abs(b('d_los_mm') / reg_cos_xi);
        var v_downslope_mm_yr = d_downslope_mm * (365.25 / dt_days);
        v_downslope_mm_yr
        """,
            {
                "inc_deg": inc_angle_deg,
                "heading_deg": sat_heading_deg,
                "dt_days": temporal_baseline_days,
                "deg2rad": deg2rad,
            },
        )
        .updateMask(slope_deg.gte(15.0))
        .rename("v_downslope_mm_yr")
    )

    # 5. Hydro-Geotechnical Pore Pressure Coupling (CHIRPS 15-day + Topographic Wetness Index proxy)
    chirps_15d = (
        ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
        .filterBounds(aoi)
        .filterDate(rain_start_date, rain_end_date)
        .sum()
        .clip(aoi)
        .rename("rain_15d_mm")
    )

    # Composite Hydro-Kinematic Landslide Susceptibility Index (0.0 to 1.0)
    hklsi = (
        ee.Image.cat([projection_img, slope_deg, chirps_15d])
        .expression(
            """
        var v_norm = clamp(b('v_downslope_mm_yr') / 120.0, 0.0, 1.0);
        var s_norm = clamp((b('slope') - 15.0) / 30.0, 0.0, 1.0);
        var r_norm = clamp(b('rain_15d_mm') / 200.0, 0.0, 1.0);
        (0.50 * v_norm) + (0.25 * s_norm) + (0.25 * r_norm)
        """
        )
        .rename("landslide_hazard_index")
    )

    return ee.Image.cat([d_los_mm, projection_img, slope_deg, chirps_15d, coh, hklsi])
