"""Known-answer tests for the Aburrá landslide InSAR functions.

Arrays here are hand-written and the expected numbers are hand-computed.
They stay in tests/ and never reach the cache, the UI, or the report.
"""

import math

import numpy as np
import pytest

from gee_math import landslide_insar_math as slide

# λ = 0.24 m, Δφ = 1 rad.
# 4π = 12.566370614359172
# λ / 4π = 0.019098593171027442 m = 19.09859317102744 mm
# d_LOS = −19.09859317102744 mm
LOS_MM_FOR_ONE_RADIAN = -19.09859317102744

# Downslope check. β = 20°, aspect = 0 (downhill north).
# u_down = (0, cos 20°, −sin 20°) = (0, 0.9396926207859084, −0.3420201433256687)
# u_LOS  = (0, sin 37°, cos 37°) = (0, 0.6018150231520483, 0.7986355100472928)
# cos ξ = 0.29237170472273677
# d_LOS = 10 mm → d_down = 10 / cos ξ = 34.20303619833268 mm
DOWNSLOPE_MM = 34.20303619833268


def test_ionosphere_subtraction_keeps_missing_as_nan():
    corrected = slide.subtract_ionosphere(
        np.array([1.0, 2.0, 3.0]),
        np.array([0.25, np.nan, 0.5]),
    )
    assert corrected[0] == pytest.approx(0.75)
    assert corrected[2] == pytest.approx(2.5)
    assert math.isnan(corrected[1])


def test_sign_convention_positive_phase_is_negative_los():
    los = slide.los_displacement_mm(np.array([1.0, -2.0]))
    assert los[0] == pytest.approx(LOS_MM_FOR_ONE_RADIAN)
    assert los[1] == pytest.approx(-2.0 * LOS_MM_FOR_ONE_RADIAN)
    assert los[0] < 0.0


def test_troposphere_fit_on_a_hand_built_ramp():
    # los = 2 + 0.01 * elevation on the stable pixels, plus a 7.5 mm bump
    # off the ramp at 250 m that the fit must not absorb.
    elevation = np.array([100.0, 200.0, 300.0, 400.0, 250.0])
    los = np.array([3.0, 4.0, 5.0, 6.0, 12.0])
    stable = np.array([True, True, True, True, False])
    offset, scale, rms, n_stable = slide.fit_los_elevation(los, elevation, stable)
    assert n_stable == 4
    assert offset == pytest.approx(2.0)
    assert scale == pytest.approx(0.01)
    assert rms == pytest.approx(0.0, abs=1e-9)
    corrected = slide.remove_stratified_troposphere(los, elevation, offset, scale)
    assert corrected[0] == pytest.approx(0.0, abs=1e-9)
    assert corrected[3] == pytest.approx(0.0, abs=1e-9)
    # 0.01 * 250 + 2 = 4.5; 12 − 4.5 = 7.5
    assert corrected[4] == pytest.approx(7.5)


def test_failed_troposphere_fit_stays_nan():
    corrected = slide.remove_stratified_troposphere(
        np.array([1.0, 2.0]), np.array([10.0, 20.0]), math.nan, 0.0
    )
    assert np.isnan(corrected).all()


def test_reference_component_is_the_largest_valid_label():
    components = np.array(
        [
            [0, 1, 1],
            [2, 2, 2],
            [slide.COMPONENT_FILL, 1, 2],
        ]
    )
    # Label 1 has 3 pixels, label 2 has 4, 0 and 65535 are invalid.
    assert slide.reference_component_id(components) == 2
    masked, ref = slide.mask_to_reference_component(np.ones((3, 3)), components)
    assert ref == 2
    assert np.isnan(masked[0, 1])
    assert masked[1, 0] == pytest.approx(1.0)
    assert np.isnan(masked[2, 0])


def test_layover_and_shadow_geometry():
    # Radar looks east (azimuth 90°). Incidence 40°.
    # Aspect 270° is downhill toward the west, so the slope faces the radar.
    # 50° foreslope is steeper than 40°: layover.
    assert slide.layover_or_shadow(np.array([50.0]), np.array([270.0]), 40.0, 90.0)[0]
    # Aspect 90° is downhill toward the east: a backslope. 60° exceeds
    # 90° − 40° = 50°, so the pixel is in shadow.
    assert slide.layover_or_shadow(np.array([60.0]), np.array([90.0]), 40.0, 90.0)[0]
    gentle = slide.layover_or_shadow(np.array([2.0]), np.array([0.0]), 40.0, 90.0)
    assert not gentle[0]


