"""Rain trigger, effective stress, and plane-wedge stability.

Green and Ampt (1911) supply the ponded infiltration depth. A staged rainfall
depth caps that infiltration and is never replaced by zero when it is missing.
Culmann's plane wedge supplies the critical height. SPT-N enters only through
the Wolff (1989) fit to Peck, Hanson and Thornburn (1974) for friction angle
and through Stroud (1974) ``cu = f1 * N`` when the caller passes ``f1``.
The freshwater unit weight below is the method constant, not an AOI measurement.
"""

from __future__ import annotations

import math

# Freshwater unit weight used by the effective-stress change. Not an AOI datum.
WATER_UNIT_WEIGHT_KN_M3 = 9.81


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def green_ampt_wetting_front(
    duration_s: object,
    k_m_s: object,
    psi_m: object,
    delta_theta: object,
    rainfall_m: object = None,
) -> dict:
    """Ponded Green-Ampt infiltration and wetting-front depth.

    Solves ``F = K t + psi * dtheta * ln(1 + F / (psi * dtheta))`` by Newton,
    then ``z_f = F / dtheta``. When ``rainfall_m`` is provided, ``F`` cannot
    exceed it. ``rainfall_m is None`` means an unlimited ponded supply, which
    is only for the known-answer test. A missing or non-positive soil term
    returns null depths and does not converge to zero.
    """
    withheld = {"infiltration_m": None, "wetting_front_m": None, "reason": "missing_or_invalid"}
    duration = _finite_number(duration_s)
    conductivity = _finite_number(k_m_s)
    suction = _finite_number(psi_m)
    fillable = _finite_number(delta_theta)
    if (
        duration is None
        or conductivity is None
        or suction is None
        or fillable is None
        or duration <= 0
        or conductivity <= 0
        or suction <= 0
        or fillable <= 0
    ):
        return withheld
    rainfall = None
    if rainfall_m is not None:
        rainfall = _finite_number(rainfall_m)
        if rainfall is None or rainfall < 0:
            return withheld
        if rainfall == 0.0:
            return {"infiltration_m": 0.0, "wetting_front_m": 0.0, "reason": None}

    psi_dtheta = suction * fillable
    kt = conductivity * duration
    depth = max(kt, 1e-12)
    converged = False
    for _ in range(60):
        if depth <= 0 or not math.isfinite(depth):
            break
        function = depth - kt - psi_dtheta * math.log(1.0 + depth / psi_dtheta)
        derivative = 1.0 - psi_dtheta / (psi_dtheta + depth)
        if not math.isfinite(derivative) or derivative == 0.0:
            break
        nxt = depth - function / derivative
        if nxt <= 0:
            nxt = depth / 2.0
        if abs(nxt - depth) < 1e-12:
            depth = nxt
            converged = True
            break
        depth = nxt
    if not converged or not math.isfinite(depth) or depth < 0:
        return {"infiltration_m": None, "wetting_front_m": None, "reason": "no_convergence"}
    if rainfall is not None:
        depth = min(depth, rainfall)
    return {
        "infiltration_m": float(depth),
        "wetting_front_m": float(depth / fillable),
        "reason": None,
    }


def wetting_front_reaches(wetting_front_m: object, failure_depth_m: object) -> bool | None:
    """True when the wet front is at or below a staged failure depth.

    None when either depth is missing. A measured miss is False, not None.
    """
    front = _finite_number(wetting_front_m)
    failure = _finite_number(failure_depth_m)
    if front is None or failure is None or failure < 0:
        return None
    return front >= failure


def effective_stress_change_kpa(
    water_table_rise_m: object,
    unit_weight_water_kn_m3: float = WATER_UNIT_WEIGHT_KN_M3,
) -> float | None:
    """Change in effective stress for a staged water-table rise.

    ``Δσ' = -γ_w Δh``. A rise is positive and reduces effective stress.
    A missing rise is None. Zero rise is a measured zero.
    """
    rise = _finite_number(water_table_rise_m)
    weight = _finite_number(unit_weight_water_kn_m3)
    if rise is None or weight is None or weight <= 0:
        return None
    return float(-weight * rise)


