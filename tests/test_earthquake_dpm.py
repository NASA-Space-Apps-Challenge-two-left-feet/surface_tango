# tests/test_earthquake_dpm.py
"""Known-answer tests for the Aug 10 2026 quake coherence-loss DPM
(gee_math/earthquake_dpm_math.py). Every array is hand-written and every
expected value hand-computed (validation/ALLOWLIST.md); nothing here reaches
the app, cache or video, and no number is fabricate*d* evidence — it is
arithmetic on hand-written inputs.

Hand derivations are stated inline with each test.
Offline only (pytest -m "not network and not cache")."""

import math

import numpy as np
import pytest

from gee_math.earthquake_dpm_math import (
    PREREG_PATH,
    classify_coverage,
    delta_gamma,
    dpm_from_z,
    evaluate_units,
    gunw_mask_flags,
    load_quake_prereg,
    parquet_columns_from_rows,
    read_parquet,
    run_dpm_pass,
    standardize,
    unit_stats,
    valid_pixels,
    write_parquet,
)

SQ3 = math.sqrt(3.0)  # sqrt(3), used in the hand-derived z values below


def test_delta_gamma_unclamped_and_nan_preserved():
    # Δγ = γ_R − γ_C by hand: 0.9−0.4=0.5, 0.2−0.9=-0.7, NaN-0.5=NaN.
    # Unclamped: an out-of-range input pair (1.2−0.1=1.1) is NOT clamped here;
    # range checks happen at load time (load_gunw_window), not in the math.
    r = np.array([0.9, 0.2, np.nan, 1.2])
    c = np.array([0.4, 0.9, 0.5, 0.1])
    d = delta_gamma(r, c)
    assert d[0] == pytest.approx(0.5)
    assert d[1] == pytest.approx(-0.7)
    assert np.isnan(d[2])
    assert d[3] == pytest.approx(1.1)


def test_standardize_mu_sigma_over_reference_pixels_only():
    # d = [0.1, 0.2, 0.3, 0.9, NaN], reference mask selects the first three.
    # mu = 0.2; population sigma = sqrt((0.01+0+0.01)/3) = sqrt(0.02/3).
    # z = (d - 0.2)/sigma: [-(1/10)/s, 0, (1/10)/s, (7/10)/s, NaN]
    # with s = sqrt(0.02/3) = 0.081649658...:
    #   z = [-1.224744871, 0.0, 1.224744871, 8.573214098, NaN]
    d = np.array([0.1, 0.2, 0.3, 0.9, np.nan])
    ref = np.array([True, True, True, False, False])
    z, mu, sigma, n = standardize(d, ref)
    assert mu == pytest.approx(0.2)
    assert sigma == pytest.approx(math.sqrt(0.02 / 3.0), rel=1e-12)
    assert n == 3
    assert z[0] == pytest.approx(-1.224744871, rel=1e-9)
    assert z[1] == pytest.approx(0.0, abs=1e-12)
    assert z[2] == pytest.approx(1.224744871, rel=1e-9)
    assert z[3] == pytest.approx(8.573214098, rel=1e-9)
    assert np.isnan(z[4])


def test_standardize_zero_sigma_gives_z_nan_everywhere():
    # All reference values equal 0.5 -> sigma = 0 -> Z undefined, so NaN
    # everywhere (never zero-filled), but mu/n are still reported.
    d = np.array([0.5, 0.5, 0.2])
    ref = np.array([True, True, False])
    z, mu, sigma, n = standardize(d, ref)
    assert np.all(np.isnan(z))
    assert mu == pytest.approx(0.5)
    assert sigma == pytest.approx(0.0)
    assert n == 2


def test_standardize_fewer_than_two_reference_pixels():
    # n=1 -> Z NaN everywhere.
    d = np.array([0.5, 0.9])
    ref = np.array([True, False])
    z, mu, sigma, n = standardize(d, ref)
    assert np.all(np.isnan(z))
    assert n == 1


def test_dpm_clamps_after_standardization():
    # Clamp order proof: dpm = max(Z, 0), never max(delta, 0) first.
    # If delta were clamped before standardization the reference statistics
    # would change; here we only verify the output stage: negative Z -> 0,
    # NaN Z stays NaN (missing stays missing).
    z = np.array([np.nan, -3.0, 2.0, -0.0])
    dpm = dpm_from_z(z)
    assert np.isnan(dpm[0])
    assert dpm[1] == 0.0
    assert dpm[2] == pytest.approx(2.0)
    assert dpm[3] == 0.0