def test_downslope_projection_keeps_sign_and_drops_unstable_pixels():
    los_east = 0.0
    los_north = math.sin(math.radians(37.0))
    los_up = math.cos(math.radians(37.0))
    down = slide.downslope_displacement_mm(
        np.array([10.0, -10.0]),
        np.array([20.0, 20.0]),
        np.array([0.0, 0.0]),
        los_east,
        los_north,
        los_up,
    )
    assert down[0] == pytest.approx(DOWNSLOPE_MM)
    assert down[1] == pytest.approx(-DOWNSLOPE_MM)
    # Horizontal downslope against a vertical LOS: cosine is 0, so the
    # pixel stays missing instead of being clamped.
    unstable = slide.downslope_displacement_mm(
        np.array([10.0]),
        np.array([0.0]),
        np.array([0.0]),
        0.0,
        0.0,
        1.0,
    )
    assert math.isnan(unstable[0])


def test_noise_floor_accepts_two_independent_pairs():
    result = slide.noise_floor(
        los_mm=[np.array([[5.0]]), np.array([[6.0]])],
        downslope_mm=[np.array([[5.0]]), np.array([[4.0]])],
        rate_mm_per_yr=[np.array([[150.0]]), np.array([[120.0]])],
        residual_rms_mm=[2.0, 2.0],
        acquisition_dates=[
            frozenset({"2026-06-17", "2026-06-29"}),
            frozenset({"2026-07-11", "2026-07-23"}),
        ],
    )
    assert result.n_pixels_kept == 1
    assert result.n_pairs == 2
    assert result.kept_rate_mm_per_yr[0, 0] == pytest.approx(135.0)
    assert result.noise_floor_mm == pytest.approx(2.0)
    assert result.verdict == "kept downslope rates on 1 pixels; noise floor 2 mm (2 pairs)"


def test_noise_floor_rejects_below_rms_and_opposite_signs():
    below = slide.noise_floor(
        los_mm=[np.array([[1.0]]), np.array([[1.5]])],
        downslope_mm=[np.array([[1.0]]), np.array([[1.5]])],
        rate_mm_per_yr=[np.array([[10.0]]), np.array([[12.0]])],
        residual_rms_mm=[2.0, 4.0],
        acquisition_dates=[
            frozenset({"2026-06-17", "2026-06-29"}),
            frozenset({"2026-07-11", "2026-07-23"}),
        ],
    )
    # Published floor is the median of the pair RMS values: median(2, 4) = 3.
    assert below.verdict == "no motion detected above 3 mm (2 pairs)"
    assert below.n_pixels_kept == 0
    assert math.isnan(below.kept_rate_mm_per_yr[0, 0])

    opposite = slide.noise_floor(
        los_mm=[np.array([[5.0]]), np.array([[-6.0]])],
        downslope_mm=[np.array([[5.0]]), np.array([[-4.0]])],
        rate_mm_per_yr=[np.array([[150.0]]), np.array([[-120.0]])],
        residual_rms_mm=[2.0, 2.0],
        acquisition_dates=[
            frozenset({"2026-06-17", "2026-06-29"}),
            frozenset({"2026-07-11", "2026-07-23"}),
        ],
    )
    assert opposite.verdict == "no motion detected above 2 mm (2 pairs)"
    assert opposite.n_pixels_kept == 0


def test_noise_floor_rejects_pairs_that_share_a_date_or_have_unknown_dates():
    shared = slide.noise_floor(
        los_mm=[np.array([[5.0]]), np.array([[6.0]])],
        downslope_mm=[np.array([[5.0]]), np.array([[4.0]])],
        rate_mm_per_yr=[np.array([[150.0]]), np.array([[120.0]])],
        residual_rms_mm=[2.0, 2.0],
        acquisition_dates=[
            frozenset({"2026-06-17", "2026-06-29"}),
            frozenset({"2026-06-29", "2026-07-11"}),
        ],
    )
    assert shared.verdict == "no motion detected above 2 mm (2 pairs)"
    unknown = slide.noise_floor(
        los_mm=[np.array([[5.0]]), np.array([[6.0]])],
        downslope_mm=[np.array([[5.0]]), np.array([[4.0]])],
        rate_mm_per_yr=[np.array([[150.0]]), np.array([[120.0]])],
        residual_rms_mm=[2.0, 2.0],
        acquisition_dates=[frozenset(), frozenset({"2026-07-11", "2026-07-23"})],
    )
    assert unknown.n_pixels_kept == 0


def test_slice_bounds_on_a_descending_axis():
    coords = np.array([100.0, 90.0, 80.0, 70.0])
    assert slide.slice_bounds(coords, 75.0, 95.0) == (1, 3)


