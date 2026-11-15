# gee_math/flood_polarimetric_math.py
import ee


def compute_flood_scattering_decomposition(
    gcov_hhhh_pre_gcs: str,
    gcov_hvhv_pre_gcs: str,
    gcov_hhhh_post_gcs: str,
    gcov_hvhv_post_gcs: str,
    aoi: ee.Geometry,
    s1_post_start: str = "2026-11-01",
    s1_post_end: str = "2026-11-13",
) -> ee.Image:
    """
    Decomposes NISAR L2 GCOV polarimetric covariance (HHHH, HVHV) fused with Sentinel-1 C-band
    and MERIT Hydro HAND to map both Specular Open-Water and Sub-Canopy Double-Bounce Flooding.
    """
    eps = 1e-6
    hh_pre = ee.Image.loadGeoTIFF(gcov_hhhh_pre_gcs).max(eps)
    hv_pre = ee.Image.loadGeoTIFF(gcov_hvhv_pre_gcs).max(eps)
    hh_post = ee.Image.loadGeoTIFF(gcov_hhhh_post_gcs).max(eps)
    hv_post = ee.Image.loadGeoTIFF(gcov_hvhv_post_gcs).max(eps)

    # 1. Convert linear gamma0 covariance to decibels (dB) and compute temporal Log-Ratio
    hh_pre_db = hh_pre.log10().multiply(10.0).rename("hh_pre_db")
    hh_post_db = hh_post.log10().multiply(10.0).rename("hh_post_db")
    hv_post_db = hv_post.log10().multiply(10.0).rename("hv_post_db")
    delta_hh_db = hh_post_db.subtract(hh_pre_db).rename("delta_hh_db")

    # 2. Dual-Pol Freeman-Style Power Decomposition (Linear Power Domain)
    # Volume power Pv = 4 * HVHV; Surface/Double-Bounce power P_sd = max(HHHH - 2*HVHV, 0)
    decomp = (
        ee.Image.cat([hh_post, hv_post, hh_pre, hv_pre])
        .expression(
            """
        var pv_post  = 4.0 * b(1);
        var psd_post = max(b(0) - (2.0 * b(1)), 0.0);
        var span_post = b(0) + (2.0 * b(1));
        var double_bounce_fraction = psd_post / (span_post + 1e-6);
        double_bounce_fraction
        """
        )
        .rename("double_bounce_fraction")
    )

    # 3. Ancillary Hydrological Conditioning: MERIT Hydro HAND & JRC Permanent Water
    hand = ee.Image("MERIT/Hydro/v1_0_1").select("hnd").clip(aoi).rename("hand_m")
    perm_water = (
        ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("seasonality").gte(10).clip(aoi).unmask(0)
    )
    floodplain_mask = hand.lt(18.0).And(perm_water.Not())

    # 4. Fuse Sentinel-1 C-Band VV for Multi-Frequency Specular Confirmation
    s1_vv_db = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(aoi)
        .filterDate(s1_post_start, s1_post_end)
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .select("VV")
        .median()
        .clip(aoi)
        .rename("s1_vv_db")
    )

    # 5. Classify Physical Flood Regimes
    # Regime 1: Specular Open-Water Flood (Dark in both L-band HH and C-band VV)
    open_water_flood = (
        delta_hh_db.lt(-5.5)
        .And(hh_post_db.lt(-14.5))
        .And(s1_vv_db.lt(-16.0))
        .And(floodplain_mask)
        .rename("specular_open_flood")
    )

    # Regime 2: Sub-Canopy Dihedral Double-Bounce Flood (L-band HH surges > +3.0 dB while HV volume stays high)
    subcanopy_flood = (
        delta_hh_db.gt(3.0)
        .And(hv_post_db.gt(-15.5))
        .And(decomp.gt(0.55))
        .And(floodplain_mask)
        .rename("subcanopy_double_bounce_flood")
    )

    # Categorical Flood Class (0: Non-Flood, 1: Specular Open Water, 2: Sub-Canopy Double-Bounce)
    flood_class = (
        open_water_flood.multiply(1).add(subcanopy_flood.multiply(2)).rename("flood_regime_class")
    )

    return ee.Image.cat(
        [
            hh_post_db,
            hv_post_db,
            delta_hh_db,
            decomp,
            open_water_flood,
            subcanopy_flood,
            flood_class,
        ]
    )
