"""The hazard evidence serializers: faithful artifacts from measured inputs only."""

import json

from scripts import write_hazard_evidence as whe


def _setup(tmp_path, monkeypatch, exceeds):
    base = tmp_path / "aburra"
    base.mkdir()
    (base / "summary.json").write_text(
        json.dumps(
            {
                "noise_floor_mm": 9.105,
                "n_pairs_with_rms": 17,
                "aoi_key": "1_aburra",
                "command": "uv run python -m gee_math.landslide_insar_math",
                "measured_at_utc": "2026-11-15T02:10:16Z",
                "pairs": [
                    {
                        "scene_name": "NISAR_L2_PR_GUNW_A",
                        "track": 47,
                        "reference_date": "2026-06-17",
                        "secondary_date": "2026-06-29",
                        "residual_rms_mm": 7.7,
                        "n_stable": 26456,
                    }
                ],
            }
        )
    )
    (base / "calibration.json").write_text(
        json.dumps(
            [
                {
                    "stack": "track 11",
                    "n_pairs": 8,
                    "n_eligible": 100,
                    "observed_kept_fraction": 0.9 if exceeds else 0.37,
                    "null_mean": 0.41,
                    "null_p95": 0.5,
                    "exceeds_null": exceeds,
                },
            ]
        )
    )
    monkeypatch.setattr(whe, "CACHE", tmp_path)


def test_no_motion_when_kept_fraction_below_null(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, exceeds=False)
    art = whe.landslide_artifact("aburra")
    assert art["schema"] == "landslide/1"
    assert art["noise_floor_verdict"]["outcome"] == "no_motion"
    assert "no motion detected above 9.105 mm (17 pairs)" in art["noise_floor_verdict"]["text"]
    assert art["provenance"]["granule_ids"] == ["NISAR_L2_PR_GUNW_A"]


def test_motion_when_a_stack_exceeds_the_null(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, exceeds=True)
    art = whe.landslide_artifact("aburra")
    assert art["noise_floor_verdict"]["outcome"] == "motion"


def test_absent_inputs_are_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(whe, "CACHE", tmp_path)
    assert whe.landslide_artifact("aburra") is None


# --- flood (La Mojana) ------------------------------------------------------- #
def _flood_setup(tmp_path, monkeypatch, dates=None, manifest=None):
    if dates is None:
        dates = [
            {
                "date": "2026-10-27",
                "granule_ids": ["NISAR_L2_PR_GCOV_REF"],
                "n_water": 10,
                "n_valid": 100,
                "n_class1": 0,
                "n_valid_class1": 1,
                "n_class2": 0,
                "n_valid_class2": 1,
            },
            {
                "date": "2026-06-17",
                "granule_ids": ["NISAR_L2_PR_GCOV_WET"],
                "n_water": 1000,
                "n_valid": 2000,
                "n_class1": 30,
                "n_valid_class1": 200,
                "n_class2": 50,
                "n_valid_class2": 200,
            },
        ]
    base = tmp_path / "mojana"
    base.mkdir()
    (base / "provenance.json").write_text(
        json.dumps(
            {
                "command": "uv run python -m gee_math.flood_polarimetric_math",
                "generated_utc": "2026-11-15T03:00:00Z",
                "bbox": [-74.9, 8.2, -74.2, 8.9],
                "baseline": {
                    "accepted": True,
                    "reference_date": "2026-10-27",
                    "f_wet": "2473/76974",
                    "f_dry": "0",
                    "gap": "1",
                },
                "dates": dates,
            }
        )
    )
    (base / "manifest.json").write_text(
        json.dumps(manifest if manifest is not None else {"aoi_key": "3_la_mojana_caregato"})
    )
    prereg = tmp_path / "prereg.yaml"
    prereg.write_text("status: frozen\nlabels: {uncalibrated: [label_a, label_b]}\n")
    monkeypatch.setattr(whe, "CACHE", tmp_path)
    monkeypatch.setattr(whe, "PREREG", prereg)


