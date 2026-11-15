"""Known-answer tests for Green-Ampt, Culmann, SPT-N, and effective stress.

Inputs are hand-written. Expected numbers are the closed-form arithmetic below.
"""

from gee_math.landslide_hydrogeology import (
    built_up_surcharge_kpa,
    cu_kpa_stroud,
    culmann_plane_wedge,
    effective_stress_change_kpa,
    green_ampt_wetting_front,
    phi_deg_peck_wolff,
    wetting_front_reaches,
)

# psi = 0.5 m, dtheta = 0.2, psi*dtheta = 0.1 m, F = 0.1 m.
# K t = F - psi*dtheta*ln(1 + F/(psi*dtheta)) = 0.1*(1 - ln 2) = 0.03068528194400546 m
# K = 1e-5 m/s → t = 3068.528194400546 s. z_f = F/dtheta = 0.5 m.
GREEN_AMPT_SECONDS = 3068.528194400546
# β = 60°, φ = 30°, c = 10 kPa, γ = 20 kN/m³.
# sin(60) cos(30) = 0.75. 1 - cos(30°) = 1 - √3/2.
# H_c = (4*10/20) * 0.75 / (1 - cos(30°)) = 11.196152422706637 m.
# H = 5 m → FS = 2.2392304845413276. q = 10 kPa → H + q/γ = 5.5 → FS = 2.035664076855752.
CULMANN_HEIGHT_M = 11.196152422706637
CULMANN_FS = 2.2392304845413276
CULMANN_FS_LOADED = 2.035664076855752


def test_green_ampt_recovers_the_chosen_front_and_caps_at_rainfall():
    ponded = green_ampt_wetting_front(GREEN_AMPT_SECONDS, 1e-5, 0.5, 0.2)
    assert ponded["reason"] is None
    assert ponded["infiltration_m"] == pytest_approx(0.1)
    assert ponded["wetting_front_m"] == pytest_approx(0.5)
    capped = green_ampt_wetting_front(GREEN_AMPT_SECONDS, 1e-5, 0.5, 0.2, rainfall_m=0.02)
    assert capped["infiltration_m"] == pytest_approx(0.02)
    assert capped["wetting_front_m"] == pytest_approx(0.1)
    dry = green_ampt_wetting_front(GREEN_AMPT_SECONDS, 1e-5, 0.5, 0.2, rainfall_m=0.0)
    assert dry["infiltration_m"] == 0.0
    assert dry["wetting_front_m"] == 0.0
    missing = green_ampt_wetting_front(GREEN_AMPT_SECONDS, None, 0.5, 0.2, rainfall_m=0.1)
    assert missing["infiltration_m"] is None
    assert missing["wetting_front_m"] is None
    assert wetting_front_reaches(0.5, 0.4) is True
    assert wetting_front_reaches(0.5, 0.5) is True
    assert wetting_front_reaches(0.5, 0.6) is False
    assert wetting_front_reaches(0.5, None) is None


def test_effective_stress_falls_by_the_water_unit_weight_times_the_rise():
    # γ_w = 9.81 kN/m³, rise = 2 m → Δσ' = -19.62 kPa.
    assert effective_stress_change_kpa(2.0) == pytest_approx(-19.62)
    assert effective_stress_change_kpa(0.0) == 0.0
    assert effective_stress_change_kpa(None) is None


def test_spt_correlations_match_the_published_equations():
    # N = 10 → φ = 27.1 + 3 - 0.00054*100 = 30.046°.
    assert phi_deg_peck_wolff(10) == pytest_approx(30.046)
    assert phi_deg_peck_wolff(0) == pytest_approx(27.1)
    assert phi_deg_peck_wolff(None) is None
    assert phi_deg_peck_wolff(-1) is None
    # Stroud: cu = 4.5 * 8 = 36 kPa. The factor is an argument, not a hidden default.
    assert cu_kpa_stroud(8, 4.5) == 36.0
    assert cu_kpa_stroud(8, None) is None
    assert built_up_surcharge_kpa(0.25, 20.0) == 5.0
    assert built_up_surcharge_kpa(1.2, 20.0) is None
    assert built_up_surcharge_kpa(None, 20.0) is None


def test_culmann_critical_height_and_loaded_factor_of_safety():
    result = culmann_plane_wedge(10.0, 30.0, 60.0, 20.0, 5.0, 10.0)
    assert result["reason"] is None
    assert result["critical_height_m"] == pytest_approx(CULMANN_HEIGHT_M)
    assert result["factor_of_safety"] == pytest_approx(CULMANN_FS)
    assert result["factor_of_safety_with_surcharge"] == pytest_approx(CULMANN_FS_LOADED)
    stable = culmann_plane_wedge(10.0, 40.0, 30.0, 20.0, 5.0)
    assert stable["reason"] == "beta_not_steeper_than_phi"
    assert stable["critical_height_m"] is None
    missing = culmann_plane_wedge(None, 30.0, 60.0, 20.0, 5.0)
    assert missing["critical_height_m"] is None
    assert missing["factor_of_safety"] is None


def pytest_approx(value):
    import pytest

    return pytest.approx(value)
