"""Response posture for one AOI, read from evidence envelopes.

This is the decision layer. It does not compute a new hazard number, a
population, a building count, or an aid quantity. It copies fields the
#122 envelopes already carry and maps them to an evidence-state light.

Lights, highest rank first:

- ``deploy_assessment`` — a configured red or orange alert on a product
  whose ``uncalibrated`` list is empty, and, for an earthquake, a scorecard
  that is not in ``scorecard_blocks_deploy``.
- ``provisional`` — a measured extent or a motion verdict that is not a
  dispatch basis (alert unset, below the dispatch alerts, or uncalibrated).
- ``not_assessed`` — missing artifact, error, too few pairs, or an
  earthquake scorecard that does not support a damage call.
- ``monitor`` — a landslide ``no_motion`` verdict only. Not a safety clearance.

The #122 adapter sets ``calibrated`` false on every envelope, including the
Aburrá null. Deploy therefore reads the ``uncalibrated`` list and the alert,
not that flag. A non-empty ``uncalibrated`` list blocks dispatch.

Out-of-scope hazards are reported and do not enter the rank. They are not
a clearance. A monitor light does not clear an in-scope hazard that is
``not_assessed``. Quake pixel counts stay an analyzed window: this module
never multiplies them into hectares.

Action labels, lifelines, and lines of effort come from ``config/bailasar.yaml``
``decision:``. Lifeline rows stay ``not_assessed`` until an envelope carries
a service observation. Doctrine orders the response. It does not set a
hectare, population, or dollar trigger, and it is not a USGS PAGER color.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from mcp_servers import evidence

ROOT = Path(__file__).resolve().parents[1]
OPS_CONFIG = ROOT / "config" / "bailasar.yaml"
PREREG = ROOT / "config" / "preregistered.yaml"

LIGHTS = ("deploy_assessment", "provisional", "not_assessed", "monitor")
ACTIONS = ("no_dispatch", "preposition_assessment", "dispatch_life_safety")
_AREA_FIELDS = ("value_ha", "pixel_count", "valid_pixel_count", "pixel_area_m2")
_SOCIAL_KEYS = ("population", "people", "worldpop", "buildings", "osm_buildings")
_ECON_KEYS = ("loss_usd", "economic_loss", "damage_usd")
_FLOOD_COMPONENTS = (
    ("water_extent_ha", "provisional_open_water"),
    ("total_inundated_ha", "change_area"),
    ("open_water_flood_ha", "open_water_flood"),
    ("subcanopy_double_bounce_flood_ha", "subcanopy_double_bounce_flood"),
)


class DecisionConfigError(ValueError):
    """``decision:`` is missing or does not name the lights and actions."""


def _ops() -> dict[str, Any]:
    return yaml.safe_load(OPS_CONFIG.read_text(encoding="utf-8")) or {}


def _frozen() -> bool:
    try:
        data = yaml.safe_load(PREREG.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return False
    return str(data.get("status", "draft")).strip().lower() == "frozen"


def _is_num(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _unavailable(reason: str) -> dict[str, str]:
    return {"availability": "unavailable", "reason": reason}


def _require(cfg: dict[str, Any], key: str) -> Any:
    if key not in cfg:
        raise DecisionConfigError(f"decision.{key} is missing")
    return cfg[key]


def decision_config(ops: dict[str, Any]) -> dict[str, Any]:
    """The operational ``decision:`` block, or an error naming the gap."""
    raw = ops.get("decision")
    if not isinstance(raw, dict):
        raise DecisionConfigError("decision block is missing from the operational config")
    lights = _require(raw, "lights")
    rank = _require(raw, "rank")
    actions = _require(raw, "actions")
    light_action = _require(raw, "light_action")
    if set(lights) != set(LIGHTS) or list(rank) != list(LIGHTS):
        raise DecisionConfigError("decision.rank must list the four lights, highest first")
    if set(actions) != set(ACTIONS):
        raise DecisionConfigError("decision.actions must name the three response actions")
    if any(light_action.get(light) not in ACTIONS for light in LIGHTS):
        raise DecisionConfigError("decision.light_action must map every light to an action")
    rules = _require(raw, "rules")
    for key in ("dispatch_alerts", "monitor_outcomes", "scorecard_blocks_deploy"):
        if not isinstance(rules.get(key), list) or not rules[key]:
            raise DecisionConfigError(f"decision.rules.{key} must be a non-empty list")
    for key in (
        "domains",
        "aois",
        "extent_labels",
        "unavailable",
        "priorities",
        "lines_of_effort",
        "lifelines",
        "check_first",
        "hazard_notes",
        "product_kind",
        "product_labels",
        "board_note",
        "chips",
        "damage_level",
        "response_packages",
        "doctrine",
        "not_a",
        "clearance",
        "priority_status",
        "out_of_scope_reason",
        "lifeline_reason",
        "numbers_policy",
    ):
        _require(raw, key)
    for aoi, spec in raw["aois"].items():
        if not isinstance(spec, dict) or not spec.get("hazards") or not spec.get("label"):
            raise DecisionConfigError(f"decision.aois.{aoi} needs a label and hazards")
        if "earthquake" in spec["hazards"] and not spec.get("quake_tracks"):
            raise DecisionConfigError(f"decision.aois.{aoi} needs quake_tracks")
    kinds = raw["product_kind"]
    for domain in raw["domains"]:
        kind = kinds.get(domain) if isinstance(kinds, dict) else None
        if kind not in raw["product_labels"] or domain not in raw["response_packages"]:
            raise DecisionConfigError(f"decision.product_kind.{domain} is incomplete")
        if domain not in raw["damage_level"]:
            raise DecisionConfigError(f"decision.damage_level.{domain} is missing")
    return raw


def _env_reason(env: dict[str, Any]) -> str:
    err = env.get("error")
    if isinstance(err, dict) and err.get("message"):
        return str(err["message"])
    if isinstance(err, str) and err:
        return err
    data = env.get("data") if isinstance(env.get("data"), dict) else {}
    if data.get("alert_reason"):
        return str(data["alert_reason"])
    if env.get("reason"):
        return str(env["reason"])
    return "no reason on the envelope"


def _blocks_dispatch(env: dict[str, Any], domain: str) -> bool:
    raw = env.get("uncalibrated") or []
    if not isinstance(raw, list):
        return True
    return bool(raw) or domain in raw


def _copy_area(block: Any) -> dict[str, Any] | None:
    if not isinstance(block, dict):
        return None
    if not all(_is_num(block.get(field)) for field in _AREA_FIELDS):
        return None
    ids = block.get("source_ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i for i in ids):
        return None
    copied: dict[str, Any] = {field: block[field] for field in _AREA_FIELDS}
    copied["source_ids"] = list(ids)
    if block.get("measurement") in {"measured", "estimate"}:
        copied["measurement"] = block["measurement"]
    if isinstance(block.get("command"), str) and block["command"]:
        copied["command"] = block["command"]
    return copied


def _labeled_area(block: Any, kind: str, cfg: dict[str, Any]) -> dict[str, Any] | None:
    copied = _copy_area(block)
    if copied is None:
        return None
    copied["availability"] = "measured"
    copied["represents"] = kind
    copied["label"] = cfg["extent_labels"][kind]
    return copied


def _copy_named(data: dict[str, Any], keys: tuple[str, ...], reason: str) -> dict[str, Any]:
    for key in keys:
        block = data.get(key)
        if not isinstance(block, dict) or not _is_num(block.get("value")):
            continue
        ids = block.get("source_ids")
        if not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i for i in ids):
            continue
        copied: dict[str, Any] = {
            "availability": "measured",
            "field": key,
            "value": block["value"],
            "source_ids": list(ids),
        }
        if isinstance(block.get("unit"), str):
            copied["unit"] = block["unit"]
        if isinstance(block.get("command"), str):
            copied["command"] = block["command"]
        return copied
    return _unavailable(reason)


def _window(data: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any] | None:
    counts = data.get("counts")
    if not isinstance(counts, dict) or isinstance(counts.get("valid_pixels"), bool):
        return None
    if not isinstance(counts.get("valid_pixels"), int):
        return None
    window: dict[str, Any] = {
        "availability": "measured",
        "represents": "analyzed_window",
        "label": cfg["extent_labels"]["analyzed_window"],
        "valid_pixels": counts["valid_pixels"],
        "combined": False,
    }
    if isinstance(counts.get("window_pixels"), int) and not isinstance(
        counts.get("window_pixels"), bool
    ):
        window["window_pixels"] = counts["window_pixels"]
    pixel_area = counts.get("pixel_area_m2")
    if _is_num(pixel_area):
        window["pixel_area_m2"] = pixel_area
    return window


def _kinematics(verdict: dict[str, Any]) -> dict[str, Any] | None:
    rate = verdict.get("retained_rate_stat_mm_yr")
    if not _is_num(rate):
        return None
    return {"retained_rate_stat_mm_yr": rate, "unit": "mm/yr"}


def _dead(domain: str, env: dict[str, Any] | None, cfg: dict[str, Any]) -> dict[str, Any]:
    reason = _env_reason(env) if env else cfg["unavailable"]["missing"]
    state = env.get("state") if env else "not cached"
    if state not in {"not cached", "error", "gate result", "live"}:
        state = "error" if env and env.get("error") else "not cached"
    return {
        "light": "not_assessed",
        "evidence_state": state,
        "reason": reason,
        "alert_level": None,
        "extent": _unavailable(reason),
        "kinematics": None,
        "social_impact": _unavailable(cfg["unavailable"]["social"]),
        "economic_impact": _unavailable(cfg["unavailable"]["economic"]),
        "tool": env.get("tool") if env else None,
        "track": env.get("track") if env else None,
    }


def _reading(domain: str, env: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """One envelope to one light. Pixel windows are never turned into hectares."""
    state = env.get("state")
    if (
        state in {"not cached", "error"}
        or env.get("error")
        or not isinstance(env.get("data"), dict)
    ):
        return _dead(domain, env, cfg)
    data = env["data"]
    rules = cfg["rules"]
    social = _copy_named(data, _SOCIAL_KEYS, cfg["unavailable"]["social"])
    economic = _copy_named(data, _ECON_KEYS, cfg["unavailable"]["economic"])
    base = {
        "evidence_state": state,
        "alert_level": data.get("alert_level"),
        "social_impact": social,
        "economic_impact": economic,
        "tool": env.get("tool"),
        "track": env.get("track"),
        "kinematics": None,
    }
    dispatch = data.get("alert_level") in rules["dispatch_alerts"] and not _blocks_dispatch(
        env, domain
    )

    if domain == "earthquake":
        scorecard = data.get("scorecard") if isinstance(data.get("scorecard"), dict) else {}
        score_state = scorecard.get("state")
        blocked = score_state in rules["scorecard_blocks_deploy"] or not score_state
        window = _window(data, cfg)
        extent = window or _unavailable(cfg["unavailable"]["area"])
        if dispatch and not blocked:
            light = "deploy_assessment"
            reason = data.get("alert_reason") or "configured alert on an unblocked scorecard"
        else:
            light = "not_assessed"
            reason = scorecard.get("reason") or data.get("alert_reason") or _env_reason(env)
        return {**base, "light": light, "reason": reason, "extent": extent}

    if domain == "landslide":
        verdict = (
            data.get("noise_floor_verdict")
            if isinstance(data.get("noise_floor_verdict"), dict)
            else {}
        )
        outcome = verdict.get("outcome")
        kinematics = _kinematics(verdict)
        area = _copy_area(data.get("area_evidence"))
        if area is None:
            extent = _unavailable(str(data.get("area_reason") or cfg["unavailable"]["area"]))
        else:
            extent = {
                **area,
                "availability": "measured",
                "represents": "landslide_area",
                "label": cfg["extent_labels"]["landslide_area"],
            }
        if outcome in rules["monitor_outcomes"]:
            light, reason = "monitor", cfg["clearance"]
        elif outcome == "motion" and dispatch:
            light = "deploy_assessment"
            reason = data.get("alert_reason") or "configured alert on supported motion"
        elif outcome == "motion":
            light = "provisional"
            reason = (
                "motion is recorded, and the alert is unset, below dispatch, or the product "
                "is uncalibrated"
            )
        else:
            light = "not_assessed"
            reason = data.get("alert_reason") or _env_reason(env)
        return {
            **base,
            "light": light,
            "reason": reason,
            "extent": extent,
            "kinematics": kinematics,
        }

    areas = data.get("area_evidence") if isinstance(data.get("area_evidence"), dict) else {}
    components = []
    for key, kind in _FLOOD_COMPONENTS:
        labeled = _labeled_area(areas.get(key), kind, cfg)
        if labeled is not None:
            components.append(labeled)
    total = next((c for c in components if c["represents"] == "change_area"), None)
    water = next((c for c in components if c["represents"] == "provisional_open_water"), None)
    headline = total or water
    if headline is None:
        return {
            **base,
            "light": "not_assessed",
            "reason": data.get("alert_reason") or cfg["unavailable"]["area"],
            "extent": _unavailable(cfg["unavailable"]["area"]),
        }
    if dispatch and total is not None:
        light = "deploy_assessment"
        reason = data.get("alert_reason") or "configured alert on total change area"
    else:
        light = "provisional"
        reason = data.get("alert_reason") or cfg["extent_labels"]["provisional_open_water"]
    extent = {**headline, "components": components, "combined": False}
    return {**base, "light": light, "reason": reason, "extent": extent}


def _higher(rank: list[str], left: str, right: str) -> str:
    return left if rank.index(left) <= rank.index(right) else right


def _out_of_scope(domain: str, cfg: dict[str, Any]) -> dict[str, Any]:
    reason = cfg["out_of_scope_reason"]
    return {
        "domain": domain,
        "in_scope": False,
        "light": "out_of_scope",
        "evidence_state": None,
        "reason": reason,
        "alert_level": None,
        "extent": _unavailable(reason),
        "kinematics": None,
        "social_impact": _unavailable(cfg["unavailable"]["social"]),
        "economic_impact": _unavailable(cfg["unavailable"]["economic"]),
        "parts": [],
        "note": cfg["hazard_notes"].get(domain),
    }


def _domain_row(
    domain: str, envelopes: list[dict[str, Any]], cfg: dict[str, Any]
) -> dict[str, Any]:
    if not envelopes:
        blank = _dead(domain, None, cfg)
        blank.update(domain=domain, in_scope=True, parts=[], note=cfg["hazard_notes"].get(domain))
        return blank
    parts = [_reading(domain, env, cfg) for env in envelopes]
    light = parts[0]["light"]
    for part in parts[1:]:
        light = _higher(cfg["rank"], light, part["light"])
    social = next(
        (p["social_impact"] for p in parts if p["social_impact"]["availability"] == "measured"),
        None,
    )
    economic = next(
        (p["economic_impact"] for p in parts if p["economic_impact"]["availability"] == "measured"),
        None,
    )
    if domain == "earthquake":
        windows = [p["extent"] for p in parts if p["extent"].get("represents") == "analyzed_window"]
        extent: dict[str, Any]
        if not windows:
            extent = _unavailable(cfg["unavailable"]["area"])
        elif len(windows) == 1:
            extent = windows[0]
        else:
            extent = {
                "availability": "measured",
                "represents": "analyzed_window",
                "label": cfg["extent_labels"]["analyzed_window"],
                "combined": False,
                "reason": "Track windows are listed separately and are not added.",
                "parts": [
                    {
                        "track": p.get("track"),
                        **{k: p["extent"][k] for k in p["extent"] if k != "label"},
                    }
                    for p in parts
                    if p["extent"].get("represents") == "analyzed_window"
                ],
            }
    else:
        chosen = next(
            (
                p
                for p in parts
                if p["light"] == light and p["extent"].get("availability") == "measured"
            ),
            None,
        )
        extent = chosen["extent"] if chosen else parts[0]["extent"]
    kinematics = next((p["kinematics"] for p in parts if p["kinematics"]), None)
    reason = next(p["reason"] for p in parts if p["light"] == light)
    return {
        "domain": domain,
        "in_scope": True,
        "light": light,
        "evidence_state": _panel([p["evidence_state"] for p in parts]),
        "reason": reason,
        "alert_level": next((p["alert_level"] for p in parts if p["light"] == light), None),
        "extent": extent,
        "kinematics": kinematics,
        "social_impact": social or _unavailable(cfg["unavailable"]["social"]),
        "economic_impact": economic or _unavailable(cfg["unavailable"]["economic"]),
        "parts": parts,
        "note": cfg["hazard_notes"].get(domain),
    }


def _panel(states: list[str | None]) -> str:
    present = [s for s in states if s]
    if not present:
        return "not cached"
    if "live" in present:
        return "live"
    if "gate result" in present:
        return "gate result"
    if "error" in present:
        return "error"
    return "not cached"


def _first_measured(rows: list[dict[str, Any]], field: str, reason: str) -> dict[str, Any]:
    for row in rows:
        impact = row.get(field) or {}
        if impact.get("availability") == "measured":
            return {**impact, "combined": False, "note": "Not summed across hazards or tracks."}
    return _unavailable(reason)


def _action_block(posture: str, cfg: dict[str, Any]) -> dict[str, Any]:
    action_id = cfg["light_action"][posture]
    spec = cfg["actions"][action_id]
    return {"id": action_id, "label": spec["label"], "detail": spec["detail"]}


def _priorities(action_id: str, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    status = cfg["priority_status"][action_id]
    rows = []
    for item in cfg["priorities"]:
        rows.append(
            {
                "id": item["id"],
                "label": item["label"],
                "detail": item["detail"],
                "status": status,
                "quantity": _unavailable(cfg["unavailable"]["quantity"]),
            }
        )
    return rows


def _lines(action_id: str, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    status = cfg["priority_status"][action_id]
    rows = []
    for item in cfg["lines_of_effort"]:
        rows.append(
            {
                "id": item["id"],
                "esf": item["esf"],
                "label": item["label"],
                "detail": item["detail"],
                "status": status,
                "quantity": _unavailable(cfg["unavailable"]["quantity"]),
            }
        )
    return rows


def _lifelines(scope: list[str], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    check: set[str] = set()
    for domain in scope:
        check.update(cfg["check_first"].get(domain) or [])
    rows = []
    for item in cfg["lifelines"]:
        rows.append(
            {
                "id": item["id"],
                "label": item["label"],
                "status": "not_assessed",
                "check_first": item["id"] in check,
                "reason": cfg["lifeline_reason"],
            }
        )
    return rows


def _provenance(envelopes: list[dict[str, Any]]) -> dict[str, Any]:
    granule_ids: list[str] = []
    commands: list[str] = []
    tools: list[str] = []
    for env in envelopes:
        prov = env.get("provenance") if isinstance(env.get("provenance"), dict) else {}
        for granule_id in prov.get("granule_ids") or []:
            if isinstance(granule_id, str) and granule_id not in granule_ids:
                granule_ids.append(granule_id)
        command = prov.get("command")
        if isinstance(command, str) and command and command not in commands:
            commands.append(command)
        tool = env.get("tool")
        if isinstance(tool, str) and tool not in tools:
            tools.append(tool)
    return {"granule_ids": granule_ids, "commands": commands, "tools": tools}


def _product_kind(scope: list[str], cfg: dict[str, Any]) -> str:
    kinds = [cfg["product_kind"][domain] for domain in scope if domain in cfg["product_kind"]]
    if kinds and all(kind == kinds[0] for kind in kinds):
        return kinds[0]
    return "mixed"


def _damage_level(domain: str | None, cfg: dict[str, Any]) -> dict[str, str]:
    reason = cfg["damage_level"][domain] if domain in cfg["damage_level"] else cfg["board_note"]
    return {"availability": "unavailable", "label": "Not classified", "reason": reason}


def _response_package(
    domain: str | None, action_id: str, cfg: dict[str, Any]
) -> list[dict[str, Any]]:
    """Help lines name where to look. They never carry a quantity."""
    items = cfg["response_packages"].get(domain) if domain else None
    if not isinstance(items, list):
        return []
    status = cfg["priority_status"][action_id]
    quantity = _unavailable(cfg["unavailable"]["quantity"])
    return [
        {
            "id": item["id"],
            "help": item["help"],
            "look": item["look"],
            "status": status,
            "quantity": quantity,
        }
        for item in items
    ]


def _chip(
    product_kind: str,
    extent: dict[str, Any],
    posture_label: str,
    state: str,
    cfg: dict[str, Any],
) -> str:
    chips = cfg["chips"]
    if product_kind == "landslide_ews":
        return posture_label
    if product_kind == "flood_extent_response":
        if extent.get("availability") != "unavailable" and extent.get("value_ha") is not None:
            return chips["flood_extent"]
        return chips["flood_unavailable"]
    if state == "not cached":
        return chips["not_cached"]
    return chips["quake_window"]


def decide(
    scope: list[str],
    envelopes: dict[str, list[dict[str, Any]]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Combine in-scope envelopes. ``scope`` is the AOI's own hazards."""
    rows = []
    for domain in cfg["domains"]:
        if domain in scope:
            rows.append(_domain_row(domain, envelopes.get(domain) or [], cfg))
        else:
            rows.append(_out_of_scope(domain, cfg))
    in_scope = [row for row in rows if row["in_scope"]]
    if not in_scope:
        posture = "not_assessed"
    else:
        posture = in_scope[0]["light"]
        for row in in_scope[1:]:
            posture = _higher(cfg["rank"], posture, row["light"])
    action = _action_block(posture, cfg)
    headline = next((row["extent"] for row in in_scope if row["light"] == posture), None)
    flat = [env for domain in scope for env in envelopes.get(domain) or []]
    product_kind = _product_kind(scope, cfg)
    domain = scope[0] if len(scope) == 1 else None
    extent = headline or _unavailable(cfg["unavailable"]["area"])
    state = _panel([row["evidence_state"] for row in in_scope])
    posture_label = cfg["lights"][posture]
    return {
        "product_kind": product_kind,
        "product_label": cfg["product_labels"].get(product_kind, product_kind),
        "lights_applicable": product_kind == "landslide_ews",
        "chip": _chip(product_kind, extent, posture_label, state, cfg),
        "damage_level": _damage_level(domain, cfg),
        "response_package": _response_package(domain, action["id"], cfg),
        "posture": posture,
        "posture_label": posture_label,
        "state": state,
        "action": action["id"],
        "action_label": action["label"],
        "action_detail": action["detail"],
        "clearance": False,
        "clearance_text": cfg["clearance"],
        "hazards": rows,
        "magnitude": {
            "extent": extent,
            "social_impact": _first_measured(
                in_scope, "social_impact", cfg["unavailable"]["social"]
            ),
            "economic_impact": _first_measured(
                in_scope, "economic_impact", cfg["unavailable"]["economic"]
            ),
        },
        "priorities": _priorities(action["id"], cfg),
        "lines_of_effort": _lines(action["id"], cfg),
        "lifelines": _lifelines(scope, cfg),
        "provenance": _provenance(flat),
        "doctrine": cfg["doctrine"],
        "not_a": list(cfg["not_a"]),
        "numbers_policy": cfg["numbers_policy"],
        "rank": list(cfg["rank"]),
        "lights": dict(cfg["lights"]),
    }


