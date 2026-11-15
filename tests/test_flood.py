"""Known-answer tests for La Mojana dual-pol flood classes.

Arrays here are hand-written. Expected counts are hand-computed from those
arrays and from thresholds loaded through yaml.safe_load. They never enter
the cache or the report of a real run.
"""

from pathlib import Path

import numpy as np
import rasterio
import yaml

from gee_math.flood_polarimetric_math import (
    AnalysisGrid,
    DateCube,
    DateStats,
    FloodThresholds,
    GranuleRef,
    ReportContext,
    StackChoice,
    absolute_water_counts,
    change_class_counts,
    choose_baseline,
    classify_stack,
    compare_s1,
    db_to_power,
    invalid_gcov_pixels,
    load_flood_thresholds,
    mosaic_linear,
    parse_scene_name,
    power_to_db,
    render_report,
    resample_power_mean,
    safe_error,
    select_stack,
    water_raster,
    write_class_geotiff,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "preregistered.yaml"

DUAL = (
    "NISAR_L2_PR_GCOV_004_004_A_018_4005_DHDH_A_20251029T111130_20251029T111153_P05023_N_P_J_001.h5"
)
SINGLE = (
    "NISAR_L2_PR_GCOV_010_160_A_036_7700_SHNA_A_20260120T070339_20260120T070415_X05010_N_P_J_001.h5"
)


def _repo_thresholds() -> FloodThresholds:
    return load_flood_thresholds(CONFIG)


def test_power_to_db_exact_and_missing_stays_missing():
    db = power_to_db(np.array([0.01, 0.1, 0.0, -1.0, np.nan]))
    assert db[0] == -20.0
    assert db[1] == -10.0
    assert np.isnan(db[2])
    assert np.isnan(db[3])
    assert np.isnan(db[4])
    assert db_to_power(np.array([-20.0]))[0] == 0.01


def test_mosaic_means_linear_power_and_skips_missing():
    merged = mosaic_linear(
        [
            np.array([1.0, np.nan, 4.0]),
            np.array([3.0, 2.0, np.nan]),
        ]
    )
    assert np.allclose(merged, [2.0, 2.0, 4.0])
    empty = mosaic_linear([np.array([np.nan, np.nan])])
    assert np.isnan(empty).all()


def test_open_water_respects_hand_gate_and_exact_threshold():
    thr = _repo_thresholds()
    # Pixel 0 is just below the loaded cut and inside HAND.
    # Pixel 1 equals the cut (not strictly below) and is valid.
    # Pixel 2 is darker but HAND equals the gate, so it is outside the denominator.
    # Pixel 3 has missing HH and must not enter the denominator.
    hh = np.array(
        [
            thr.open_water_abs_hh_db - 0.5,
            thr.open_water_abs_hh_db,
            thr.open_water_abs_hh_db - 1.0,
            np.nan,
        ]
    )
    hand = np.array(
        [
            thr.hand_max_m - 1.0,
            thr.hand_max_m - 1.0,
            thr.hand_max_m,
            thr.hand_max_m - 1.0,
        ]
    )
    assert absolute_water_counts(hh, hand, thr) == (1, 2)
    raster = water_raster(hh, hand, thr)
    assert list(raster) == [1, 0, -1, -1]


def test_repo_config_is_what_the_loader_returns():
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    thr = _repo_thresholds()
    flood = raw["flood"]
    assert thr.open_water_abs_hh_db == flood["open_water_abs_hh_db"]
    assert thr.class1_delta_hh_db_max == flood["class1_delta_hh_db_max"]
    assert thr.class2_delta_hh_db_min == flood["class2_delta_hh_db_min"]
    assert thr.class2_delta_hv_hh_db_abs_max == flood["class2_delta_hv_hh_db_abs_max"]
    assert thr.hand_max_m == flood["hand_max_m"]
    assert thr.no_baseline_relative_gap == flood["no_baseline_relative_gap"]
    assert thr.db_step == flood["sensitivity"]["db_step"]
    assert thr.hand_sensitivity_m == tuple(flood["sensitivity"]["hand_m"])
    assert thr.uncalibrated == tuple(raw["labels"]["uncalibrated"])


def test_thresholds_come_from_the_yaml_file(tmp_path: Path):
    path = tmp_path / "flood.yaml"
    path.write_text(
        """
flood:
  open_water_abs_hh_db: -5.0
  class1_delta_hh_db_max: -1.0
  class2_delta_hh_db_min: 1.0
  class2_delta_hv_hh_db_abs_max: 0.5
  hand_max_m: 9
  no_baseline_relative_gap: 0.20
  sensitivity: {db_step: 1.0, hand_m: [12, 18, 24]}
labels: {uncalibrated: [open_water_abs_hh_db]}
""",
        encoding="utf-8",
    )
    loaded = load_flood_thresholds(path)
    hh = np.array([[-5.1, -4.9]])
    hand = np.array([[8.0, 8.0]])
    assert absolute_water_counts(hh, hand, loaded) == (1, 2)
    # The same pixels are not water under the repository thresholds.
    assert absolute_water_counts(hh, hand, _repo_thresholds()) == (0, 2)


def test_class_boundaries_use_loaded_thresholds():
    thr = _repo_thresholds()
    hand_in = np.array([thr.hand_max_m - 1.0])
    hand_edge = np.array([thr.hand_max_m])
    ref_hh = np.array([0.0])
    ref_hv = np.array([0.0])

    at_class1 = np.array([thr.class1_delta_hh_db_max])
    below_class1 = np.array([thr.class1_delta_hh_db_max - 1.0])
    at = change_class_counts(at_class1, ref_hv, ref_hh, ref_hv, hand_in, thr)
    below = change_class_counts(below_class1, ref_hv, ref_hh, ref_hv, hand_in, thr)
    assert at.n_class1 == 0 and at.n_valid_class1 == 1
    assert below.n_class1 == 1

    delta = thr.class2_delta_hh_db_min + 1.0
    inside = change_class_counts(
        np.array([delta]),
        np.array([delta]),
        ref_hh,
        ref_hv,
        hand_in,
        thr,
    )
    at_hh = change_class_counts(
        np.array([thr.class2_delta_hh_db_min]),
        np.array([thr.class2_delta_hh_db_min]),
        ref_hh,
        ref_hv,
        hand_in,
        thr,
    )
    at_ratio = change_class_counts(
        np.array([delta]),
        np.array([delta + thr.class2_delta_hv_hh_db_abs_max]),
        ref_hh,
        ref_hv,
        hand_in,
        thr,
    )
    under_ratio = change_class_counts(
        np.array([delta]),
        np.array([delta + thr.class2_delta_hv_hh_db_abs_max - 1.0]),
        ref_hh,
        ref_hv,
        hand_in,
        thr,
    )
    outside_hand = change_class_counts(
        np.array([delta]),
        np.array([delta]),
        ref_hh,
        ref_hv,
        hand_edge,
        thr,
    )
    assert inside.n_class2 == 1 and inside.n_class1 == 0
    assert at_hh.n_class2 == 0
    assert at_ratio.n_class2 == 0
    assert under_ratio.n_class2 == 1
    assert outside_hand.n_valid_class1 == 0 and outside_hand.n_class2 == 0


def test_baseline_accepts_exact_gap_and_rejects_a_smaller_one():
    # 4/5 and 5/5 → drop = 1/5, which is the configured 0.20, so the baseline stands.
    exact = choose_baseline(
        [
            DateStats("2026-06-17", ("dry",), 4, 5),
            DateStats("2026-11-14", ("wet",), 5, 5),
        ],
        _repo_thresholds().no_baseline_relative_gap,
    )
    assert exact.accepted
    assert exact.reference_date == "2026-06-17"
    assert exact.gap == "1/5"

    # 81/100 and 100/100 → drop = 19/100, which is below 0.20.
    under = choose_baseline(
        [
            DateStats("2026-06-17", ("dry",), 81, 100),
            DateStats("2026-11-14", ("wet",), 100, 100),
        ],
        0.20,
    )
    assert not under.accepted
    assert under.reason == "relative_gap"
    assert under.reference_date is None
    assert under.gap == "19/100"


def test_f_wet_zero_and_no_valid_dates_select_no_baseline():
    zero = choose_baseline(
        [
            DateStats("2026-06-17", ("a",), 0, 10),
            DateStats("2026-07-01", ("b",), 0, 8),
        ],
        0.20,
    )
    assert not zero.accepted
    assert zero.reason == "f_wet_zero"
    assert zero.gap is None
    assert zero.reference_date is None

    none = choose_baseline([DateStats("2026-06-17", ("a",), 0, 0)], 0.20)
    assert none.reason == "no_valid_dates"
    assert none.gap is None


def test_safe_error_strips_urls_and_tokens(monkeypatch):
    monkeypatch.setenv("EARTHDATA_TOKEN", "abcdefghijklmnop")
    text = safe_error(RuntimeError("get https://example.test/a.h5 failed token=abcdefghijklmnop"))
    assert "https://" not in text
    assert "abcdefghijklmnop" not in text
    assert "<url>" in text
    assert "<redacted>" in text


def test_product_flags_stay_missing():
    """Mask 0/255, a zero look count, and a nonzero exception are not data."""
    power_shape = (1, 4)
    looks = np.array([[4.0, 0.0, 4.0, 4.0]])
    mask = np.array([[1, 1, 0, 255]], dtype=np.uint8)
    exception = np.array([[0, 0, 0, 0]], dtype=np.uint8)
    invalid, note = invalid_gcov_pixels(power_shape, looks, mask, exception)
    assert list(invalid[0]) == [False, True, True, True]
    assert "mask values 0 and 255" in note
    slipped = np.array([[2, 0, 0, 0]], dtype=np.uint8)
    kept = np.array([[1, 1, 1, 1]], dtype=np.uint8)
    four = np.array([[4.0, 4.0, 4.0, 4.0]])
    invalid_slip, _note = invalid_gcov_pixels(power_shape, four, kept, slipped)
    assert list(invalid_slip[0]) == [True, False, False, False]


def test_driest_tie_takes_the_earliest_date():
    decision = choose_baseline(
        [
            DateStats("2026-08-01", ("b",), 1, 4),
            DateStats("2026-07-01", ("a",), 1, 4),
            DateStats("2026-09-01", ("c",), 4, 4),
        ],
        0.20,
    )
    assert decision.accepted
    assert decision.reference_date == "2026-07-01"
    assert decision.dry_dates == ("2026-07-01", "2026-08-01")
    assert decision.wet_dates == ("2026-09-01",)


def _cube(date: str, granule: str, hh_db: list[float], hv_db: list[float]) -> DateCube:
    return DateCube(
        date=date,
        granule_ids=(granule,),
        hh_linear=db_to_power(np.array([hh_db], dtype=np.float64)),
        hv_linear=db_to_power(np.array([hv_db], dtype=np.float64)),
    )


def test_classify_stack_both_classes_and_sensitivity_counts():
    """Six pixels. Counts below were computed by hand from these dB values.

    hand:                 10    10    15    10    10    20
    dry HH:              -20   -10   -10   -12   -10   -10
    wet HH:              -21 -18.5   -16  -8.5  -7.5  -5.5
    wet HV − wet HH:       0     0     0   0.8   0.2   0.3
    dry HV − dry HH:       0     0     0     0     0     0

    Nominal gate HAND < 18, so pixel 5 is outside. Valid denominator = 5.
    Dry water (HH < -18): pixel 0 only → 1/5.
    Wet water: pixels 0 and 1 → 2/5.
    Gap = (2/5 − 1/5) / (2/5) = 1/2, so the dry date is the baseline.

    ΔHH wet−dry: -1, -8.5, -6, +3.5, +2.5, +4.5.
    Class 1 is ΔHH < -5.5: pixels 1 and 2.
    Class 2 is ΔHH > 3 and |Δratio| < 1.5: pixel 3 only.
    """
    thr = _repo_thresholds()
    hand = np.array([[10.0, 10.0, 15.0, 10.0, 10.0, 20.0]])
    # Pixel 1 stays inside HAND 12. Pixel 2 (HAND 15) drops. Pixel 5 is 20.
    dry = _cube(
        "2026-06-20",
        "NISAR_DRY",
        [-20.0, -10.0, -10.0, -12.0, -10.0, -10.0],
        [-20.0, -10.0, -10.0, -12.0, -10.0, -10.0],
    )
    wet = _cube(
        "2026-09-01",
        "NISAR_WET",
        [-21.0, -18.5, -16.0, -8.5, -7.5, -5.5],
        [-21.0, -18.5, -16.0, -7.7, -7.3, -5.2],
    )
    analysis = classify_stack([dry, wet], hand, thr, pixel_area_m2=10_000.0)
    assert analysis.baseline.accepted
    assert analysis.baseline.reference_date == "2026-06-20"
    assert analysis.baseline.gap == "1/2"
    assert analysis.baseline.f_dry == "1/5"
    assert analysis.baseline.f_wet == "2/5"

    by_date = {item.date: item for item in analysis.dates}
    assert by_date["2026-06-20"].n_water == 1
    assert by_date["2026-06-20"].n_valid == 5
    assert by_date["2026-06-20"].class_raster is None
    assert by_date["2026-06-20"].n_class2 is None

    wet_result = by_date["2026-09-01"]
    assert wet_result.n_water == 2
    assert wet_result.n_valid == 5
    assert wet_result.n_class1 == 2
    assert wet_result.n_valid_class1 == 5
    assert wet_result.n_class2 == 1
    assert wet_result.n_valid_class2 == 5
    assert list(wet_result.water_raster[0]) == [1, 1, 0, 0, 0, -1]
    assert list(wet_result.class_raster[0]) == [0, 1, 1, 2, 0, -1]

    sens = {row.name: row for row in wet_result.sensitivity}
    assert sens["nominal"].n_class1 == 2
    assert sens["nominal"].n_class2 == 1
    assert sens["class1_delta_hh_db_max_minus"].n_class1 == 1
    assert sens["class1_delta_hh_db_max_plus"].n_class1 == 2
    assert sens["class2_delta_hh_db_min_minus"].n_class2 == 2
    assert sens["class2_delta_hh_db_min_plus"].n_class2 == 0
    assert sens["class2_delta_hv_hh_db_abs_max_minus"].n_class2 == 0
    assert sens["class2_delta_hv_hh_db_abs_max_plus"].n_class2 == 1
    assert sens["hand_12"].n_class1 == 1
    assert sens["hand_12"].n_class2 == 1
    assert sens["hand_12"].n_valid_class1 == 4
    assert sens["hand_24"].n_class2 == 2
    assert sens["hand_24"].n_valid_class1 == 6
    assert sens["open_water_abs_hh_db_minus"].n_water == 1
    assert sens["open_water_abs_hh_db_plus"].n_water == 2
    assert sens["hand_12"].n_water == 2
    assert sens["hand_12"].n_valid_water == 4
    assert sens["hand_24"].n_valid_water == 6


def test_no_baseline_and_f_wet_zero_leave_class_2_null():
    thr = _repo_thresholds()
    hand = np.array([[5.0, 5.0]])
    # Same fraction on both dates: gap 0, which is below 0.20.
    dry = _cube("2026-06-20", "A", [-20.0, -10.0], [-20.0, -10.0])
    wet = _cube("2026-09-01", "B", [-20.0, -10.0], [-20.0, -10.0])
    analysis = classify_stack([dry, wet], hand, thr, 10_000.0)
    assert not analysis.baseline.accepted
    assert analysis.baseline.reason == "relative_gap"
    for item in analysis.dates:
        assert item.n_class2 is None
        assert item.class_raster is None
        assert list(item.water_raster[0]) == [1, 0]

    dark_never = _cube("2026-06-20", "A", [-10.0, -10.0], [-10.0, -10.0])
    dark_later = _cube("2026-09-01", "B", [-12.0, -11.0], [-12.0, -11.0])
    zero = classify_stack([dark_never, dark_later], hand, thr, 10_000.0)
    assert zero.baseline.reason == "f_wet_zero"
    assert zero.baseline.gap is None
    for item in zero.dates:
        assert item.n_water == 0
        assert item.n_valid == 2
        assert item.n_class2 is None
        assert list(item.water_raster[0]) == [0, 0]


def test_scene_name_parser_and_stack_choice():
    dual = parse_scene_name(DUAL)
    assert dual["processing_type"] == "PR"
    assert dual["track"] == 4
    assert dual["frame"] == 18
    assert dual["direction"] == "A"
    assert dual["pole"] == "DHDH"
    assert dual["crid"] == "P05023"
    assert dual["start_token"] == "20251029T111130"

    single = parse_scene_name(SINGLE)
    assert single["pole"] == "SHNA"
    assert single["pole"][:2] == "SH"
    assert single["crid"] == "X05010"

    def ref(name: str, date: str, track: int, frame: int) -> GranuleRef:
        parsed = parse_scene_name(name) if name.endswith(".h5") else {}
        pole = str(parsed.get("pole") or "DHDH")
        return GranuleRef(
            scene_name=name,
            date=date,
            track=track,
            frame=frame,
            direction="A",
            pole=pole,
            primary_pol=pole[:2],
            url="https://example.test/granule.h5",
            provisional=True,
            crid=str(parsed.get("crid") or ""),
        )

    second = (
        "NISAR_L2_PR_GCOV_014_011_A_086_2005_DHDH_A_"
        "20260701T000000_20260701T000100_P05023_N_P_J_001.h5"
    )
    third = (
        "NISAR_L2_PR_GCOV_014_011_A_086_2005_DHDH_A_"
        "20260713T000000_20260713T000100_P05023_N_P_J_001.h5"
    )
    long_stack = [
        ref(DUAL, "2026-06-17", 11, 86),
        ref(second, "2026-07-01", 11, 86),
        ref(third, "2026-07-13", 11, 86),
    ]
    # The parser reads track/frame from the name, so build refs explicitly.
    granules = [
        GranuleRef("DH_A", "2026-06-17", 11, 86, "A", "DHDH", "DH", "https://a", True, "P05023"),
        GranuleRef("DH_B", "2026-07-01", 11, 86, "A", "DHDH", "DH", "https://b", True, "P05023"),
        GranuleRef("DH_C", "2026-07-13", 11, 86, "A", "DHDH", "DH", "https://c", True, "P05023"),
        GranuleRef("DH_OTHER", "2026-06-17", 47, 4, "A", "DHDH", "DH", "https://d", True, "P05023"),
        GranuleRef(SINGLE, "2026-06-20", 10, 36, "A", "SHNA", "SH", "https://e", True, "X05010"),
    ]
    # Silence the unused long_stack construction if the name parser is what we wanted.
    assert long_stack[0].primary_pol == "DH"
    choice = select_stack(granules)
    assert choice.key == (11, 86, "A")
    assert tuple(item.scene_name for item in choice.granules) == ("DH_A", "DH_B", "DH_C")
    reasons = dict(choice.excluded)
    assert "no HH and HV" in reasons[SINGLE]
    assert reasons["DH_OTHER"].startswith("other stack")


def test_resample_averages_finite_power_only():
    grid = AnalysisGrid(
        crs="EPSG:32618",
        transform=(20.0, 0.0, 0.0, 0.0, -20.0, 20.0),
        width=1,
        height=1,
        cell_m=20.0,
    )
    # Source centers (5, 15), (15, 15), (5, 5), (15, 5), all inside the 20 m cell.
    averaged = resample_power_mean(
        np.array([[1.0, 1.0], [np.nan, 3.0]]),
        np.array([5.0, 15.0]),
        np.array([15.0, 5.0]),
        "EPSG:32618",
        grid,
    )
    assert averaged.shape == (1, 1)
    assert abs(float(averaged[0, 0]) - (5.0 / 3.0)) < 1e-12

    same = AnalysisGrid("EPSG:32618", (10.0, 0.0, 0.0, 0.0, -10.0, 20.0), 2, 2, 10.0)
    copied = resample_power_mean(
        np.array([[1.0, np.nan], [0.0, 4.0]]),
        np.array([5.0, 15.0]),
        np.array([15.0, 5.0]),
        "EPSG:32618",
        same,
    )
    assert copied[0, 0] == 1.0
    assert np.isnan(copied[0, 1])
    assert copied[1, 0] == 0.0
    assert copied[1, 1] == 4.0

    missing = resample_power_mean(
        np.array([[np.nan, np.nan], [np.nan, np.nan]]),
        np.array([5.0, 15.0]),
        np.array([15.0, 5.0]),
        "EPSG:32618",
        same,
    )
    assert np.isnan(missing).all()


def test_s1_miss_does_not_count_missing_pixels():
    positive = np.array([True, True, True, False])
    domain = np.array([True, True, True, True])
    vv = np.array([-20.0, -10.0, np.nan, -20.0])
    vh = np.array([-25.0, -18.0, np.nan, -22.0])
    result = compare_s1(positive, domain, vv, vh, -18.0, "2026-09-01", "class2", 3)
    assert result.n_positive == 3
    assert result.n_positive_with_s1 == 2
    assert result.n_positive_s1_missing == 1
    assert result.n_missed == 1
    assert result.n_s1_water == 2
    assert result.n_s1_water_not_positive == 1
    assert result.median_vv_positive == -15.0


def test_raster_roundtrip_keeps_nodata(tmp_path: Path):
    grid = AnalysisGrid("EPSG:32618", (90.0, 0.0, 500000.0, 0.0, -90.0, 1_000_000.0), 2, 2, 90.0)
    array = np.array([[1, -1], [0, 2]], dtype=np.int16)
    path = tmp_path / "class.tif"
    write_class_geotiff(path, array, grid, "uncalibrated class raster")
    with rasterio.open(path) as src:
        assert src.nodata == -1
        assert src.crs.to_epsg() == 32618
        assert list(src.read(1).reshape(-1)) == [1, -1, 0, 2]


def test_analysis_grid_covers_the_gate_bbox():
    grid = __import__("gee_math.flood_polarimetric_math", fromlist=["build_grid"]).build_grid(
        (-75.40, 7.90, -74.20, 9.20)
    )
    # 1.2° by 1.3° at 90 m is about 1.5e3 by 1.6e3 cells.
    assert grid.crs == "EPSG:32618"
    assert grid.cell_m == 90.0
    assert grid.pixel_area_m2 == 8100.0
    assert 1200 < grid.width < 2200
    assert 1400 < grid.height < 2200


def test_report_contains_ids_denominators_and_null_class2():
    thr = _repo_thresholds()
    hand = np.array([[5.0, 5.0]])
    dry = _cube("2026-06-20", "NISAR_DRY_ID", [-20.0, -10.0], [-20.0, -10.0])
    wet = _cube("2026-09-01", "NISAR_WET_ID", [-20.0, -10.0], [-20.0, -10.0])
    analysis = classify_stack([dry, wet], hand, thr, 10_000.0)
    context = _context(
        granules=(
            GranuleRef(
                "NISAR_DRY_ID",
                "2026-06-20",
                11,
                86,
                "A",
                "DHDH",
                "DH",
                "https://example.test/a.h5",
                True,
                "P05023",
            ),
        ),
        stack=StackChoice((11, 86, "A"), (), "test stack", ()),
    )
    text = render_report(analysis, context)
    assert "NISAR_DRY_ID" in text
    assert "NISAR_WET_ID" in text
    assert "denominator 2 valid pixels *(measured)*" in text
    assert "Class 2 = null" in text
    assert "PROVISIONAL" in text
    assert "uncalibrated" in text
    assert "P05023" in text
    assert "not a map of the May 2024 breach" in text


def test_blocked_report_does_not_invent_hectares():
    context = _context(blocked="MERIT Hydro HAND fetch failed. RuntimeError: offline")
    text = render_report(None, context)
    assert "HAND fetch failed" in text
    assert "Class 2 = null" in text
    assert "Hectares were not computed" in text
    assert "*(measured)*" in text  # the search count is the only measurement
    assert "valid pixels" not in text


def _context(**overrides) -> ReportContext:
    base = dict(
        command="uv run python -m gee_math.flood_polarimetric_math",
        generated_utc="2026-11-14T00:00:00Z",
        bbox=(-75.4, 7.9, -74.2, 9.2),
        bbox_source="brief estimate",
        window=("2026-06-17", "2026-11-14"),
        config_path="config/preregistered.yaml",
        config_sha256="abc",
        granules=(),
        stack=None,
        grid_text="EPSG:32618, 90 m",
        hand_source="missing",
        gcov_units=(),
        chirps_mm={},
        s1=(),
        read_failures=(),
        notes=(),
        blocked=None,
        search_count=1,
    )
    base.update(overrides)
    return ReportContext(**base)