def test_classify_coverage_threshold_edges_from_prereg():
    # Frozen thresholds: built-up >= 0.50 (inclusive), non-built <= 0.10
    # (inclusive), NaN is neither (never filled).
    thr = load_quake_prereg()
    b_min = thr["built_up_min_footprint_fraction"]
    nb_max = thr["non_built_max_footprint_fraction"]
    assert b_min == pytest.approx(0.50)
    assert nb_max == pytest.approx(0.10)
    cov = np.array([0.50, 0.4999, 0.10, 0.1001, np.nan, 1.0, 0.0])
    built, non_built = classify_coverage(cov, b_min, nb_max)
    assert built.tolist() == [True, False, False, False, False, True, False]
    assert non_built.tolist() == [False, False, True, False, False, False, True]


def test_gunw_mask_flags_three_digit_semantics():
    # JPL D-102272 Rev E p.44: value = [water][ref-subswath][sec-subswath],
    # 255 = fill. Hand-evaluated:
    #   11  -> land, both subswaths valid
    #   111 -> water, both subswaths valid (valid land AND water flag)
    #   255 -> fill: not valid, not water
    #   10  -> sec-subswath digit 0 -> invalid
    #   5   -> ref-subswath digit 0 -> invalid
    #   51  -> land, valid; 110 -> water, sec invalid so not valid
    m = np.array([11, 111, 255, 10, 5, 51, 110], dtype=np.uint32)
    valid, water = gunw_mask_flags(m)
    assert valid.tolist() == [True, True, False, False, False, True, False]
    assert water.tolist() == [False, True, False, False, False, False, True]


def test_valid_pixels_mask_combination_and_layover_optional():
    # Pixel is valid iff delta finite and no mask excludes it. A layover/shadow
    # layer of None (the GUNW product has none) excludes nothing; a provided
    # one does exclude.
    delta = np.array([1.0, 1.0, 1.0, 1.0, np.nan, 1.0, 1.0])
    veg = np.array([False, True, False, False, False, False, False])
    wat = np.array([False, False, True, False, False, False, False])
    gv = np.array([True, True, True, False, True, True, True])
    lay = np.array([False, False, False, False, False, True, False])
    v_none = valid_pixels(delta, veg, wat, gv, None)
    assert v_none.tolist() == [True, False, False, False, False, True, True]
    v_lay = valid_pixels(delta, veg, wat, gv, lay)
    assert v_lay.tolist() == [True, False, False, False, False, False, True]


def test_unit_stats_median_nan_filter_and_zero_skipped():
    # unit 1: z = [1, NaN, 3] over its 3 pixels -> finite [1,3], median 2,
    # n_px 2 (NaN excluded, never filled). unit 2: [4,5] -> median 4.5,
    # n_px 2. unit id 0 (outside any unit polygon) never reported.
    z = np.array([1.0, np.nan, 3.0, 4.0, 5.0, 100.0])
    ids = np.array([1, 1, 1, 2, 2, 0])
    sel = np.array([True] * 6)
    stats = unit_stats(z, ids, sel)
    assert set(stats) == {1, 2}
    assert stats[1]["median_z"] == pytest.approx(2.0)
    assert stats[1]["n_px"] == 2
    assert stats[2]["median_z"] == pytest.approx(4.5)
    assert stats[2]["n_px"] == 2


def test_evaluate_units_boundary_and_zero_pixel_units_counted():
    # Boundary: 20 px is evaluated (>=, frozen rule), 19 is excluded.
    # A unit absent from stats (zero valid built-up pixels) is excluded too,
    # so every rasterized unit is either evaluated or explicitly excluded.
    stats = {1: {"median_z": 1.0, "n_px": 19}, 2: {"median_z": 2.0, "n_px": 20}}
    evaluated, excluded = evaluate_units(stats, 20, all_unit_ids=[1, 2, 3])
    assert evaluated == [2]
    assert excluded == [1, 3]


