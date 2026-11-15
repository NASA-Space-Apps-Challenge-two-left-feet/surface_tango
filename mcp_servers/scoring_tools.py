# mcp_servers/scoring_tools.py
"""MCP tools that wrap the pure scoring library (plan 03-06, #35).

Three thin wrappers over `validation.scoring`:
  - get_earthquake_pair_set: the pre/co/control GUNW triplets from pre-registration
  - rank_first_aid_barrios:  the radar ranking + evaluation k for first aid
  - score_against_baseline:  precision@k (radar vs baseline), Wilson CIs, informative gate

These tools invent no numbers. Every threshold and weight comes from the frozen
pre-registration (`config/preregistered.yaml`), and a missing or null value raises
rather than defaulting. The pure functions below take an explicit `preregistered`
mapping so they can be unit-tested offline; `register(mcp)` wires them to a server
and loads the real config.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

# `validation/` is importable from the repo root; `src/` holds `bailasar`.
_REPO_ROOT = Path(__file__).resolve().parents[1]
for _candidate in (_REPO_ROOT, _REPO_ROOT / "src"):
    _path = str(_candidate)
    if _path not in sys.path:
        sys.path.insert(0, _path)

from validation import scoring  # noqa: E402

_TRIPLET_KEYS = ("reference_R", "coevent_C", "control_K")
_TRIPLET_EXTRAS = ("track", "geometry", "frame", "baseline_days", "baseline_mismatch")


def _section(config: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    section = config.get(name) if isinstance(config, Mapping) else None
    if not isinstance(section, Mapping):
        raise ValueError(f"pre-registration section '{name}' is missing")
    return section


def _required(mapping: Mapping[str, Any], key: str, dotted: str) -> Any:
    value = mapping.get(key) if isinstance(mapping, Mapping) else None
    if value is None:
        raise ValueError(f"pre-registration value '{dotted}' is not set")
    return value


def earthquake_pair_set(preregistered: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the pre/co/control GUNW triplets from the frozen pre-registration.

    Accepts either a single triplet mapping or a list of per-track triplets
    (config schema, #26). Raises if any R/C/K id is null or missing: the pairs
    must be filled at the hour-2 gate and frozen before this tool is usable.
    """
    quake = _section(preregistered, "quake")
    raw = quake.get("pairs")
    if raw is None:
        raise ValueError("quake.pairs is not set in the pre-registration")
    triplets = list(raw) if isinstance(raw, (list, tuple)) else [raw]
    if not triplets:
        raise ValueError("quake.pairs is empty")
    result: list[dict[str, Any]] = []
    for index, triplet in enumerate(triplets):
        if not isinstance(triplet, Mapping):
            raise ValueError(f"quake.pairs[{index}] is not a mapping")
        ids = {key: triplet.get(key) for key in _TRIPLET_KEYS}
        missing = [key for key, value in ids.items() if not value]
        if missing:
            raise ValueError(f"quake.pairs[{index}] missing granule ids: {', '.join(missing)}")
        entry: dict[str, Any] = {key: ids[key] for key in _TRIPLET_KEYS}
        for extra in _TRIPLET_EXTRAS:
            if extra in triplet:
                value = triplet[extra]
                entry[extra] = dict(value) if isinstance(value, Mapping) else value
        result.append(entry)
    return result


def rank_barrios(
    unit_ids: Sequence[str],
    dpm: Sequence[float],
    population: Sequence[float],
    distance: Sequence[float],
    *,
    preregistered: Mapping[str, Any],
    top_k_only: bool = True,
) -> dict[str, Any]:
    """Rank evaluated barrios for first aid (the radar ranking), with the evaluation k.

    `dpm` is each unit's median built-up Z from the upstream pipeline. The access
    weight and the k rule come from the pre-registration; no threshold is invented.
    """
    quake = _section(preregistered, "quake")
    access_weight = _required(
        _section(quake, "ranking"), "access_weight", "quake.ranking.access_weight"
    )
    k_rule = _section(quake, "k_rule")
    fraction = _required(k_rule, "fraction", "quake.k_rule.fraction")
    minimum = _required(k_rule, "minimum", "quake.k_rule.minimum")

    rankings = scoring.rank_units(unit_ids, dpm, population, distance, access_weight=access_weight)
    k = scoring.evaluation_k(len(rankings.radar), fraction=fraction, minimum=minimum)
    radar = [{"unit_id": unit.unit_id, "score": unit.score} for unit in rankings.radar]
    baseline = [{"unit_id": unit.unit_id, "score": unit.score} for unit in rankings.baseline]
    return {
        "k": k,
        "first_aid_barrios": radar[:k] if top_k_only else radar,
        "radar_ranking": radar,
        "baseline_ranking": baseline,
    }