def phi_deg_peck_wolff(spt_n: object) -> float | None:
    """Friction angle in degrees from SPT-N.

    Wolff (1989) approximation of Peck, Hanson and Thornburn (1974):
    ``φ = 27.1 + 0.3 N - 0.00054 N²``. A missing or negative N is None.
    N of zero is a valid blow count.
    """
    blows = _finite_number(spt_n)
    if blows is None or blows < 0:
        return None
    return float(27.1 + 0.3 * blows - 0.00054 * blows * blows)


def cu_kpa_stroud(spt_n: object, factor: object) -> float | None:
    """Undrained strength ``cu = f1 * N`` (Stroud 1974), with ``f1`` supplied by the caller.

    There is no hidden plasticity factor. A missing N or factor is None.
    """
    blows = _finite_number(spt_n)
    strength_factor = _finite_number(factor)
    if blows is None or strength_factor is None or blows < 0 or strength_factor < 0:
        return None
    return float(strength_factor * blows)


def built_up_surcharge_kpa(built_fraction: object, surcharge_on_built_kpa: object) -> float | None:
    """Area-weighted surcharge. Fraction must be in ``[0, 1]``. Missing inputs are None."""
    fraction = _finite_number(built_fraction)
    surcharge = _finite_number(surcharge_on_built_kpa)
    if fraction is None or surcharge is None:
        return None
    if fraction < 0 or fraction > 1 or surcharge < 0:
        return None
    return float(fraction * surcharge)


def culmann_plane_wedge(
    cohesion_kpa: object,
    friction_deg: object,
    slope_deg: object,
    unit_weight_kn_m3: object,
    height_m: object = None,
    surcharge_kpa: object = None,
) -> dict:
    """Culmann critical height and factor of safety for a plane wedge.

    ``H_c = (4 c / γ) * sin(β) cos(φ) / (1 - cos(β - φ))``.
    ``FS = H_c / H``. With a surcharge, ``H`` becomes ``H + q / γ``.
    When ``β <= φ`` the wedge formula has no finite critical height.
    """
    empty = {
        "critical_height_m": None,
        "factor_of_safety": None,
        "factor_of_safety_with_surcharge": None,
        "reason": "missing_or_invalid",
    }
    cohesion = _finite_number(cohesion_kpa)
    friction = _finite_number(friction_deg)
    slope = _finite_number(slope_deg)
    weight = _finite_number(unit_weight_kn_m3)
    if cohesion is None or friction is None or slope is None or weight is None:
        return empty
    if cohesion < 0 or weight <= 0 or not 0 < slope < 90 or not 0 <= friction < 90:
        return empty
    if slope <= friction:
        return {
            "critical_height_m": None,
            "factor_of_safety": None,
            "factor_of_safety_with_surcharge": None,
            "reason": "beta_not_steeper_than_phi",
        }
    slope_rad = math.radians(slope)
    friction_rad = math.radians(friction)
    denominator = 1.0 - math.cos(slope_rad - friction_rad)
    if denominator <= 0:
        return {
            "critical_height_m": None,
            "factor_of_safety": None,
            "factor_of_safety_with_surcharge": None,
            "reason": "beta_not_steeper_than_phi",
        }
    critical = (4.0 * cohesion / weight) * (
        math.sin(slope_rad) * math.cos(friction_rad) / denominator
    )
    result = {
        "critical_height_m": float(critical),
        "factor_of_safety": None,
        "factor_of_safety_with_surcharge": None,
        "reason": None,
    }
    height = None if height_m is None else _finite_number(height_m)
    if height_m is not None and (height is None or height <= 0):
        result["reason"] = "invalid_height"
        return result
    if height is not None:
        result["factor_of_safety"] = float(critical / height)
    if surcharge_kpa is None:
        return result
    surcharge = _finite_number(surcharge_kpa)
    if surcharge is None or surcharge < 0:
        result["reason"] = "invalid_surcharge"
        return result
    if height is not None:
        result["factor_of_safety_with_surcharge"] = float(critical / (height + surcharge / weight))
    return result