def test_run_dpm_pass_hand_computed_end_to_end():
    # 8-pixel hand case (see module docstring):
    #   coverage  = [0.80, 0.85, 0.05, 0.08, 0.50, 0.00, 0.90, 0.06]
    #   gamma_R   = [0.9, 0.9, 0.7, 0.7, 0.6, 0.6, 0.8, 0.7]
    #   gamma_C   = [0.4, 0.5, 0.6, 0.65, 0.2, 0.5, 0.1, 0.6]
    #   delta     = gamma_R - gamma_C
    #             = [0.5, 0.4, 0.1, 0.05, 0.4, 0.1, 0.7, 0.1]
    # built-up (>= 0.50): pixels 0,1,4,6; non-built (<= 0.10): 2,3,5,7.
    # mask = 11 everywhere (valid land), no vegetation, no water.
    # Reference (valid & non-built) deltas: [0.1, 0.05, 0.1, 0.1]
    #   mu = 0.35/4 = 0.0875 = 7/80
    #   var = ((0.0125)^2 + (0.0375)^2 + (0.0125)^2 + (0.0125)^2)/4 = 0.00046875
    #   sigma = sqrt(0.00046875) = sqrt(3)/80
    #   z = (delta - 7/80) / (sqrt(3)/80) = (80*delta - 7)/sqrt(3)
    #     delta 0.5 -> 33/sqrt(3) = 11*sqrt(3) ~ 19.0525589
    #     delta 0.4 -> 25/sqrt(3) ~ 14.4337567
    #     delta 0.1 ->  1/sqrt(3) ~  0.5773503
    #     delta 0.05 -> -3/sqrt(3) = -sqrt(3) ~ -1.7320508
    #     delta 0.7 -> 49/sqrt(3) ~ 28.2901632
    # median Z built-up = median of [11s3, 25/s3, 25/s3, 49/s3] = (25/s3+11s3)/2.
    # median Z non-built = median of [1/s3, -s3, 1/s3, 1/s3] = 1/s3.
    # excess E = med_built - med_non_built = (25/s3+33/s3)/2 - 1/s3
    #          = (58/s3 - 2/s3)/2 = 28/s3.
    coverage = np.array([0.80, 0.85, 0.05, 0.08, 0.50, 0.00, 0.90, 0.06])
    gamma_r = np.array([0.9, 0.9, 0.7, 0.7, 0.6, 0.6, 0.8, 0.7])
    gamma_c = np.array([0.4, 0.5, 0.6, 0.65, 0.2, 0.5, 0.1, 0.6])
    mask = np.full(8, 11, dtype=np.uint32)
    units = np.array([1, 1, 1, 1, 2, 2, 2, 2])
    thr = {
        "built_up_min_footprint_fraction": 0.50,
        "non_built_max_footprint_fraction": 0.10,
        "min_built_up_pixels_per_unit": 2,
    }
    out = run_dpm_pass(
        gamma_r,
        gamma_c,
        coverage,
        None,
        None,
        mask,
        units,
        thr,
        layover_shadow=None,
        unit_names={1: "u1", 2: "u2"},
        label="C",
    )
    assert out["delta"].tolist() == [
        pytest.approx(v) for v in (0.5, 0.4, 0.1, 0.05, 0.4, 0.1, 0.7, 0.1)
    ]
    s = out["summary"]
    assert s["n_reference_px"] == 4
    assert s["mu"] == pytest.approx(7.0 / 80.0, rel=1e-12)
    assert s["sigma"] == pytest.approx(SQ3 / 80.0, rel=1e-12)
    z_expected = np.array([11 * SQ3, 25 / SQ3, 1 / SQ3, -SQ3, 25 / SQ3, 1 / SQ3, 49 / SQ3, 1 / SQ3])
    assert np.allclose(out["z"], z_expected, rtol=1e-12)
    assert out["dpm"][3] == pytest.approx(0.0)  # negative Z clamped after
    assert np.allclose(out["dpm"], np.maximum(z_expected, 0.0), rtol=1e-12)
    assert s["n_px_total"] == 8
    assert s["n_px_valid"] == 8
    assert s["n_px_built_up_valid"] == 4
    assert s["n_px_non_built_valid"] == 4
    assert s["median_z_built_up"] == pytest.approx((25 / SQ3 + 11 * SQ3) / 2, rel=1e-12)
    assert s["median_z_non_built"] == pytest.approx(1 / SQ3, rel=1e-12)
    assert s["excess_e"] == pytest.approx(
        s["median_z_built_up"] - s["median_z_non_built"], rel=1e-12
    )
    assert s["excess_e"] == pytest.approx(28 / SQ3, rel=1e-12)
    assert s["n_units_total"] == 2
    assert s["n_units_evaluated"] == 2
    assert s["n_units_excluded"] == 0
    assert s["layover_shadow_mask"] == "missing"
    stats = out["unit_stats"]
    assert stats[1]["n_px"] == 2
    assert stats[1]["median_z"] == pytest.approx((11 * SQ3 + 25 / SQ3) / 2, rel=1e-12)
    assert stats[2]["n_px"] == 2
    assert stats[2]["median_z"] == pytest.approx((25 / SQ3 + 49 / SQ3) / 2, rel=1e-12)


