"""Known-answer tests for terrain derivatives and photogrammetric lengths.

The elevation grid, control points, and distances are hand-written.
Expected numbers are the arithmetic in the comments, not fitted outputs.
"""

import math

import numpy as np

from gee_math.landslide_geomorphology import (
    epoch_path_m,
    gully_head_retreat_m_per_yr,
    horn_derivatives,
    planimetric_displacement_m,
    relative_relief_m,
    sign_agreement,
    slope_summary,
    translation_coregistration,
)

# 3x3 elevation, metres. Axis 0 north, axis 1 east. dx = dy = 10 m.
# a b c = 10 10 10
# d e f = 10 20 30
# g h i = 10 20 30
# p = ((c+2f+i) - (a+2d+g)) / 80 = (100-40)/80 = 0.75
# q = ((a+2b+c) - (g+2h+i)) / 80 = (40-80)/80 = -0.5
# slope = atan(hypot(0.75, -0.5)) in degrees = 42.03111377419729
# aspect = atan2(-p, -q) in degrees, mod 360 = 303.69006752597977
# r = 0, t = -0.1, s = 0.05
# profile curvature = 0.031523877038014105 per metre
# plan curvature = 0.025601547518087502 per metre
ELEVATION = np.array(
    [
        [10.0, 10.0, 10.0],
        [10.0, 20.0, 30.0],
        [10.0, 20.0, 30.0],
    ]
)
SLOPE_DEG = 42.03111377419729
ASPECT_DEG = 303.69006752597977
PROFILE_PER_M = 0.031523877038014105
PLAN_PER_M = 0.025601547518087502


def test_slope_summary_percentiles_ignore_missing_samples():
    # Finite samples 0, 10, 20, 30. Linear percentile index is (n-1)*p.
    # Median (n-1)/2 = 1.5 → 15. p05 index 0.15 → 1.5. p95 index 2.85 → 28.5.
    summary = slope_summary(np.array([0.0, 10.0, np.nan, 20.0, 30.0]))
    assert summary["n_pixels"] == 5
    assert summary["n_finite"] == 4
    assert summary["median_deg"] == pytest_approx(15.0)
    assert summary["p05_deg"] == pytest_approx(1.5)
    assert summary["p95_deg"] == pytest_approx(28.5)
    empty = slope_summary(np.array([np.nan, np.nan]))
    assert empty["n_finite"] == 0
    assert empty["median_deg"] is None


def test_horn_derivatives_match_the_hand_partials_and_keep_edges_missing():
    derived = horn_derivatives(ELEVATION, 10.0, 10.0)
    assert derived["slope_deg"][1, 1] == pytest_approx(SLOPE_DEG)
    assert derived["aspect_deg"][1, 1] == pytest_approx(ASPECT_DEG)
    assert derived["profile_curvature_per_m"][1, 1] == pytest_approx(PROFILE_PER_M)
    assert derived["plan_curvature_per_m"][1, 1] == pytest_approx(PLAN_PER_M)
    assert math.isnan(derived["slope_deg"][0, 0])
    assert math.isnan(derived["aspect_deg"][0, 2])
    assert relative_relief_m(ELEVATION) == 20.0


def test_missing_neighbor_or_cell_size_stays_missing():
    broken = ELEVATION.copy()
    broken[0, 0] = np.nan
    derived = horn_derivatives(broken, 10.0, 10.0)
    assert math.isnan(derived["slope_deg"][1, 1])
    invalid = horn_derivatives(ELEVATION, 0.0, 10.0)
    assert np.isnan(invalid["slope_deg"]).all()
    flat = horn_derivatives(np.full((3, 3), 5.0), 10.0, 10.0)
    assert flat["slope_deg"][1, 1] == 0.0
    assert math.isnan(flat["aspect_deg"][1, 1])
    assert relative_relief_m(np.array([np.nan, 4.0])) is None
    assert relative_relief_m(np.array([4.0, 4.0])) == 0.0


def test_photogrammetric_lengths_and_coregistration():
    # (0, 0) → (3, 4) is 5 m. A second equal step makes a 10 m path.
    assert planimetric_displacement_m((0.0, 0.0), (3.0, 4.0)) == 5.0
    assert planimetric_displacement_m((0.0, 0.0), (None, 4.0)) is None
    path = epoch_path_m([(0.0, 0.0), (3.0, 4.0), (6.0, 8.0)])
    assert path["step_m"] == [5.0, 5.0]
    assert path["path_m"] == 10.0
    gap = epoch_path_m([(0.0, 0.0), None, (6.0, 8.0)])
    assert gap["path_m"] is None
    # Shift mean of (1, 2) and (2, 2) is (1.5, 2). Residuals ±0.5 m east. RMSE 0.5 m.
    fit = translation_coregistration([(0.0, 0.0), (10.0, 0.0)], [(1.0, 2.0), (12.0, 2.0)])
    assert fit["shift_east_m"] == 1.5
    assert fit["shift_north_m"] == 2.0
    assert fit["rmse_m"] == 0.5
    assert fit["n_points"] == 2
    assert translation_coregistration([(None, 0.0)], [(1.0, 2.0)])["rmse_m"] is None
    # 10 m over 365.25 days is 10 m/yr. Twice the interval is 5 m/yr.
    assert gully_head_retreat_m_per_yr(10.0, 365.25) == 10.0
    assert gully_head_retreat_m_per_yr(10.0, 730.5) == 5.0
    assert gully_head_retreat_m_per_yr(10.0, 0.0) is None
    assert gully_head_retreat_m_per_yr(None, 365.25) is None


def test_sign_agreement_is_undefined_at_zero_or_when_either_side_is_missing():
    assert sign_agreement(1.0, 2.0) == "agree"
    assert sign_agreement(1.0, -1.0) == "disagree"
    assert sign_agreement(0.0, 1.0) is None
    assert sign_agreement(None, 1.0) is None


def pytest_approx(value):
    import pytest

    return pytest.approx(value)
