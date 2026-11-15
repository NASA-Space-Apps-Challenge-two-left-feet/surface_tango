"""Hand-written logic fixtures only; inventory and arithmetic in ALLOWLIST.md."""

import random
import sys
from collections import Counter
from itertools import permutations
from pathlib import Path

import pytest

# The repository is not an installed package; also support the pytest console entry point.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation.scoring import (  # noqa: E402
    ConfidenceInterval,
    beats_baseline,
    block_bootstrap,
    built_up_excess,
    evaluation_k,
    informative_gate,
    percentile_ranks,
    precision_at_k,
    rank_units,
    wilson_interval,
)


def test_percentiles_ties_constant_and_singleton():
    assert percentile_ranks([30, 10, 20, 20]) == (1, 0, 0.5, 0.5)
    assert percentile_ranks([7, 7]) == (0.5, 0.5)
    assert percentile_ranks([7]) == (0.5,)


def test_radar_and_baseline_share_population_and_access_terms():
    result = rank_units(["a", "b", "c"], [3, 1, 2], [10, 30, 20], [0, 20, 10], access_weight=0.25)
    assert [(u.unit_id, u.score) for u in result.radar] == [("c", 0.28125), ("a", 0), ("b", 0)]
    assert [(u.unit_id, u.score) for u in result.baseline] == [("b", 1.25), ("c", 0.5625), ("a", 0)]


def test_tie_break_is_independent_of_input_order_and_negative_z_is_valid():
    result = rank_units(["b", "a"], [-1, -1], [1, 1], [0, 0], access_weight=0.25)
    assert [u.unit_id for u in result.radar] == ["a", "b"]
    assert result.radar[0].score == 0.28125


@pytest.mark.parametrize("n,expected", [(1, 1), (30, 5), (50, 5), (51, 6), (100, 10)])
def test_k_ceil_minimum_and_cap(n, expected):
    assert evaluation_k(n, fraction=0.1, minimum=5) == expected


def test_precision_uses_only_top_k():
    assert precision_at_k([True, False, True, True], 2) == 0.5
    assert precision_at_k([True, False, True, True], 4) == 0.75


@pytest.mark.parametrize(
    "successes,low,high",
    [
        (0, 0, 0.4898908364545973),
        (2, 0.15003898915214958, 0.8499610108478504),
        (4, 0.5101091635454027, 1),
    ],
)
def test_wilson_known_answers(successes, low, high):
    ci = wilson_interval(successes, 4)
    assert ci.low == pytest.approx(low)
    assert ci.high == pytest.approx(high)


def gate(labels, **kwargs):
    return informative_gate(
        labels, min_units=30, min_positives=5, prevalence_min=0.1, prevalence_max=0.7, **kwargs
    )


@pytest.mark.parametrize(
    "n,positives,expected",
    [
        (30, 5, True),
        (29, 5, False),
        (30, 4, False),
        (50, 5, True),
        (51, 5, False),
        (30, 21, True),
        (30, 22, False),
    ],
)
def test_informative_boundaries(n, positives, expected):
    result = gate([True] * positives + [False] * (n - positives))
    assert result.informative is expected
    assert result.n_units == n
    assert result.n_positives == positives
    assert result.prevalence == positives / n


def test_empty_and_missing_ground_truth_are_explicit():
    assert gate([]).prevalence is None
    assert not gate([]).informative
    result = gate([True] * 5 + [False] * 25, ground_truth_available=False)
    assert result.reasons == ("missing_ground_truth",)


def test_excess_uses_pooled_pixels_not_mean_of_barrio_medians():
    assert built_up_excess([[2, 4, 6], [10]], [[0], [2]]) == 4


@pytest.fixture
def paired_barrios():
    # Final field is the original barrio ID, retained through resampling.
    a = (False, (2,), (0,), (1,), (0,), "a")
    b = (True, (4,), (0,), (1,), (0,), "b")
    return a, b


def _paired_statistics(blocks):
    # Keep original barrio identity as the primary tie-break key. The suffix
    # distinguishes repeated copies of that same barrio without deduplicating them.
    occurrences = Counter()
    ids = []
    for row in blocks:
        original_id = row[5]
        occurrences[original_id] += 1
        ids.append(f"{original_id}#{occurrences[original_id]}")
    rankings = rank_units(
        ids,
        [row[1][0] for row in blocks],
        [1] * len(blocks),
        [0] * len(blocks),
        access_weight=0.25,
    )
    labels = {uid: row[0] for uid, row in zip(ids, blocks, strict=True)}
    delta = precision_at_k([labels[u.unit_id] for u in rankings.radar], 1) - precision_at_k(
        [labels[u.unit_id] for u in rankings.baseline], 1
    )
    ec = built_up_excess([row[1] for row in blocks], [row[2] for row in blocks])
    ek = built_up_excess([row[3] for row in blocks], [row[4] for row in blocks])
    return {"precision_difference": delta, "E_C": ec, "E_K": ek, "adjusted_excess": ec - ek}