def test_flood_display_date_areas_and_envelope(tmp_path, monkeypatch):
    _flood_setup(tmp_path, monkeypatch)
    art = whe.flood_artifact("mojana")
    assert art["schema"] == "flood/1"
    assert art["baseline"]["accepted"] is True
    assert art["baseline"]["reference_date"] == "2026-10-27"
    assert len(art["dates"]) == 2
    assert art["uncalibrated"] == ["label_a", "label_b"]
    assert art["provenance"]["granule_ids"] == ["NISAR_L2_PR_GCOV_REF", "NISAR_L2_PR_GCOV_WET"]
    assert art["provenance"]["cache_build_time"] == "2026-11-15T03:00:00Z"
    assert art["provenance"]["pixel_area_m2_source"].startswith("constant 90 m")
    w = art["water_extent"]
    assert w["pixel_count"] == 1000 and w["valid_pixel_count"] == 2000
    assert w["value_ha"] == 810.0  # 1000 px * 8100 m2 / 1e4, hand-computed
    assert w["pixel_area_m2"] == 8100.0
    assert w["reference_date"] == "2026-06-17"
    assert w["source_ids"] == ["NISAR_L2_PR_GCOV_WET"]
    assert w["sensitivity_range"] is None
    assert "sweep not serialized" in w["sensitivity_reason"]
    c1 = art["open_water_flood"]
    assert c1["value_ha"] == 24.3  # 30 px * 8100 m2 / 1e4, hand-computed
    assert c1["reference_date"] == "2026-10-27" and c1["target_date"] == "2026-06-17"
    assert c1["source_ids"] == ["NISAR_L2_PR_GCOV_REF", "NISAR_L2_PR_GCOV_WET"]
    assert art["subcanopy_double_bounce_flood"]["value_ha"] == 40.5  # 50 px, hand-computed
    from mcp_servers import evidence

    env = evidence.build_flood_envelope(art, {}, "analyze_flood_inundation")
    assert env["state"] == "live"
    assert env["data"]["area_evidence"]["water_extent_ha"]["pixel_count"] == 1000
    assert env["data"]["area_evidence"]["total_inundated_ha"] is None
    assert env["data"]["alert_level"] is None


def test_flood_uses_the_manifest_pixel_size_when_stated(tmp_path, monkeypatch):
    _flood_setup(
        tmp_path,
        monkeypatch,
        manifest={"aoi_key": "3_la_mojana_caregato", "pixel_size_m": 10.0},
    )
    art = whe.flood_artifact("mojana")
    assert art["water_extent"]["pixel_area_m2"] == 100.0  # 10 m x 10 m
    assert art["water_extent"]["value_ha"] == 10.0  # 1000 px * 100 m2 / 1e4
    assert art["provenance"]["pixel_area_m2_source"] == "manifest.json states the pixel area/size"


def test_flood_absent_inputs_are_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(whe, "CACHE", tmp_path)
    assert whe.flood_artifact("mojana") is None


def test_flood_skips_when_the_display_date_is_absent(tmp_path, monkeypatch):
    _flood_setup(
        tmp_path,
        monkeypatch,
        dates=[
            {
                "date": "2026-10-27",
                "granule_ids": ["NISAR_L2_PR_GCOV_REF"],
                "n_water": 10,
                "n_valid": 100,
                "n_class1": 0,
                "n_valid_class1": 1,
                "n_class2": 0,
                "n_valid_class2": 1,
            }
        ],
    )
    assert whe.flood_artifact("mojana") is None


