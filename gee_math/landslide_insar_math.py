"""Offline landslide rules and an Earth Engine pipeline with uncalibrated HKLSI."""

import math
from collections.abc import Mapping

import numpy as np

# L-band carrier wavelength, not a threshold.
NISAR_L_BAND_WAVELENGTH_MM = 240.0
DAYS_PER_YEAR = 365.25

# Callers read the preregistered landslide section through bailasar.config.
# Jack4Codes owns config/; absent keys are reported without supplying defaults.
LANDSLIDE_PARAM_KEYS = [
    "coherence_min",
    "stable_slope_max_deg",
    "min_slope_deg",
    "cos_xi_floor",
    "noise_floor.min_pairs",
    "noise_floor.require_sign_agreement",
    "hklsi.weights.velocity",
    "hklsi.weights.slope",
    "hklsi.weights.rain",
    "hklsi.velocity_norm_mm_yr",
    "hklsi.slope_offset_deg",
    "hklsi.slope_norm_deg",
    "hklsi.rain_norm_mm",
    "incidence_deg",
    "heading_deg",
]


def _require(params, dotted_key):
    """Read a required nested parameter, naming the full key on failure."""
    value = params
    for key in dotted_key.split("."):
        if not isinstance(value, Mapping) or key not in value:
            raise KeyError(f"Missing required landslide parameter: {dotted_key}")
        value = value[key]
    return value


def missing_landslide_params(params):
    """Return every key of LANDSLIDE_PARAM_KEYS absent from params (dotted names)."""
    missing = []
    for dotted_key in LANDSLIDE_PARAM_KEYS:
        try:
            _require(params, dotted_key)
        except KeyError:
            missing.append(dotted_key)
    return missing


def noise_floor_verdict(rates_by_pair, stable_residuals_by_pair, params):
    """Keep finite rates exceeding every independent pair's stable-pixel RMS."""
    min_pairs = _require(params, "noise_floor.min_pairs")
    require_sign = _require(params, "noise_floor.require_sign_agreement")
    n_pairs = len(rates_by_pair)
    if len(stable_residuals_by_pair) != n_pairs:
        raise ValueError("Rates and stable residuals must have the same number of pairs")
    rates = [np.asarray(rate, dtype=float) for rate in rates_by_pair]
    shape = rates[0].shape if rates else (0,)
    if any(rate.shape != shape for rate in rates):
        raise ValueError("All pair rates must have equal shapes")
    floors = []
    for residuals in stable_residuals_by_pair:
        residuals = np.asarray(residuals, dtype=float)
        if residuals.ndim != 1:
            raise ValueError("Stable residuals for each pair must be one-dimensional")
        finite = residuals[np.isfinite(residuals)]
        floors.append(float(np.sqrt(np.mean(finite**2))) if finite.size else float("nan"))
    floor = float(np.max(floors)) if floors else float("nan")
    kept_mask = np.full(shape, False, dtype=bool)
    kept_rate = np.full(shape, np.nan)
    if n_pairs and n_pairs >= min_pairs:
        stack = np.stack(rates)
        floor_grid = np.asarray(floors).reshape((n_pairs,) + (1,) * len(shape))
        kept_mask = np.all(np.isfinite(stack) & (np.abs(stack) > floor_grid), axis=0)
        if require_sign:
            kept_mask &= np.all(np.sign(stack) == np.sign(stack[0]), axis=0)
        kept_rate = np.mean(np.where(kept_mask, stack, np.nan), axis=0)
    count = int(np.count_nonzero(kept_mask))
    text = (
        f"motion above {floor:.1f} mm noise floor in {count} pixels ({n_pairs} pairs)"
        if count
        else f"no motion detected above {floor:.1f} mm noise floor ({n_pairs} pairs)"
    )
    if n_pairs < min_pairs:
        text = f"null: {n_pairs} independent pairs available, {min_pairs} required"
    return {
        "kept_rate": kept_rate,
        "kept_mask": kept_mask,
        "n_pairs": n_pairs,
        "noise_floor_mm_yr": floor,
        "per_pair_noise_floor_mm_yr": floors,
        "verdict": "motion detected" if count else "null",
        "text": text,
    }


def project_los_to_downslope(d_los_mm, slope_deg, aspect_deg, params):
    """Project signed LOS displacement using a sign-preserving cosine floor."""
    theta = np.deg2rad(_require(params, "incidence_deg"))
    alpha = np.deg2rad(_require(params, "heading_deg"))
    floor = _require(params, "cos_xi_floor")
    beta = np.deg2rad(np.asarray(slope_deg, dtype=float))
    psi = np.deg2rad(np.asarray(aspect_deg, dtype=float))
    cos_xi = (
        -np.sin(theta) * np.cos(alpha) * np.cos(beta) * np.sin(psi)
        + np.sin(theta) * np.sin(alpha) * np.cos(beta) * np.cos(psi)
        - np.cos(theta) * np.sin(beta)
    )
    regularised = np.where(np.abs(cos_xi) < floor, np.where(cos_xi >= 0, floor, -floor), cos_xi)
    return np.asarray(d_los_mm, dtype=float) / regularised


def hklsi(v_downslope_mm_yr, slope_deg, rain_mm, params):
    """Return the uncalibrated Hydro-Kinematic Landslide Susceptibility Index."""
    # Absolute signed velocity is used only inside HKLSI; exported velocity keeps its sign.
    velocity = np.clip(
        np.abs(v_downslope_mm_yr) / _require(params, "hklsi.velocity_norm_mm_yr"), 0, 1
    )
    slope = np.clip(
        (np.asarray(slope_deg) - _require(params, "hklsi.slope_offset_deg"))
        / _require(params, "hklsi.slope_norm_deg"),
        0,
        1,
    )
    rain = np.clip(np.asarray(rain_mm) / _require(params, "hklsi.rain_norm_mm"), 0, 1)
    return (
        _require(params, "hklsi.weights.velocity") * velocity
        + _require(params, "hklsi.weights.slope") * slope
        + _require(params, "hklsi.weights.rain") * rain
    )


