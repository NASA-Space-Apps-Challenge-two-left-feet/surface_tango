"""Evidence-envelope builders for the MCP hazard tools (the #122 contract).

The fusion tools are **adapters over a serialized evidence artifact**, never a
place where numbers are computed or invented. The data lane writes
``local_cache/<aoi>/<hazard>_evidence*.json`` during the cache build (from the
same measured run that produces ``reports/<hazard>.md``); these builders read
that artifact and return the outward envelope. If the artifact is absent the
tool returns ``not cached``; a number without a denominator and a source is
never emitted.

Envelope (every outcome, including gates and errors):
    state, tool, domain, reason, calibrated, uncalibrated, data,
    provenance, unavailable, error

Rules honoured here:
- ``calibrated`` is always ``False`` for this integration (a CLI calibration
  artifact does not calibrate the MCP adapter).
- Every area value carries ``pixel_count``, ``valid_pixel_count``,
  ``pixel_area_m2``, ``source_ids`` and ``sensitivity_range`` (or null + reason).
- Quake C-pair / co-event statistics stay sealed until the pre-registration is
  frozen; the builder is told ``is_frozen`` and withholds otherwise.
- Alert thresholds come only from ``config/bailasar.yaml`` ``hazard_tools.*``;
  a missing key is an ``error`` naming the dotted keys, never a default GREEN.
- Renderers/hotspots the modules do not expose are ``null`` with an
  ``unavailable`` reason, never an AOI-centroid substitute.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

ENVELOPE_FIELDS = (
    "state",
    "tool",
    "domain",
    "reason",
    "calibrated",
    "uncalibrated",
    "data",
    "provenance",
    "unavailable",
    "error",
)

# Products the merged #98/#109/#111 modules do not expose to this adapter.
_ABSENT_RENDER = {
    "gee_xyz_tile_url": "no GEE tile renderer in the merged module; writes local rasters only",
    "diagnostic_rgb_tile_url": "no RGB tile renderer; the polarimetric decomposition bands are obsolete",
    "hotspot_coordinates": "no hotspot reduction in the merged module; never substitute the AOI centroid",
}


class EvidenceError(ValueError):
    """The artifact is present but malformed, or required config is missing."""


def _envelope(state: str, tool: str, domain: str, **fields: Any) -> dict[str, Any]:
    env = {
        "state": state,
        "tool": tool,
        "domain": domain,
        "reason": None,
        "calibrated": False,
        "uncalibrated": [],
        "data": None,
        "provenance": None,
        "unavailable": {},
        "error": None,
    }
    env.update(fields)
    assert set(env) == set(ENVELOPE_FIELDS), sorted(set(env) ^ set(ENVELOPE_FIELDS))
    return env


def not_cached(tool: str, domain: str, reason: str) -> dict[str, Any]:
    return _envelope("not cached", tool, domain, reason=reason, error="not cached")


def errored(tool: str, domain: str, reason: str, missing_keys: list[str] | None = None) -> dict:
    err: dict[str, Any] = {"message": reason}
    if missing_keys:
        err["missing_keys"] = missing_keys
    return _envelope("error", tool, domain, reason=reason, error=err)


def load_artifact(path: Path) -> dict[str, Any] | None:
    """Read and shallow-validate a serialized evidence artifact; None if absent."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvidenceError(f"unreadable evidence artifact: {exc}") from None
    if not isinstance(data, dict) or "schema" not in data or "provenance" not in data:
        raise EvidenceError("evidence artifact missing schema or provenance")
    return data


def _unavailable(reason: str) -> dict[str, str]:
    return {"availability": "unavailable", "reason": reason}


def _render_fields() -> tuple[dict[str, None], dict[str, dict]]:
    """The three render/hotspot fields as nulls plus their unavailable entries."""
    data = dict.fromkeys(_ABSENT_RENDER)
    unavailable = {name: _unavailable(reason) for name, reason in _ABSENT_RENDER.items()}
    return data, unavailable


# --------------------------------------------------------------------------- #
# Alert policy — thresholds come only from config, missing keys are an error    #
# --------------------------------------------------------------------------- #
def _alert_block(config: dict[str, Any], domain: str) -> tuple[dict | None, list[str]]:
    """(levels, missing_keys). levels is None when any required key is absent/invalid."""
    keys = [f"hazard_tools.{domain}.alert.{edge}_above" for edge in ("red", "orange", "yellow")]
    node = (config.get("hazard_tools") or {}).get(domain, {}).get("alert", {})
    values, missing = {}, []
    for edge, dotted in zip(("red", "orange", "yellow"), keys, strict=True):
        v = node.get(f"{edge}_above")
        if isinstance(v, bool) or not isinstance(v, int | float):
            missing.append(dotted)
        else:
            values[edge] = float(v)
    if missing or not (values["red"] > values["orange"] > values["yellow"]):
        return None, (missing or keys)
    return values, []