def _track_ids(spec: dict[str, Any]) -> list[int]:
    tracks = []
    for raw in spec.get("quake_tracks") or []:
        if isinstance(raw, bool) or not isinstance(raw, str) or not raw.isdigit():
            raise DecisionConfigError("quake_tracks must be numeric strings")
        tracks.append(int(raw))
    return tracks


def _build_one(tool: str, domain: str, artifact_path: Path, builder) -> dict[str, Any]:
    try:
        artifact = evidence.load_artifact(artifact_path)
    except evidence.EvidenceError as exc:
        return evidence.errored(tool, domain, str(exc))
    if artifact is None:
        return evidence.not_cached(tool, domain, f"no {domain} evidence ({artifact_path.name})")
    try:
        return builder(artifact)
    except evidence.EvidenceError as exc:
        return evidence.errored(tool, domain, str(exc))


def _load_envelopes(
    spec: dict[str, Any],
    cache_root: Path,
    ops: dict[str, Any],
    frozen: bool,
) -> dict[str, list[dict[str, Any]]]:
    cache_id = spec.get("cache_id") or spec["id"]
    root = cache_root / cache_id
    loaded: dict[str, list[dict[str, Any]]] = {}
    hazards = spec["hazards"]
    if "flood" in hazards:
        loaded["flood"] = [
            _build_one(
                "analyze_flood_inundation",
                "flood",
                root / "flood_evidence.json",
                lambda artifact: evidence.build_flood_envelope(
                    artifact, ops, "analyze_flood_inundation"
                ),
            )
        ]
    if "landslide" in hazards:
        loaded["landslide"] = [
            _build_one(
                "analyze_landslide_kinematics",
                "landslide",
                root / "landslide_evidence.json",
                lambda artifact: evidence.build_landslide_envelope(
                    artifact, ops, "analyze_landslide_kinematics"
                ),
            )
        ]
    if "earthquake" in hazards:
        quake = []
        for track in _track_ids(spec):
            env = _build_one(
                "analyze_earthquake_dpm",
                "earthquake",
                root / f"quake_evidence_track{track}.json",
                lambda artifact, track=track: evidence.build_quake_envelope(
                    artifact, ops, "analyze_earthquake_dpm", is_frozen=frozen
                ),
            )
            env["track"] = track
            quake.append(env)
        loaded["earthquake"] = quake
    return loaded