def compute_landslide_insar_kinematics(
    gunw_unw_gcs: str,
    gunw_iono_gcs: str | None,
    gunw_coh_gcs: str,
    gunw_conncomp_gcs: str,
    aoi,
    rain_start_date: str,
    rain_end_date: str,
    temporal_baseline_days: float,
    params: Mapping,
):
    """Compute signed downslope velocity and uncalibrated HKLSI from real layers.

    Missing ionosphere or tropospheric fit leaves displacement and velocity masked.
    Independent-pair noise-floor assessment is provided by noise_floor_verdict.
    """
    missing = missing_landslide_params(params)
    if missing:
        raise KeyError(
            "Missing required landslide parameters (add a landslide: section to "
            f"config/preregistered.yaml): {', '.join(missing)}"
        )
    if temporal_baseline_days <= 0:
        raise ValueError("temporal_baseline_days must be positive")

    import ee

    coh = ee.Image.loadGeoTIFF(gunw_coh_gcs).rename("coherence")
    conn_comp = ee.Image.loadGeoTIFF(gunw_conncomp_gcs).rename("conn_comp")
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
    valid_mask = coh.gte(_require(params, "coherence_min")).And(conn_comp.gt(0))
    if gunw_iono_gcs:
        phi_unw = ee.Image.loadGeoTIFF(gunw_unw_gcs)
        phi_iono = ee.Image.loadGeoTIFF(gunw_iono_gcs)
        corrected = phi_unw.subtract(phi_iono).updateMask(valid_mask).rename("phase")
        stable = slope_deg.lt(_require(params, "stable_slope_max_deg")).And(valid_mask)
        fit = ee.Dictionary(
            ee.Image.cat([fabdem, corrected])
            .updateMask(stable)
            .reduceRegion(
                reducer=ee.Reducer.linearFit(),
                geometry=aoi,
                scale=coh.projection().nominalScale(),
                maxPixels=1e8,
                bestEffort=True,
            )
        )
        missing = coh.updateMask(ee.Image.constant(0))
        has_fit = ee.Algorithms.If(
            ee.Algorithms.IsEqual(fit.get("scale"), None),
            False,
            ee.Algorithms.If(ee.Algorithms.IsEqual(fit.get("offset"), None), False, True),
        )
        d_los_mm = ee.Image(
            ee.Algorithms.If(
                has_fit,
                corrected.subtract(
                    fabdem.multiply(ee.Number(fit.get("scale"))).add(ee.Number(fit.get("offset")))
                ).multiply(-NISAR_L_BAND_WAVELENGTH_MM / (4 * math.pi)),
                missing,
            )
        ).rename("d_los_mm")
        displacement_status = ee.Algorithms.If(has_fit, "available", "missing: tropospheric fit")
    else:
        d_los_mm = coh.updateMask(ee.Image.constant(0)).rename("d_los_mm")
        displacement_status = "missing: ionosphere layer not available"

    theta = math.radians(_require(params, "incidence_deg"))
    alpha = math.radians(_require(params, "heading_deg"))
    beta = slope_deg.multiply(math.pi / 180)
    psi = aspect_deg.multiply(math.pi / 180)
    cos_xi = (
        beta.cos()
        .multiply(psi.sin())
        .multiply(-math.sin(theta) * math.cos(alpha))
        .add(beta.cos().multiply(psi.cos()).multiply(math.sin(theta) * math.sin(alpha)))
        .subtract(beta.sin().multiply(math.cos(theta)))
    )
    floor = _require(params, "cos_xi_floor")
    regularised = cos_xi.where(cos_xi.abs().lt(floor).And(cos_xi.gte(0)), floor).where(
        cos_xi.abs().lt(floor).And(cos_xi.lt(0)), -floor
    )
    velocity = (
        d_los_mm.divide(regularised)
        .multiply(DAYS_PER_YEAR / temporal_baseline_days)
        .updateMask(slope_deg.gte(_require(params, "min_slope_deg")))
        .rename("v_downslope_mm_yr")
    )
    rain = (
        ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
        .filterBounds(aoi)
        .filterDate(rain_start_date, rain_end_date)
        .sum()
        .clip(aoi)
        .rename("rain_15d_mm")
    )
    # Absolute signed velocity is used only inside HKLSI; exported velocity keeps its sign.
    score = (
        velocity.abs()
        .divide(_require(params, "hklsi.velocity_norm_mm_yr"))
        .clamp(0, 1)
        .multiply(_require(params, "hklsi.weights.velocity"))
        .add(
            slope_deg.subtract(_require(params, "hklsi.slope_offset_deg"))
            .divide(_require(params, "hklsi.slope_norm_deg"))
            .clamp(0, 1)
            .multiply(_require(params, "hklsi.weights.slope"))
        )
        .add(
            rain.divide(_require(params, "hklsi.rain_norm_mm"))
            .clamp(0, 1)
            .multiply(_require(params, "hklsi.weights.rain"))
        )
        .rename("landslide_hazard_index")
        .set({"calibrated": False, "label": "uncalibrated"})
    )
    return ee.Image.cat([d_los_mm, velocity, slope_deg, rain, coh, score]).set(
        {"displacement": displacement_status, "calibrated": False, "label": "uncalibrated"}
    )