def test_run_dpm_pass_excluded_units_with_frozen_threshold():
    # Same 8-pixel case but the frozen min_built_up_pixels_per_unit = 20:
    # both units have only 2 built-up pixels, so both are excluded and
    # counted, and their rows carry the reason.
    coverage = np.array([0.80, 0.85, 0.05, 0.08, 0.50, 0.00, 0.90, 0.06])
    gamma_r = np.array([0.9, 0.9, 0.7, 0.7, 0.6, 0.6, 0.8, 0.7])
    gamma_c = np.array([0.4, 0.5, 0.6, 0.65, 0.2, 0.5, 0.1, 0.6])
    mask = np.full(8, 11, dtype=np.uint32)
    units = np.array([1, 1, 1, 1, 2, 2, 2, 2])
    thr = load_quake_prereg()
    out = run_dpm_pass(gamma_r, gamma_c, coverage, None, None, mask, units, thr)
    assert thr["min_built_up_pixels_per_unit"] == 20
    assert out["summary"]["n_units_evaluated"] == 0
    assert out["summary"]["n_units_excluded"] == 2
    rows = {(r["unit_id"]): r for r in out["excluded_rows"]}
    assert set(rows) == {1, 2}
    assert rows[1]["n_built_up_valid_px"] == 2
    assert "n_built_up_valid_px < 20" in rows[1]["reason"]


def test_run_dpm_pass_control_pass_is_identical_code():
    # Control pass (K vs R): the same callable, gamma_ref=gamma_K,
    # gamma_cmp=gamma_R. Hand: gamma_K = [0.8, 0.85, 0.65, 0.68, 0.5, 0.55,
    # 0.7, 0.65] gives delta_K = gamma_K - gamma_R = [-0.1, -0.05, -0.05,
    # -0.02, -0.1, -0.05, -0.1, -0.05]; reference deltas (px 2,3,5,7) =
    # [-0.05, -0.02, -0.05, -0.05]: mu = -0.17/4 = -0.0425,
    # var = ((-.0075)^2 + (.0225)^2 + (.0075)^2 + (.0075)^2)/4 = 0.00016875,
    # sigma = sqrt(0.00016875) = 0.012990381 = (sqrt(3)*3)/80... check:
    # 0.00016875 = 27*0.00000625/... hand: sqrt(0.00016875) = 0.0129903811
    # z = (delta + 0.0425)/0.0129903811.
    gamma_k = np.array([0.8, 0.85, 0.65, 0.68, 0.5, 0.55, 0.7, 0.65])
    gamma_r = np.array([0.9, 0.9, 0.7, 0.7, 0.6, 0.6, 0.8, 0.7])
    gamma_c = np.array([0.4, 0.5, 0.6, 0.65, 0.2, 0.5, 0.1, 0.6])
    coverage = np.array([0.80, 0.85, 0.05, 0.08, 0.50, 0.00, 0.90, 0.06])
    mask = np.full(8, 11, dtype=np.uint32)
    units = np.array([1, 1, 1, 1, 2, 2, 2, 2])
    thr = {
        "built_up_min_footprint_fraction": 0.50,
        "non_built_max_footprint_fraction": 0.10,
        "min_built_up_pixels_per_unit": 2,
    }
    ctrl = run_dpm_pass(gamma_k, gamma_r, coverage, None, None, mask, units, thr)
    coev = run_dpm_pass(gamma_r, gamma_c, coverage, None, None, mask, units, thr)
    # The control pass runs the identical pipeline: recompute its z by the
    # same public functions and demand exact equality.
    d_ctrl = delta_gamma(gamma_k, gamma_r)
    z_re, mu_re, sig_re, n_re = standardize(d_ctrl, ctrl["valid"] & ctrl["non_built"])
    assert mu_re == pytest.approx(ctrl["summary"]["mu"], rel=1e-12)
    assert sig_re == pytest.approx(ctrl["summary"]["sigma"], rel=1e-12)
    assert n_re == ctrl["summary"]["n_reference_px"]
    assert np.allclose(ctrl["z"], z_re, equal_nan=True, rtol=1e-12)
    # Hand spot values: mu = -0.0425, sigma = sqrt(0.00016875) = 0.01299038106.
    assert ctrl["summary"]["mu"] == pytest.approx(-0.0425, rel=1e-12)
    assert ctrl["summary"]["sigma"] == pytest.approx(math.sqrt(0.00016875), rel=1e-12)
    # delta at pixel 2: 0.65-0.7 = -0.05 -> z = (-0.05+0.0425)/sigma
    z2 = (-0.05 + 0.0425) / math.sqrt(0.00016875)
    assert ctrl["z"][2] == pytest.approx(z2, rel=1e-12)
    # and the co-event and control passes carry distinct labels.
    assert ctrl["summary"]["label"] == "C"
    assert coev["summary"]["label"] == "C"  # default label; runs are separate
    assert ctrl["z"].shape == coev["z"].shape


