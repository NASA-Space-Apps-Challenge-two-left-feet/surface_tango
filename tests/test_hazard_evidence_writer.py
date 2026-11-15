"""The landslide evidence serializer: faithful outcome from measured inputs only."""

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
