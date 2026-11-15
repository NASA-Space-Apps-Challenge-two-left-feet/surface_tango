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
TOOL_ARGUMENTS = {
    "get_earthquake_pair_set": ({}, set()),
    "search_nisar_granules": ({"bbox", "start_date", "end_date"}, {"product_level"}),
    "stage_nisar_gcov_to_gcs": (
        {"https_url", "scene_name", "bbox"},
        {"polarizations"},
    ),
    "stage_nisar_gunw_ionosphere_corrected_to_gcs": (
        {"https_url", "scene_name", "bbox"},
        set(),
    ),
    "analyze_landslide_kinematics": (
        {"gunw_unw_gcs", "gunw_iono_gcs", "gunw_coh_gcs", "gunw_conncomp_gcs", "bbox"},
        {"rain_start_date", "rain_end_date", "temporal_baseline_days"},
    ),
    "analyze_earthquake_dpm": (
        {"coh_pre_gcs", "coh_coseismic_gcs", "goff_range_gcs", "goff_azimuth_gcs", "bbox"},
        set(),
    ),
    "analyze_flood_inundation": (
        {
            "gcov_hhhh_pre_gcs",
            "gcov_hvhv_pre_gcs",
            "gcov_hhhh_post_gcs",
            "gcov_hvhv_post_gcs",
            "bbox",
        },
        {"s1_post_start", "s1_post_end"},
    ),
    "rank_first_aid_barrios": ({"dataset_id"}, set()),
    "score_against_baseline": ({"dataset_id"}, set()),
}


def domain_request(domain, specification):
    if (
        not isinstance(domain, str)
        or domain not in DOMAIN_TOOLS
        or not isinstance(specification, dict)
    ):
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


def _validate_argument_references(value, *, context, available_ids):
    if isinstance(value, list):
        for item in value:
            _validate_argument_references(item, context=context, available_ids=available_ids)
        return
    if isinstance(value, dict):
        if "from_context" in value:
            field = value["from_context"]
            if (
                set(value) != {"from_context"}
                or not isinstance(field, str)
                or field not in CONTEXT_FIELDS
                or field not in context
            ):
                raise BulletinContractError("invalid context reference")
            return
        if "from_staged" in value:
            request_id, path = value.get("from_staged"), value.get("path")
            if (
                set(value) != {"from_staged", "path"}
                or not isinstance(request_id, str)
                or request_id not in available_ids
                or not isinstance(path, list)
                or not path
                or any(not isinstance(part, str) or not part for part in path)
            ):
                raise BulletinContractError("invalid staged reference")
            return
        for item in value.values():
            _validate_argument_references(item, context=context, available_ids=available_ids)


def _validate_tool_arguments(name, arguments, *, context, available_ids):
    if name not in TOOL_ARGUMENTS or not isinstance(arguments, dict):
        raise BulletinContractError("unknown tool or invalid arguments")
    required, optional = TOOL_ARGUMENTS[name]
    keys = set(arguments)
    if not required <= keys or not keys <= required | optional:
        raise BulletinContractError("missing or unknown tool arguments")
    _validate_argument_references(arguments, context=context, available_ids=available_ids)


def validate_requests(ingestion_requests, tool_requests, context):
    """Validate the whole request collection before permitting any tool effect."""
    if not isinstance(ingestion_requests, list) or not isinstance(tool_requests, dict):
        raise BulletinContractError("run plan requires ingestion and domain requests")
    seen = set()
    prior_ids = set()
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
            or set(request) - {"id", "tool", "arguments"}
        ):
            raise BulletinContractError("invalid or duplicate ingestion request")
        _validate_tool_arguments(
            name, request.get("arguments", {}), context=context, available_ids=prior_ids
        )
        seen.add(request_id)
        prior_ids.add(request_id)
    for domain, specification in tool_requests.items():
        name, arguments = domain_request(domain, specification)
        _validate_tool_arguments(name, arguments, context=context, available_ids=prior_ids)


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
    validate_requests(plan.get("ingestion_requests"), plan.get("tool_requests"), plan["context"])
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