@pytest.mark.parametrize("sample_ids", ["ab", "aab", "abb"])
def test_paired_statistic_is_independent_of_draw_order(paired_barrios, sample_ids):
    a, b = paired_barrios
    by_id = {"a": a, "b": b}
    sample = tuple(by_id[uid] for uid in sample_ids)
    expected = _paired_statistics(sample)
    assert expected["precision_difference"] == 1.0
    for reordered in set(permutations(sample)):
        assert _paired_statistics(reordered) == expected


def test_paired_bootstrap_recomputes_rankings_and_preserves_whole_blocks(paired_barrios):
    # With seed zero the two draws are (b,b), then (a,b). No pixel resampling.
    a, b = paired_barrios
    draws = []

    def statistics(blocks):
        draws.append(blocks)
        return _paired_statistics(blocks)

    before = random.getstate()
    result = block_bootstrap([a, b], statistics, replicates=2, seed=0)
    assert random.getstate() == before
    assert draws == [(b, b), (a, b)]
    assert result["precision_difference"].low == pytest.approx(0.025)
    assert result["precision_difference"].high == pytest.approx(0.975)
    assert result["E_C"].low == pytest.approx(3.025)
    assert result["E_C"].high == pytest.approx(3.975)
    assert result["E_K"] == ConfidenceInterval(1, 1)
    assert result["adjusted_excess"].low == pytest.approx(2.025)
    assert result["adjusted_excess"].high == pytest.approx(2.975)
    assert block_bootstrap([a, b], statistics, replicates=2, seed=0) == result


def test_bootstrap_single_block_has_zero_width_interval():
    result = block_bootstrap([(2, 4)], lambda rows: {"sum": sum(rows[0])}, replicates=2, seed=0)
    assert result == {"sum": ConfidenceInterval(6, 6)}


@pytest.mark.parametrize(
    "precision,coevent,adjusted,timing,informative,expected",
    [
        ((0.1, 0.2), (1, 2), (0.5, 1), "pre-event", True, True),
        ((-0.2, -0.1), (1, 2), (0.5, 1), "pre-event", True, False),
        ((0, 0.2), (1, 2), (0.5, 1), "pre-event", True, False),
        ((0.1, 0.2), (0, 2), (0.5, 1), "pre-event", True, False),
        ((0.1, 0.2), (1, 2), (-1, 1), "pre-event", True, False),
        ((0.1, 0.2), (1, 2), (0, 1), "pre-event", True, False),
        ((0.1, 0.2), (1, 2), None, "missing", True, False),
        ((0.1, 0.2), (1, 2), (0.5, 1), "post-event", True, False),
        ((0.1, 0.2), (1, 2), (0.5, 1), "pre-event", False, False),
    ],
)
def test_beats_rule_requires_direction_control_and_information(
    precision,
    coevent,
    adjusted,
    timing,
    informative,
    expected,
):
    assert (
        beats_baseline(
            ConfidenceInterval(*precision),
            ConfidenceInterval(*coevent),
            ConfidenceInterval(*adjusted) if adjusted else None,
            control_timing=timing,
            informative=informative,
        )
        is expected
    )


@pytest.mark.parametrize(
    "call",
    [
        lambda: percentile_ranks([]),
        lambda: percentile_ranks([float("nan")]),
        lambda: percentile_ranks([float("inf")]),
        lambda: rank_units(["a", "a"], [1, 2], [1, 2], [0, 0], access_weight=0.25),
        lambda: rank_units(["a"], [1, 2], [1], [0], access_weight=0.25),
        lambda: rank_units(["a"], [1], [-1], [0], access_weight=0.25),
        lambda: rank_units(["a"], [1], [1], [0], access_weight=float("nan")),
        lambda: evaluation_k(0, fraction=0.1, minimum=5),
        lambda: evaluation_k(30, fraction=0, minimum=5),
        lambda: precision_at_k([True], 2),
        lambda: precision_at_k([True], 0),
        lambda: precision_at_k([None], 1),
        lambda: gate([1]),
        lambda: wilson_interval(1, 0),
        lambda: wilson_interval(2, 1),
        lambda: wilson_interval(True, 1),
        lambda: wilson_interval(0, 1, confidence=1),
        lambda: ConfidenceInterval(1, 0),
        lambda: ConfidenceInterval(float("nan"), 1),
        lambda: built_up_excess([[1]], [[]]),
        lambda: built_up_excess([[1]], [[0], [1]]),
        lambda: block_bootstrap([], lambda rows: {"x": 1}, replicates=2, seed=0),
        lambda: block_bootstrap([1], lambda rows: {"x": 1}, replicates=1, seed=0),
        lambda: block_bootstrap([1], lambda rows: {"x": float("nan")}, replicates=2, seed=0),
    ],
)
def test_invalid_or_missing_inputs_fail_explicitly(call):
    with pytest.raises(ValueError):
        call()


def test_bootstrap_rejects_changing_statistics():
    results = iter([{"a": 1}, {"b": 1}])
    with pytest.raises(ValueError, match="keys changed"):
        block_bootstrap([1], lambda rows: next(results), replicates=2, seed=0)