# --- quake (Eje Cafetero; C/K statistics gated on the pre-registration) ------ #
def _quake_setup(tmp_path, monkeypatch, frozen=True, prov=None):
    if prov is None:
        prov = {
            "run_utc": "2026-11-15T04:00:00Z",
            "prereg_status": "draft",  # run-time state, as the real runs record it
            "prereg_sha1": "0123456789abcdef",
            "baseline_mismatch": True,
            "pairs": {
                "C": {
                    "granule_id": "NISAR_L2_PR_GUNW_C",
                    "ref_date": "20260720",
                    "sec_date": "20260813",
                    "baseline_days": 24,
                    "frame": 86,
                    "flight_direction": "descending",
                    "provisional": False,
                },
                "R": {
                    "granule_id": "NISAR_L2_PR_GUNW_R",
                    "ref_date": "20260708",
                    "sec_date": "20260720",
                    "baseline_days": 12,
                    "frame": 86,
                    "flight_direction": "descending",
                    "provisional": False,
                },
                "K": {
                    "granule_id": "NISAR_L2_PR_GUNW_K",
                    "ref_date": "20260626",
                    "sec_date": "20260708",
                    "baseline_days": 12,
                    "frame": 86,
                    "flight_direction": "descending",
                    "provisional": False,
                },
            },
            "units": {"n_units": 32, "unit_source": "asset:FAO/GAUL/2025/level2"},
            "summary_C": {
                "n_px_valid": 316399,
                "n_px_total": 10353357,
                "n_units_total": 32,
                "n_units_evaluated": 28,
                "n_units_excluded": 4,
                "excess_e": 0.125,
                "mu": 0.9,
            },
            "summary_K_control": {"excess_e": 0.01, "mu": 0.95},
        }
    (tmp_path / "quake" / "dpm_track11.zarr").mkdir(parents=True)
    (tmp_path / "quake" / "dpm_track11.zarr" / "zarr.json").write_text(
        json.dumps({"attributes": {"provenance": json.dumps(prov)}})
    )
    prereg = tmp_path / "prereg.yaml"
    prereg.write_text(f"status: {'frozen' if frozen else 'draft'}\nlabels: {{uncalibrated: []}}\n")
    monkeypatch.setattr(whe, "CACHE", tmp_path)
    monkeypatch.setattr(whe, "PREREG", prereg)
    return prov


def test_quake_counts_served_and_statistics_sealed_while_draft(tmp_path, monkeypatch):
    _quake_setup(tmp_path, monkeypatch, frozen=False)
    art = whe.quake_artifact(track=11)
    assert art["schema"] == "quake/1"
    assert art["counts"] == {
        "valid_pixels": 316399,
        "window_pixels": 10353357,
        "units_total": 32,
        "evaluated": 28,
        "excluded": 4,
    }
    assert art["pairs"]["C"]["baseline_days"] == 24
    assert art["units"]["n_units"] == 32
    assert art["scorecard"]["state"] == "uninformative"
    assert art["provenance"]["granule_ids"] == [
        "NISAR_L2_PR_GUNW_C",
        "NISAR_L2_PR_GUNW_R",
        "NISAR_L2_PR_GUNW_K",
    ]
    assert art["provenance"]["baseline_mismatch"] is True
    assert art["provenance"]["run_prereg_status"] == "draft"
    assert "coherence_statistics" not in art
    dumped = json.dumps(art)
    assert "excess_e" not in dumped and '"mu":' not in dumped and "summary_C" not in dumped
    from mcp_servers import evidence

    env = evidence.build_quake_envelope(art, {}, "analyze_earthquake_dpm", is_frozen=False)
    assert env["state"] == "live"
    assert env["data"]["counts"]["valid_pixels"] == 316399
    assert env["data"]["coherence_statistics"] is None
    assert "coherence_statistics" in env["unavailable"]


def test_quake_statistics_served_once_frozen(tmp_path, monkeypatch):
    prov = _quake_setup(tmp_path, monkeypatch, frozen=True)
    art = whe.quake_artifact(track=11)
    stats = art["coherence_statistics"]
    assert stats["coevent_C"] == prov["summary_C"]
    assert stats["control_K"] == prov["summary_K_control"]
    assert "draft" in stats["note"]
    from mcp_servers import evidence

    env = evidence.build_quake_envelope(art, {}, "analyze_earthquake_dpm", is_frozen=True)
    assert env["state"] == "live"
    assert env["data"]["coherence_statistics"] == stats


def test_quake_absent_zarr_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(whe, "CACHE", tmp_path)
    assert whe.quake_artifact(track=47) is None


def test_quake_skips_when_summary_counts_are_incomplete(tmp_path, monkeypatch):
    _quake_setup(
        tmp_path,
        monkeypatch,
        frozen=False,
        prov={
            "run_utc": "2026-11-15T04:00:00Z",
            "prereg_status": "draft",
            "pairs": {"C": {"granule_id": "NISAR_L2_PR_GUNW_C", "baseline_days": 24}},
            "units": {"n_units": 32},
            "summary_C": {"n_px_valid": 1},
        },
    )
    assert whe.quake_artifact(track=11) is None
