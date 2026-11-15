"""Pure barrio scoring; callers supply all frozen parameters from preregistered.yaml.

No IO, radar generation, imputation, or default scientific thresholds. Percentiles
use average ranks for ties, scaled as (rank - 1) / (n - 1); a singleton is 0.5.
Missing/nonfinite values are rejected: callers must explicitly exclude and count
unevaluable barrios before scoring. Unknown damage labels are never negatives.
"""

import math
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from statistics import NormalDist, median
from typing import TypeVar

T = TypeVar("T")


def _finite(values: Sequence[float], name: str) -> list[float]:
    result = [float(value) for value in values]
    if not result or not all(math.isfinite(value) for value in result):
        raise ValueError(f"{name} must be nonempty and finite")
    return result


def _integer(value: int, name: str, minimum: int = 1) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _confidence(value: float) -> None:
    if not math.isfinite(value) or not 0 < value < 1:
        raise ValueError("confidence must be between zero and one")


def percentile_ranks(values: Sequence[float]) -> tuple[float, ...]:
    """Average tied ranks, ascending; constant vectors therefore have rank 0.5."""
    values = _finite(values, "values")
    n = len(values)
    if n == 1:
        return (0.5,)
    order = sorted(range(n), key=values.__getitem__)
    result = [0.0] * n
    start = 0
    while start < n:
        end = start + 1
        while end < n and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / (2 * (n - 1))
        for index in order[start:end]:
            result[index] = rank
        start = end
    return tuple(result)


@dataclass(frozen=True)
class RankedUnit:
    unit_id: str
    score: float


@dataclass(frozen=True)
class Rankings:
    radar: tuple[RankedUnit, ...]
    baseline: tuple[RankedUnit, ...]


def rank_units(
    unit_ids: Sequence[str],
    dpm: Sequence[float],
    population: Sequence[float],
    distance: Sequence[float],
    *,
    access_weight: float,
) -> Rankings:
    """Rank evaluated barrios, descending; resolve score ties by ascending unit ID.

    dpm is the unit's median built-up Z supplied by the upstream pipeline.
    Negative Z is valid; population and road distance must be nonnegative.
    Both rankings use the exact same evaluated units.
    """
    ids = tuple(unit_ids)
    if not ids or any(not isinstance(item, str) or not item for item in ids):
        raise ValueError("unit_ids must be nonempty strings")
    if len(set(ids)) != len(ids):
        raise ValueError("unit_ids must be unique")
    vectors = [
        _finite(values, name)
        for values, name in [(dpm, "dpm"), (population, "population"), (distance, "distance")]
    ]
    if any(len(values) != len(ids) for values in vectors):
        raise ValueError("all vectors must describe the same evaluated units")
    if any(value < 0 for values in vectors[1:] for value in values):
        raise ValueError("population and distance must be nonnegative")
    if not math.isfinite(access_weight) or access_weight < 0:
        raise ValueError("access_weight must be finite and nonnegative")
    pd, pp, pa = (percentile_ranks(values) for values in vectors)
    baseline = [p * (1 + access_weight * a) for p, a in zip(pp, pa, strict=True)]
    radar = [d * base for d, base in zip(pd, baseline, strict=True)]

    def ordered(scores: Sequence[float]) -> tuple[RankedUnit, ...]:
        if not all(math.isfinite(score) for score in scores):
            raise ValueError("ranking scores overflowed")
        return tuple(
            sorted(
                (RankedUnit(uid, score) for uid, score in zip(ids, scores, strict=True)),
                key=lambda unit: (-unit.score, unit.unit_id),
            )
        )

    return Rankings(ordered(radar), ordered(baseline))


def evaluation_k(n_units: int, *, fraction: float, minimum: int) -> int:
    """Round the fractional unit count UP, enforce minimum, cap at available units."""
    _integer(n_units, "n_units")
    _integer(minimum, "minimum")
    if not math.isfinite(fraction) or not 0 < fraction <= 1:
        raise ValueError("fraction must be in (0, 1]")
    return min(n_units, max(minimum, math.ceil(fraction * n_units)))


def _labels(labels: Sequence[bool]) -> tuple[bool, ...]:
    labels = tuple(labels)
    if not all(type(value) is bool for value in labels):
        raise ValueError("labels must be known booleans, not missing values or counts")
    return labels


def precision_at_k(ordered_labels: Sequence[bool], k: int) -> float:
    """Labels must already be in descending ranking order; denominator is exactly k."""
    labels = _labels(ordered_labels)
    _integer(k, "k")
    if k > len(labels):
        raise ValueError("k exceeds the evaluated units")
    return sum(labels[:k]) / k


@dataclass(frozen=True)
class ConfidenceInterval:
    low: float
    high: float

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in (self.low, self.high)):
            raise ValueError("interval endpoints must be finite")
        if self.low > self.high:
            raise ValueError("interval endpoints are reversed")


def wilson_interval(successes: int, trials: int, *, confidence: float = 0.95) -> ConfidenceInterval:
    """Wilson score interval for successes among exactly trials evaluated units."""
    _integer(successes, "successes", 0)
    _integer(trials, "trials")
    _confidence(confidence)
    if successes > trials:
        raise ValueError("successes exceeds trials")
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    p = successes / trials
    denominator = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / denominator
    radius = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials**2)) / denominator
    return ConfidenceInterval(max(0.0, center - radius), min(1.0, center + radius))