def score_barrios(
    radar_ordered_labels: Sequence[bool],
    baseline_ordered_labels: Sequence[bool],
    *,
    preregistered: Mapping[str, Any],
    ground_truth_available: bool = True,
) -> dict[str, Any]:
    """Precision@k for radar vs baseline, each with a Wilson CI, plus the informative gate.

    Each label vector must already be in its ranking's descending order and cover
    the same evaluated units. k, and the gate thresholds, come from pre-registration.
    """
    quake = _section(preregistered, "quake")
    k_rule = _section(quake, "k_rule")
    fraction = _required(k_rule, "fraction", "quake.k_rule.fraction")
    minimum = _required(k_rule, "minimum", "quake.k_rule.minimum")
    informative = _section(quake, "informative")

    radar_labels = [bool(label) for label in radar_ordered_labels]
    baseline_labels = [bool(label) for label in baseline_ordered_labels]
    if len(radar_labels) != len(baseline_labels):
        raise ValueError("radar and baseline label vectors must cover the same evaluated units")

    k = scoring.evaluation_k(len(radar_labels), fraction=fraction, minimum=minimum)
    radar_precision = scoring.precision_at_k(radar_labels, k)
    baseline_precision = scoring.precision_at_k(baseline_labels, k)
    radar_ci = scoring.wilson_interval(sum(radar_labels[:k]), k)
    baseline_ci = scoring.wilson_interval(sum(baseline_labels[:k]), k)
    gate = scoring.informative_gate(
        radar_labels,
        min_units=_required(informative, "min_units", "quake.informative.min_units"),
        min_positives=_required(informative, "min_positives", "quake.informative.min_positives"),
        prevalence_min=_required(informative, "prevalence_min", "quake.informative.prevalence_min"),
        prevalence_max=_required(informative, "prevalence_max", "quake.informative.prevalence_max"),
        ground_truth_available=ground_truth_available,
    )
    return {
        "k": k,
        "radar_precision_at_k": radar_precision,
        "baseline_precision_at_k": baseline_precision,
        "precision_difference": radar_precision - baseline_precision,
        "radar_wilson": {"low": radar_ci.low, "high": radar_ci.high},
        "baseline_wilson": {"low": baseline_ci.low, "high": baseline_ci.high},
        "informative": gate.informative,
        "informative_reasons": list(gate.reasons),
        "n_units": gate.n_units,
        "n_positives": gate.n_positives,
        "prevalence": gate.prevalence,
    }


def _load_preregistered() -> Mapping[str, Any]:
    """Load the real pre-registration config for a running server."""
    from bailasar.config import get_config

    return get_config().preregistered


def register(mcp: Any) -> None:
    """Register the three scoring tools on a FastMCP server.

    The tool names are the plan 03-06 names; each delegates to the module-level
    pure function (distinct name) so the real config is loaded only at call time.
    """

    @mcp.tool
    def get_earthquake_pair_set() -> list[dict[str, Any]]:
        """Return the pre/co/control GUNW triplets from the frozen pre-registration."""
        return earthquake_pair_set(_load_preregistered())

    @mcp.tool
    def rank_first_aid_barrios(
        unit_ids: list[str],
        dpm: list[float],
        population: list[float],
        distance: list[float],
        top_k_only: bool = True,
    ) -> dict[str, Any]:
        """Rank evaluated barrios for first aid using the pre-registered access weight and k."""
        return rank_barrios(
            unit_ids,
            dpm,
            population,
            distance,
            preregistered=_load_preregistered(),
            top_k_only=top_k_only,
        )

    @mcp.tool
    def score_against_baseline(
        radar_ordered_labels: list[bool],
        baseline_ordered_labels: list[bool],
        ground_truth_available: bool = True,
    ) -> dict[str, Any]:
        """Precision@k (radar vs baseline) with Wilson CIs and the informative gate."""
        return score_barrios(
            radar_ordered_labels,
            baseline_ordered_labels,
            preregistered=_load_preregistered(),
            ground_truth_available=ground_truth_available,
        )