def test_legacy_gee_entrypoint_is_still_present():
    assert callable(slide.compute_landslide_insar_kinematics)


def test_aburra_bbox_is_read_from_config():
    bbox, key = slide.aburra_bbox_from_config(
        {"aois": {"1_aburra_medellin_bello": [-1.0, 2.0, -3.0, 4.0], "2_other": [0, 0, 1, 1]}}
    )
    assert key == "1_aburra_medellin_bello"
    assert bbox == (-1.0, 2.0, -3.0, 4.0)
    assert not hasattr(slide, "GATE_BBOX")


def test_granule_name_dates_follow_the_gate_parser():
    scene = (
        "NISAR_L2_PR_GUNW_023_047_A_005_024_4000_SH_"
        "20260617T103906_20260617T103941_20260629T103906_20260629T103940_"
        "P05023_N_F_J_001"
    )
    parsed = slide.parse_granule_name(scene)
    assert parsed["stream"] == "PR"
    assert parsed["product"] == "GUNW"
    assert parsed["polarization"] == "SH"
    assert parsed["date_1"] == "2026-06-17"
    assert parsed["date_2"] == "2026-06-29"


def test_urgent_response_copy_is_not_a_second_pair():
    rows = [
        {
            "scene_name": "pr",
            "stream": "PR",
            "track": 11,
            "frame": 85,
            "filename_reference_date": "2026-07-20",
            "filename_secondary_date": "2026-08-13",
        },
        {
            "scene_name": "ur-copy",
            "stream": "UR",
            "track": 11,
            "frame": 85,
            "filename_reference_date": "2026-07-20",
            "filename_secondary_date": "2026-08-13",
        },
        {
            "scene_name": "ur-only",
            "stream": "UR",
            "track": 47,
            "frame": 5,
            "filename_reference_date": "2026-07-23",
            "filename_secondary_date": "2026-08-16",
        },
    ]
    kept, skipped = slide._prefer_provisional(rows)
    assert [row["scene_name"] for row in kept] == ["pr", "ur-only"]
    assert skipped == ["ur-copy"]


def test_provisional_mask_keeps_the_ubyte_code():
    """D-102272 type is UByte. P05023 stores that byte in the low 8 bits."""
    codes = np.array([16777228, 11, 16777340, 111, 255, 10, 1, 12], dtype=np.uint32)
    land = slide.product_valid_land(codes)
    assert land.tolist() == [True, True, False, False, False, False, False, True]
    with_missing = np.array([12.0, np.nan])
    assert slide.product_valid_land(with_missing).tolist() == [True, False]


# --- keep-rule calibration (sign-flip null), hand-written arrays only ---------


def _dates(n):
    """n pairs with disjoint acquisition dates (all mutually independent)."""
    return [frozenset({f"d{2 * i}", f"d{2 * i + 1}"}) for i in range(n)]


def _pairs_from_signs(signs_per_pair):
    """Each pair: |LOS| = 10 mm (> RMS 1 mm); downslope and rate carry the given sign."""
    los = [np.full((1, len(s)), 10.0) for s in signs_per_pair]
    down = [np.asarray([s], dtype=float) * 5.0 for s in signs_per_pair]
    rate = [d.copy() for d in down]
    return los, down, rate, [1.0] * len(signs_per_pair), _dates(len(signs_per_pair))


def test_calibration_consistent_motion_beats_the_null():
    # Every pair says "downhill" on both pixels: real, consistent motion.
    los, down, rate, rms, dates = _pairs_from_signs([[1, 1]] * 10)
    cal = slide.calibrate_keep_rule(los, down, rate, rms, dates, draws=200, seed=7)
    assert cal.n_eligible == 2
    assert cal.observed_fraction == 1.0
    # A flip keeps the field only when at most one of the 10 signs dissents
    # (22/1024 ≈ 2.1 % of draws), so the null's 95th percentile is 0.
    assert cal.null_p95 == 0.0
    assert cal.exceeds_null is True


def test_calibration_mixed_signs_do_not_beat_the_null():
    # Pixel 0 alternates +,-,+,-…; pixel 1 goes +,+,-,-…: independent pairs disagree,
    # so the rule cancels both pixels (observed 0) and the verdict must stay null.
    signs = [[s0, s1] for s0, s1 in zip([1, -1] * 4, [1, 1, -1, -1] * 2, strict=True)]
    los, down, rate, rms, dates = _pairs_from_signs(signs)
    cal = slide.calibrate_keep_rule(los, down, rate, rms, dates, draws=200, seed=7)
    assert cal.observed_fraction == 0.0
    assert cal.exceeds_null is False