@dataclass(frozen=True)
class InformativeResult:
    informative: bool
    n_units: int
    n_positives: int
    prevalence: float | None
    reasons: tuple[str, ...]


def informative_gate(
    labels: Sequence[bool],
    *,
    min_units: int,
    min_positives: int,
    prevalence_min: float,
    prevalence_max: float,
    ground_truth_available: bool = True,
) -> InformativeResult:
    """Inclusive prevalence boundaries. Empty/missing ground truth never passes."""
    labels = _labels(labels)
    _integer(min_units, "min_units")
    _integer(min_positives, "min_positives")
    if not 0 <= prevalence_min <= prevalence_max <= 1:
        raise ValueError("prevalence limits must satisfy 0 <= min <= max <= 1")
    if type(ground_truth_available) is not bool:
        raise ValueError("ground_truth_available must be boolean")
    n, positives = len(labels), sum(labels)
    prevalence = positives / n if n else None
    reasons = []
    if not ground_truth_available:
        reasons.append("missing_ground_truth")
    if n < min_units:
        reasons.append("too_few_units")
    if positives < min_positives:
        reasons.append("too_few_positives")
    if prevalence is None or not prevalence_min <= prevalence <= prevalence_max:
        reasons.append("prevalence_outside_bounds")
    return InformativeResult(not reasons, n, positives, prevalence, tuple(reasons))


def built_up_excess(
    built_up_by_barrio: Sequence[Sequence[float]],
    non_built_by_barrio: Sequence[Sequence[float]],
) -> float:
    """Pooled pixel median Z difference, preserving barrio blocks for resampling.

    A barrio may have no non-built pixels; the entire pass must contain both
    populations. Nonfinite pixels must have been masked by the caller.
    """
    if len(built_up_by_barrio) != len(non_built_by_barrio):
        raise ValueError("built and non-built blocks must align by barrio")
    built = _finite([v for block in built_up_by_barrio for v in block], "built-up Z")
    non_built = _finite([v for block in non_built_by_barrio for v in block], "non-built Z")
    return median(built) - median(non_built)


def _quantile(values: Sequence[float], probability: float) -> float:
    values = sorted(values)
    position = (len(values) - 1) * probability
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def block_bootstrap(
    barrios: Sequence[T],
    statistic: Callable[[tuple[T, ...]], Mapping[str, float]],
    *,
    replicates: int,
    seed: int,
    confidence: float = 0.95,
) -> dict[str, ConfidenceInterval]:
    """Percentile CIs from paired whole-barrio draws, never individual pixels.

    Each input is ONE evaluated barrio containing all C/K pixels and covariates.
    The callback must recompute rankings and return all paired statistics on the
    SAME draw, including radar-minus-baseline and E_C-minus-E_K differences.
    Duplicate draws are separate occurrences: the callback must not deduplicate
    barrio IDs. Preserve original barrio identity as the primary tie-break key;
    occurrence keys must not make the statistic depend on draw ordering.
    Undefined statistics fail explicitly; replicates are never dropped.
    Uses a local RNG and leaves process-global random state untouched.
    """
    barrios = tuple(barrios)
    if not barrios:
        raise ValueError("at least one barrio is required")
    _integer(replicates, "replicates", 2)
    _integer(seed, "seed", 0)
    _confidence(confidence)
    rng = random.Random(seed)
    samples: dict[str, list[float]] = {}
    for replicate in range(replicates):
        drawn = tuple(barrios[rng.randrange(len(barrios))] for _ in barrios)
        result = dict(statistic(drawn))
        if not result or any(not isinstance(key, str) for key in result):
            raise ValueError("statistic must return named values")
        if replicate == 0:
            samples = {key: [] for key in result}
        if samples.keys() != result.keys():
            raise ValueError("statistic keys changed between replicates")
        for key, value in result.items():
            if not math.isfinite(value):
                raise ValueError(f"undefined bootstrap statistic: {key}")
            samples[key].append(value)
    tail = (1 - confidence) / 2
    return {
        key: ConfidenceInterval(_quantile(values, tail), _quantile(values, 1 - tail))
        for key, values in samples.items()
    }


def beats_baseline(
    precision_difference: ConfidenceInterval,
    coevent_excess: ConfidenceInterval,
    adjusted_excess: ConfidenceInterval | None,
    *,
    control_timing: str,
    informative: bool,
) -> bool:
    """Claim a win only with positive gain AND positive C AND positive C-minus-K.

    The design's 'excludes zero' is directional: a negative precision difference
    is evidence of losing. Missing or post-event K can never establish a win.
    """
    if control_timing not in {"pre-event", "post-event", "missing"}:
        raise ValueError("unknown control timing")
    if type(informative) is not bool:
        raise ValueError("informative must be boolean")
    return (
        informative
        and control_timing == "pre-event"
        and adjusted_excess is not None
        and precision_difference.low > 0
        and coevent_excess.low > 0
        and adjusted_excess.low > 0
    )
