"""Offline tests for the scoring MCP wrappers (plan 03-06, #35).

These check that the wrappers plumb config + inputs into `validation.scoring`
correctly and fail loudly on missing pre-registration values. Expected values
come from calling the scoring library directly, so there are no hand-computed
constants (nothing to list in validation/ALLOWLIST.md).
"""

from __future__ import annotations

import pytest

from mcp_servers import scoring_tools
from validation import scoring

# A quake pre-registration section mirroring config/preregistered.yaml (config, not data).
QUAKE = {
    "ranking": {"access_weight": 0.25},
    "k_rule": {"fraction": 0.10, "minimum": 5},
    "informative": {
        "min_units": 30,
        "min_positives": 5,
        "prevalence_min": 0.10,
        "prevalence_max": 0.70,
    },
}


def _prereg(**overrides):
    quake = {**QUAKE, **overrides.pop("quake", {})}
    return {"quake": quake, **overrides}


# --- get_earthquake_pair_set ---------------------------------------------------------------


def test_pair_set_list_schema_normalises_and_keeps_extras():
    pairs = [
        {
            "track": 11,
            "geometry": "descending",
            "frame": 86,
            "reference_R": "R11",
            "coevent_C": "C11",
            "control_K": "K11",
            "baseline_days": {"R": 12, "C": 24, "K": 12},
            "baseline_mismatch": True,
        },
        {"track": 47, "reference_R": "R47", "coevent_C": "C47", "control_K": "K47"},
    ]
    out = scoring_tools.earthquake_pair_set({"quake": {"pairs": pairs}})
    assert [t["track"] for t in out] == [11, 47]
    assert out[0]["reference_R"] == "R11" and out[0]["control_K"] == "K11"
    assert out[0]["baseline_days"] == {"R": 12, "C": 24, "K": 12}
    assert out[0]["baseline_mismatch"] is True
    assert "track" in out[1] and "baseline_days" not in out[1]


def test_pair_set_accepts_single_triplet_mapping():
    triplet = {"reference_R": "R", "coevent_C": "C", "control_K": "K"}
    out = scoring_tools.earthquake_pair_set({"quake": {"pairs": triplet}})
    assert out == [triplet]


def test_pair_set_raises_on_null_pairs():
    with pytest.raises(ValueError, match="quake.pairs is not set"):
        scoring_tools.earthquake_pair_set({"quake": {"pairs": None}})


def test_pair_set_raises_on_missing_id():
    pairs = [{"reference_R": "R", "coevent_C": None, "control_K": "K"}]
    with pytest.raises(ValueError, match="missing granule ids"):
        scoring_tools.earthquake_pair_set({"quake": {"pairs": pairs}})


def test_pair_set_raises_on_missing_quake_section():
    with pytest.raises(ValueError, match="section 'quake' is missing"):
        scoring_tools.earthquake_pair_set({})


# --- rank_first_aid_barrios ----------------------------------------------------------------

UNITS = ["a", "b", "c", "d", "e", "f"]
DPM = [2.0, 1.0, 0.5, -0.5, 3.0, 0.1]
POP = [100.0, 200.0, 50.0, 400.0, 10.0, 300.0]
DIST = [1.0, 2.0, 0.5, 3.0, 0.1, 4.0]


def test_rank_matches_direct_scoring_and_cuts_at_k():
    out = scoring_tools.rank_barrios(UNITS, DPM, POP, DIST, preregistered=_prereg())
    direct = scoring.rank_units(UNITS, DPM, POP, DIST, access_weight=0.25)
    k = scoring.evaluation_k(len(UNITS), fraction=0.10, minimum=5)
    assert out["k"] == k
    assert out["radar_ranking"] == [{"unit_id": u.unit_id, "score": u.score} for u in direct.radar]
    assert out["first_aid_barrios"] == out["radar_ranking"][:k]
    assert out["baseline_ranking"] == [
        {"unit_id": u.unit_id, "score": u.score} for u in direct.baseline
    ]


def test_rank_top_k_only_false_returns_all():
    out = scoring_tools.rank_barrios(
        UNITS, DPM, POP, DIST, preregistered=_prereg(), top_k_only=False
    )
    assert out["first_aid_barrios"] == out["radar_ranking"]


def test_rank_raises_on_missing_access_weight():
    bad = {"quake": {"ranking": {}, "k_rule": {"fraction": 0.1, "minimum": 5}}}
    with pytest.raises(ValueError, match="quake.ranking.access_weight"):
        scoring_tools.rank_barrios(UNITS, DPM, POP, DIST, preregistered=bad)


# --- score_against_baseline ----------------------------------------------------------------

RADAR_LABELS = [True, True, False, True, False, False, True, False, False, False]
BASE_LABELS = [False, True, False, False, True, False, False, True, False, False]


def test_score_matches_direct_scoring():
    out = scoring_tools.score_barrios(RADAR_LABELS, BASE_LABELS, preregistered=_prereg())
    k = scoring.evaluation_k(len(RADAR_LABELS), fraction=0.10, minimum=5)
    assert out["k"] == k
    assert out["radar_precision_at_k"] == scoring.precision_at_k(RADAR_LABELS, k)
    assert out["baseline_precision_at_k"] == scoring.precision_at_k(BASE_LABELS, k)
    assert out["precision_difference"] == pytest.approx(
        out["radar_precision_at_k"] - out["baseline_precision_at_k"]
    )
    radar_ci = scoring.wilson_interval(sum(RADAR_LABELS[:k]), k)
    assert out["radar_wilson"] == {"low": radar_ci.low, "high": radar_ci.high}
    gate = scoring.informative_gate(
        RADAR_LABELS, min_units=30, min_positives=5, prevalence_min=0.10, prevalence_max=0.70
    )
    assert out["informative"] == gate.informative
    assert out["informative_reasons"] == list(gate.reasons)
    assert out["n_positives"] == gate.n_positives


def test_score_missing_ground_truth_is_never_informative():
    out = scoring_tools.score_barrios(
        RADAR_LABELS, BASE_LABELS, preregistered=_prereg(), ground_truth_available=False
    )
    assert out["informative"] is False
    assert "missing_ground_truth" in out["informative_reasons"]


def test_score_raises_on_length_mismatch():
    with pytest.raises(ValueError, match="same evaluated units"):
        scoring_tools.score_barrios([True, False], [True], preregistered=_prereg())