def test_calibration_is_deterministic_for_a_seed():
    los, down, rate, rms, dates = _pairs_from_signs([[1, -1]] * 8)
    a = slide.calibrate_keep_rule(los, down, rate, rms, dates, draws=50, seed=3)
    b = slide.calibrate_keep_rule(los, down, rate, rms, dates, draws=50, seed=3)
    assert a == b


def test_stable_pixel_false_positive_fraction_and_denominator():
    """Hand-computed kept fraction on the stable sample.

    Two independent pairs, residual RMS 2 mm on both.
    Pixel 0: LOS 5 and 6, downslope 5 and 4. Both exceed the RMS with the
    same sign, so the keep-rule retains it.
    Pixel 1: LOS 1.0 and 1.5, downslope 1.0 and 1.5. Both are below the
    RMS, so it is not retained.
    Pixel 2: LOS 5 and -6, downslope 5 and -4. The signs disagree, so the
    rule cancels it.
    Pixel 3: LOS 10 and 10, downslope NaN. It is outside the stable sample,
    so it is not in the denominator.
    Denominator 3, numerator 1, fraction 1/3.
    """
    los = [
        np.array([[5.0, 1.0, 5.0, 10.0]]),
        np.array([[6.0, 1.5, -6.0, 10.0]]),
    ]
    down = [
        np.array([[5.0, 1.0, 5.0, np.nan]]),
        np.array([[4.0, 1.5, -4.0, np.nan]]),
    ]
    rate = [item.copy() for item in down]
    dates = [
        frozenset({"2026-06-17", "2026-06-29"}),
        frozenset({"2026-07-11", "2026-07-23"}),
    ]
    result = slide.stable_pixel_false_positive(los, down, rate, [2.0, 2.0], dates)
    assert result.n_stable == 3
    assert result.n_kept == 1
    assert result.kept_fraction == pytest.approx(1.0 / 3.0)


def test_stable_comparison_keeps_the_null_unless_both_nulls_are_exceeded():
    """Hand-written fractions. Above the stable rate but below the sign-flip p95 stays a null."""
    near = [
        {
            "stack": "track 11",
            "observed_kept_fraction": 0.37,
            "stable_kept_fraction": 0.35,
            "null_p95": 0.50,
        }
    ]
    near_line = slide.stable_comparison_sentence(near)
    assert "below the sign-flip null" in near_line
    assert "null holds" in near_line
    assert "candidate" not in near_line
    assert slide.calibration_headline(9.105, 17, near) == (
        "no motion detected above 9.105 mm (17 pairs)"
    )
    level = [
        {
            "stack": "track 47",
            "observed_kept_fraction": 0.20,
            "stable_kept_fraction": 0.40,
            "null_p95": 0.50,
        }
    ]
    assert "consistent with the stable-pixel" in slide.stable_comparison_sentence(level)
    clear = [
        {
            "stack": "track 47",
            "observed_kept_fraction": 0.80,
            "stable_kept_fraction": 0.25,
            "null_p95": 0.50,
        }
    ]
    clear_line = slide.stable_comparison_sentence(clear)
    assert "candidate, PROVISIONAL" in clear_line
    assert "detected" not in clear_line


def test_stable_pixel_false_positive_empty_sample_is_missing():
    los = [np.array([[5.0]]), np.array([[6.0]])]
    down = [np.array([[np.nan]]), np.array([[np.nan]])]
    rate = [item.copy() for item in down]
    dates = [
        frozenset({"2026-06-17", "2026-06-29"}),
        frozenset({"2026-07-11", "2026-07-23"}),
    ]
    result = slide.stable_pixel_false_positive(los, down, rate, [2.0, 2.0], dates)
    assert result.n_stable == 0
    assert result.n_kept == 0
    assert math.isnan(result.kept_fraction)


def test_noise_floor_rule_matches_the_preregistration():
    block = {"noise_floor": {"min_pairs": 2, "require_sign_agreement": True}}
    assert "read and matched" in slide.check_noise_floor_rule(block)


@pytest.mark.parametrize(
    "block",
    [
        None,
        {},
        {"noise_floor": {"min_pairs": 3, "require_sign_agreement": True}},
        {"noise_floor": {"min_pairs": 2, "require_sign_agreement": False}},
    ],
)
def test_noise_floor_rule_rejects_other_preregistrations(block):
    with pytest.raises(ValueError):
        slide.check_noise_floor_rule(block)