def _grade(value: float, levels: dict[str, float]) -> str:
    if value > levels["red"]:
        return "RED"
    if value > levels["orange"]:
        return "ORANGE"
    if value > levels["yellow"]:
        return "YELLOW"
    return "GREEN"


# --------------------------------------------------------------------------- #
# Area evidence                                                                 #
# --------------------------------------------------------------------------- #
def _area_evidence(block: dict[str, Any] | None, required: tuple[str, ...]) -> dict[str, Any]:
    """Validate one area-evidence object; raise if a required numeric/source is absent."""
    if block is None:
        return None
    for field in ("value_ha", "pixel_count", "valid_pixel_count", "pixel_area_m2"):
        v = block.get(field)
        if isinstance(v, bool) or not isinstance(v, int | float):
            raise EvidenceError(f"area evidence missing numeric {field}")
    ids = block.get("source_ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i for i in ids):
        raise EvidenceError("area evidence missing source_ids")
    out = {k: block[k] for k in ("value_ha", "pixel_count", "valid_pixel_count", "pixel_area_m2")}
    out["source_ids"] = ids
    out["measurement"] = block.get("measurement", "measured")
    out["command"] = block.get("command")
    if "sensitivity_range" in block and block["sensitivity_range"] is not None:
        out["sensitivity_range"] = block["sensitivity_range"]
        out["sensitivity_scenarios"] = block.get("sensitivity_scenarios", [])
        out["sensitivity_reason"] = None
    else:
        out["sensitivity_range"] = None
        out["sensitivity_scenarios"] = None
        out["sensitivity_reason"] = block.get("sensitivity_reason", "sweep not serialized")
    for extra in required:
        if extra not in block:
            raise EvidenceError(f"area evidence missing {extra}")
        out[extra] = block[extra]
    return out


# --------------------------------------------------------------------------- #
# Flood                                                                         #
# --------------------------------------------------------------------------- #
def build_flood_envelope(artifact: dict[str, Any], config: dict[str, Any], tool: str) -> dict:
    data, unavailable = _render_fields()
    baseline = artifact.get("baseline")
    if not isinstance(baseline, dict) or "accepted" not in baseline:
        raise EvidenceError("flood artifact missing baseline")
    water = _area_evidence(artifact.get("water_extent"), ("reference_date",))
    if water is None:
        raise EvidenceError("flood artifact missing water_extent")
    class1 = _area_evidence(artifact.get("open_water_flood"), ("reference_date", "target_date"))
    class2 = _area_evidence(
        artifact.get("subcanopy_double_bounce_flood"), ("reference_date", "target_date")
    )

    data.update(
        baseline=baseline,
        dates=artifact.get("dates", []),
        area_evidence={
            "water_extent_ha": water,
            "open_water_flood_ha": class1,
            "subcanopy_double_bounce_flood_ha": class2,
            "total_inundated_ha": None,
        },
        sentinel1_comparison=artifact.get("sentinel1_comparison"),
        rainfall=artifact.get("rainfall"),
        physical_radar_driver=(
            "NISAR L-band HH open-water change against the driest valid date, HAND-gated; "
            "classes are uncalibrated proxies and the change classification is degenerate "
            "when the dry reference has too few valid pixels."
        ),
    )

    # total inundated area is withheld unless a verified union support is serialized
    total = artifact.get("total_inundated")
    if total is None:
        unavailable["area_evidence.total_inundated_ha"] = _unavailable(
            "no verified union support over the differing Class 1 / Class 2 valid domains"
        )

    # alert on the total change area only; without that metric alerts are null
    levels, missing = _alert_block(config, "flood")
    if missing and total is not None:
        return errored(tool, "flood", "missing flood alert thresholds", missing)
    if total is None:
        data.update(
            alert_level=None,
            alert_reason="total change-area metric unavailable (degenerate change classification)",
            alert_policy=None,
        )
    else:
        data.update(
            alert_level=_grade(total["value_ha"], levels),
            alert_reason="graded on total change area (ha), strict >",
            alert_policy={
                "metric": "total_inundated_ha",
                "thresholds": levels,
                "compare": "strict_gt",
            },
        )

    reason = None if baseline["accepted"] else baseline.get("reason", "baseline rejected")
    state = "live" if baseline["accepted"] else "gate result"
    return _envelope(
        state,
        tool,
        "flood",
        reason=reason,
        uncalibrated=artifact.get("uncalibrated", []),
        data=data,
        provenance=artifact["provenance"],
        unavailable=unavailable,
    )


# --------------------------------------------------------------------------- #
# Landslide                                                                     #
# --------------------------------------------------------------------------- #
def build_landslide_envelope(artifact: dict[str, Any], config: dict[str, Any], tool: str) -> dict:
    data, unavailable = _render_fields()
    verdict = artifact.get("noise_floor_verdict")
    if not isinstance(verdict, dict) or "outcome" not in verdict:
        raise EvidenceError("landslide artifact missing noise_floor_verdict")

    data.update(
        noise_floor_verdict=verdict,
        pairs=artifact.get("pairs", []),
        key_quantitative_metrics=artifact.get("key_quantitative_metrics"),
        area_evidence=None,
        area_reason="no area is computed for the landslide verdict",
        sensitivity_range=None,
        sensitivity_reason="no justified landslide sensitivity sweep exists; residual RMS is not an interval",
        sensitivity_scenarios=None,
        rainfall=artifact.get("rainfall"),
        physical_radar_driver=(
            "L-band GUNW LOS, ionosphere screen subtracted, stratified-tropo corrected, projected "
            "downslope; a rate is kept only above the per-pair residual RMS with sign agreement "
            "across independent pairs, calibrated against a sign-flip null."
        ),
    )

    outcome = verdict["outcome"]
    # alerts only after a supported motion verdict with a valid configured metric
    if outcome != "motion":
        data.update(
            alert_level=None,
            alert_reason=f"no supported motion verdict (outcome={outcome})",
            alert_policy=None,
        )
    else:
        levels, missing = _alert_block(config, "landslide")
        if missing:
            return errored(tool, "landslide", "missing landslide alert thresholds", missing)
        stat = verdict.get("retained_rate_stat_mm_yr")
        if not isinstance(stat, int | float) or isinstance(stat, bool):
            raise EvidenceError("motion verdict missing retained_rate_stat_mm_yr")
        data.update(
            alert_level=_grade(float(stat), levels),
            alert_reason="graded on the retained-rate statistic (mm/yr), strict >",
            alert_policy={
                "metric": "retained_rate_stat_mm_yr",
                "thresholds": levels,
                "compare": "strict_gt",
            },
        )

    branch_state = {
        "missing": "gate result",
        "too_few_pairs": "gate result",
        "no_motion": "gate result",
        "motion": "live",
    }.get(outcome)
    if branch_state is None:
        raise EvidenceError(f"unknown verdict outcome {outcome!r}")
    return _envelope(
        branch_state,
        tool,
        "landslide",
        reason=verdict.get("text"),
        uncalibrated=artifact.get("uncalibrated", []),
        data=data,
        provenance=artifact["provenance"],
        unavailable=unavailable,
    )


# --------------------------------------------------------------------------- #
# Earthquake — C/K statistics sealed until the pre-registration freeze           #
# --------------------------------------------------------------------------- #
def build_quake_envelope(
    artifact: dict[str, Any], config: dict[str, Any], tool: str, *, is_frozen: bool
) -> dict:
    data, unavailable = _render_fields()
    counts = artifact.get("counts")
    if not isinstance(counts, dict) or "valid_pixels" not in counts:
        raise EvidenceError("quake artifact missing counts")

    data.update(
        pairs=artifact.get("pairs", []),
        counts=counts,
        units=artifact.get("units"),
        scorecard=artifact.get(
            "scorecard", {"state": "uninformative", "reason": "no barrio labels"}
        ),
        physical_radar_driver=(
            "Co-event coherence loss on non-built pixels as a damage proxy; the baseline mismatch "
            "(C 24 d vs R/K 12 d) is disclosed beside every number."
        ),
    )
    if is_frozen:
        data["coherence_statistics"] = artifact.get("coherence_statistics")
    else:
        data["coherence_statistics"] = None
        unavailable["coherence_statistics"] = _unavailable(
            "C-pair and K-control statistics are sealed until the pre-registration freeze "
            "(validation/README.md, deviation 1)"
        )
    # quake has no displayable alert: the scorecard is the verdict
    data.update(
        alert_level=None,
        alert_reason="quake uses the scorecard, not an area alert",
        alert_policy=None,
    )
    return _envelope(
        "live",
        tool,
        "earthquake",
        reason="damage proxy counts only; scorecard uninformative"
        if not is_frozen
        else "damage proxy counts; statistics unsealed after freeze",
        uncalibrated=artifact.get("uncalibrated", []),
        data=data,
        provenance=artifact["provenance"],
        unavailable=unavailable,
    )
