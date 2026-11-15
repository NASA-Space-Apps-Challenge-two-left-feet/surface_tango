"""Load an explicit real-input run plan; never select or invent scene values."""

import json
from pathlib import Path

from agents.bulletin import BulletinContractError, Placeholder

DOMAIN_TOOLS = {
    "landslide": "analyze_landslide_kinematics",
    "earthquake": "analyze_earthquake_dpm",
    "flood": "analyze_flood_inundation",
}
APPROVED_DOMAIN_TOOLS = {domain: {tool} for domain, tool in DOMAIN_TOOLS.items()}
APPROVED_DOMAIN_TOOLS["earthquake"].update({"rank_first_aid_barrios", "score_against_baseline"})
CONTEXT_FIELDS = {"bbox", "start_date", "end_date"}
INGESTION_TOOLS = {
    "get_earthquake_pair_set",
    "search_nisar_granules",
    "stage_nisar_gcov_to_gcs",
    "stage_nisar_gunw_ionosphere_corrected_to_gcs",
}


def domain_request(domain, specification):
    if domain not in DOMAIN_TOOLS or not isinstance(specification, dict):
        raise BulletinContractError("invalid domain request")
    if "tool" not in specification:
        return DOMAIN_TOOLS[domain], specification
    if (
        set(specification) != {"tool", "arguments"}
        or not isinstance(specification["tool"], str)
        or specification["tool"] not in APPROVED_DOMAIN_TOOLS[domain]
        or not isinstance(specification["arguments"], dict)
    ):
        raise BulletinContractError("unapproved domain operation")
    return specification["tool"], specification["arguments"]


def validate_requests(ingestion_requests, tool_requests):
    """Validate the whole request collection before permitting any tool effect."""
    if not isinstance(ingestion_requests, list) or not isinstance(tool_requests, dict):
        raise BulletinContractError("run plan requires ingestion and domain requests")
    seen = set()
    for request in ingestion_requests:
        if not isinstance(request, dict):
            raise BulletinContractError("invalid ingestion request")
        name = request.get("tool")
        request_id = request.get("id", name)
        if (
            not isinstance(name, str)
            or name not in INGESTION_TOOLS
            or not isinstance(request_id, str)
            or not request_id.strip()
            or request_id in seen
            or not isinstance(request.get("arguments", {}), dict)
        ):
            raise BulletinContractError("invalid or duplicate ingestion request")
        seen.add(request_id)
    for domain, specification in tool_requests.items():
        domain_request(domain, specification)


def load_run_plan(filename: Path):
    try:
        plan = json.loads(Path(filename).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(plan, dict):
        raise BulletinContractError("run plan must be an object")
    if "llm" in plan and (plan["llm"] != "configured" or "model" in plan):
        raise BulletinContractError("use the configured LLM chain or an explicit model, not both")
    if "model" in plan and (not isinstance(plan["model"], str) or not plan["model"].strip()):
        raise BulletinContractError("explicit model must be a nonempty configured model name")
    if not isinstance(plan.get("context"), dict) or not CONTEXT_FIELDS <= plan["context"].keys():
        raise BulletinContractError("run plan requires explicit place and dates")
    validate_requests(plan.get("ingestion_requests"), plan.get("tool_requests"))
    if (
        not isinstance(plan.get("placeholders"), dict)
        or not isinstance(plan.get("recipe"), str)
        or not plan["recipe"].strip()
    ):
        raise BulletinContractError("run plan requires placeholders and a model/prompt recipe")
    # Validate declarations before any tool or paid model can be invoked.
    plan_schema(plan)
    return plan


def plan_schema(plan):
    return {key: Placeholder(key=key, **spec) for key, spec in plan["placeholders"].items()}


def context_matches(plan, state):
    return all(state.get(field) == plan["context"][field] for field in CONTEXT_FIELDS)


def resolve_arguments(value, staged, context):
    """Resolve named staged fields, preserving missing observations as errors.

    A reference is {"from_staged": <request id>, "path": [<field>, ...]} or
    {"from_context": <field>}. Other dictionaries are ordinary tool arguments.
    References read only existing values; no default or numeric computation exists.
    """
    if isinstance(value, list):
        return [resolve_arguments(item, staged, context) for item in value]
    if not isinstance(value, dict):
        return value
    if "from_context" in value:
        field = value["from_context"]
        if set(value) != {"from_context"} or field not in CONTEXT_FIELDS or field not in context:
            raise BulletinContractError("invalid context reference")
        result = context[field]
    elif "from_staged" in value:
        if set(value) != {"from_staged", "path"} or not isinstance(value["path"], list):
            raise BulletinContractError("invalid staged reference")
        envelope = staged.get(value["from_staged"], {})
        if envelope.get("state") not in {"live", "cached"}:
            raise BulletinContractError("staged result unavailable")
        result = envelope.get("data")
        for field in value["path"]:
            if not isinstance(result, dict) or field not in result:
                raise BulletinContractError("staged field missing")
            result = result[field]
    else:
        return {key: resolve_arguments(item, staged, context) for key, item in value.items()}
    if result is None:
        raise BulletinContractError("referenced observation missing")
    return result