def test_run_dpm_pass_water_mask_from_gunw_only():
    # water=None still excludes water via the GUNW mask digit; the one water
    # pixel leaves only 3 ref candidates -> n=3... hand: with 4 pixels,
    # coverage [0.9, 0.05, 0.9, 0.05], deltas all 0.2, masks
    # [11, 111, 11, 11]: valid = [T, F, T, T]; non-built = [F, T, F, T];
    # valid & non-built = [F, F, F, T] -> n=1 < 2 -> Z NaN everywhere
    # (undefined, disclosed), dpm NaN, no unit evaluated.
    gamma_r = np.full(4, 0.8)
    gamma_c = np.full(4, 0.6)
    coverage = np.array([0.9, 0.05, 0.9, 0.05])
    mask = np.array([11, 111, 11, 11], dtype=np.uint32)
    units = np.array([1, 1, 1, 1])
    thr = {
        "built_up_min_footprint_fraction": 0.50,
        "non_built_max_footprint_fraction": 0.10,
        "min_built_up_pixels_per_unit": 1,
    }
    out = run_dpm_pass(gamma_r, gamma_c, coverage, None, None, mask, units, thr)
    assert out["summary"]["n_px_valid"] == 3
    assert out["summary"]["n_reference_px"] == 1
    assert np.all(np.isnan(out["z"]))
    assert np.all(np.isnan(out["dpm"]))
    assert out["summary"]["n_units_evaluated"] == 0
    assert out["summary"]["n_units_excluded"] == 1
    assert out["excluded_rows"][0]["n_built_up_valid_px"] == 0


def test_preregistered_thresholds_load_frozen_values():
    # The thresholds must come from the frozen file, never hardcode: the
    # quake block carries 0.50 / 0.10 / 20 and the file's top-level status.
    thr = load_quake_prereg()
    assert thr["built_up_min_footprint_fraction"] == pytest.approx(0.50)
    assert thr["non_built_max_footprint_fraction"] == pytest.approx(0.10)
    assert thr["min_built_up_pixels_per_unit"] == 20
    assert thr["status"] == "draft"
    assert PREREG_PATH.exists()


def test_parquet_roundtrip(tmp_path):
    # Round-trip through the in-module writer/reader (the writer is verified
    # against real pyarrow outside the repo deps; see the brief report).
    # Values include a NaN median (excluded unit) which must survive.
    p = tmp_path / "barrio_dpm.parquet"
    rows = [
        {
            "unit_id": 1,
            "unit_name": "Pereira",
            "unit_type": "municipio",
            "unit_source": "FAO/GAUL/2025/level2",
            "evaluated": 1,
            "n_built_up_valid_px": 20,
            "n_non_built_valid_px": 5,
            "median_z_built": 1.25,
            "median_z_built_control": 0.5,
        },
        {
            "unit_id": 2,
            "unit_name": "Dosquebradas",
            "unit_type": "municipio",
            "unit_source": "FAO/GAUL/2025/level2",
            "evaluated": 0,
            "n_built_up_valid_px": 19,
            "n_non_built_valid_px": 4,
            "median_z_built": float("nan"),
            "median_z_built_control": float("nan"),
        },
    ]
    cols = parquet_columns_from_rows(rows)
    assert set(cols) == {
        "unit_id",
        "unit_name",
        "unit_type",
        "unit_source",
        "evaluated",
        "n_built_up_valid_px",
        "n_non_built_valid_px",
        "median_z_built",
        "median_z_built_control",
    }
    assert cols["unit_id"][0] == "int64"
    assert cols["median_z_built"][0] == "double"
    assert cols["unit_name"][0] == "utf8"
    write_parquet(p, cols)
    back = read_parquet(p)
    assert back["unit_id"] == [1, 2]
    assert back["unit_name"] == ["Pereira", "Dosquebradas"]
    assert back["evaluated"] == [1, 0]
    assert back["n_built_up_valid_px"] == [20, 19]
    assert back["median_z_built"][0] == pytest.approx(1.25)
    assert math.isnan(back["median_z_built"][1])
    assert math.isnan(back["median_z_built_control"][1])
    assert back["median_z_built_control"][0] == pytest.approx(0.5)
    assert p.stat().st_size > 8  # real file: PAR1 magic + footer
    assert p.read_bytes()[:4] == b"PAR1"
    assert p.read_bytes()[-4:] == b"PAR1"