def _product(
    aoi: str,
    spec: dict[str, Any],
    envelopes: dict[str, list[dict[str, Any]]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    decided = decide(list(spec["hazards"]), envelopes, cfg)
    return {
        "aoi": aoi,
        "label": spec["label"],
        "primary": bool(spec.get("primary")),
        "hazards_in_scope": list(spec["hazards"]),
        **decided,
    }


def product_for_aoi(
    aoi: str,
    *,
    cache_root: Path,
    ops: dict[str, Any] | None = None,
    frozen: bool | None = None,
) -> dict[str, Any] | None:
    """One AOI's posture. ``None`` when ``aoi`` is not in ``decision.aois``."""
    ops = _ops() if ops is None else ops
    cfg = decision_config(ops)
    spec = cfg["aois"].get(aoi)
    if spec is None:
        return None
    spec = {**spec, "id": aoi}
    if frozen is None:
        frozen = _frozen()
    return _product(aoi, spec, _load_envelopes(spec, cache_root, ops, frozen), cfg)


def roster(
    *,
    cache_root: Path,
    ops: dict[str, Any] | None = None,
    frozen: bool | None = None,
) -> dict[str, Any]:
    """Every configured AOI, plus the board posture (highest light wins)."""
    ops = _ops() if ops is None else ops
    cfg = decision_config(ops)
    if frozen is None:
        frozen = _frozen()
    products = []
    for aoi, spec in cfg["aois"].items():
        full = {**spec, "id": aoi}
        products.append(_product(aoi, full, _load_envelopes(full, cache_root, ops, frozen), cfg))
    posture = products[0]["posture"]
    for product in products[1:]:
        posture = _higher(cfg["rank"], posture, product["posture"])
    action = _action_block(posture, cfg)
    return {
        "state": _panel([product["state"] for product in products]),
        "product_kind": "mixed",
        "product_label": cfg["product_labels"]["mixed"],
        "lights_applicable": False,
        "board_note": cfg["board_note"],
        "posture": posture,
        "posture_label": cfg["lights"][posture],
        "action": action["id"],
        "action_label": action["label"],
        "action_detail": action["detail"],
        "clearance": False,
        "clearance_text": cfg["clearance"],
        "aois": products,
        "doctrine": cfg["doctrine"],
        "not_a": list(cfg["not_a"]),
        "numbers_policy": cfg["numbers_policy"],
        "rank": list(cfg["rank"]),
        "lights": dict(cfg["lights"]),
    }
