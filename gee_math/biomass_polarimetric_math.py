# gee_math/biomass_polarimetric_math.py
import ee


def compute_biomass_and_carbon_flux(
    gcov_hhhh_gcs: str,
    gcov_hvhv_gcs: str,
    aoi: ee.Geometry,
    s1_start: str = "2026-09-01",
    s1_end: str = "2026-11-13",
) -> ee.Image:
    """
    Fuses NISAR L-band GCOV (HHHH, HVHV) with Sentinel-1 C-band, trains an in-situ GEE
    Gradient Boosted Regressor against GEDI L4A biomass shots, and quantifies carbon loss
    against ESA CCI AGB v6.0 (Awesome GEE Community Catalog).
    """
    eps = 1e-6
    l_hh = ee.Image.loadGeoTIFF(gcov_hhhh_gcs).max(eps).rename("l_hh")
    l_hv = ee.Image.loadGeoTIFF(gcov_hvhv_gcs).max(eps).rename("l_hv")

    # 1. Compute L-band Polarimetric Vegetation & Degradation Indices
    polarimetric_indices = ee.Image.cat(  # noqa: F841  (biomass is out of scope; dead code kept as-is)[l_hh, l_hv]).expression(
        """
        var hh = b('l_hh');
        var hv = b('l_hv');
        var rfdi = (hh - hv) / (hh + hv + 1e-6);
        var rvi  = (4.0 * hv) / (hh + hv + 1e-6);
        var cpr  = hv / (hh + 1e-6);
        var hh_db = 10.0 * log10(hh);
        var hv_db = 10.0 * log10(hv);
        """,
    )
    rfdi = l_hh.subtract(l_hv).divide(l_hh.add(l_hv)).rename("rfdi")
    rvi = l_hv.multiply(4.0).divide(l_hh.add(l_hv)).rename("rvi_dual")
    l_hh_db = l_hh.log10().multiply(10.0).rename("l_hh_db")
    l_hv_db = l_hv.log10().multiply(10.0).rename("l_hv_db")

    # 2. Load Sentinel-1 C-Band (VV, VH in dB) for Woody-to-Foliage Multi-Frequency Ratio
    s1 = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(aoi)
        .filterDate(s1_start, s1_end)
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .select(["VV", "VH"])
        .median()
        .clip(aoi)
    )
    wfr_lc = l_hv_db.subtract(s1.select("VH")).rename("wfr_lc_db")

    # 3. Topographic Slope from Awesome GEE Community Catalog FABDEM
    fabdem = (
        ee.ImageCollection("projects/sat-io/open-datasets/FABDEM")
        .filterBounds(aoi)
        .mosaic()
        .clip(aoi)
    )
    slope = ee.Terrain.slope(fabdem).rename("slope_deg")

    # Stack 6 physical radar & terrain predictors
    predictor_Names = ["l_hh_db", "l_hv_db", "rfdi", "rvi_dual", "wfr_lc_db", "slope_deg"]
    predictors = ee.Image.cat([l_hh_db, l_hv_db, rfdi, rvi, wfr_lc, slope])

    # 4. Extract Quality-Filtered GEDI L4A Aboveground Biomass Density (Mg/ha) Training Shots
    gedi_l4a = (
        ee.ImageCollection("LARSE/GEDI/GEDI04_A_002_MONTHLY")
        .filterBounds(aoi)
        .map(lambda img: img.updateMask(img.select("l4_quality_flag").eq(1)).select("agbd"))
        .median()
        .clip(aoi)
        .rename("agbd")
    )

    # Sample GEDI shots across the AOI to train the GEE Gradient Tree Boost Regressor
    training_samples = ee.Image.cat([predictors, gedi_l4a]).sample(
        region=aoi,
        scale=25,
        numPixels=1500,
        seed=2026,
        dropNulls=True,
        geometries=False,
    )

    gbdt_regressor = (
        ee.Classifier.smileGradientTreeBoost(
            numberOfTrees=65,
            shrinkage=0.08,
            maxNodes=24,
        )
        .setOutputMode("REGRESSION")
        .train(
            features=training_samples,
            classProperty="agbd",
            inputProperties=predictor_Names,
        )
    )

    # Predict current Aboveground Biomass (Mg/ha) from NISAR + S1 + FABDEM
    agb_nisar_pred = (
        predictors.classify(gbdt_regressor).clamp(0.0, 380.0).rename("agb_current_mgha")
    )

    # 5. Compare against Awesome GEE Community Catalog ESA CCI AGB v6.0 Baseline
    esa_cci_baseline = (
        ee.ImageCollection("projects/sat-io/open-datasets/ESA/ESA_CCI_AGB")
        .sort("system:time_start", False)
        .first()
        .select([0], ["agb_baseline_mgha"])
        .clip(aoi)
    )

    # Net Aboveground Carbon Change (Mg C / ha, using IPCC 0.47 carbon fraction)
    delta_carbon_mgha = (
        agb_nisar_pred.subtract(esa_cci_baseline).multiply(0.47).rename("delta_carbon_mgha")
    )

    return ee.Image.cat(
        [l_hv_db, rfdi, rvi, wfr_lc, agb_nisar_pred, esa_cci_baseline, delta_carbon_mgha]
    )
