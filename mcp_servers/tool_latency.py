"""Owner-run, uncensored live-tool latency collection for issue #28.

Preflight is entirely offline. Execution belongs to the cloud owners named in
AGENTS.md. Nothing is measured or written as a budget by a dry run.
"""

import argparse
import ast
import contextlib
import importlib
import inspect
import io
import json
import math
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
OWNERS = ("LEONOB2014", "Jack4Codes", "EstebanOchoaedos")
MODULES = {"nisar_asf": "mcp_servers.nisar_asf_mcp", "gee_fusion": "mcp_servers.gee_fusion_mcp"}
WRITES = {"stage_nisar_gcov_to_gcs", "stage_nisar_gunw_ionosphere_corrected_to_gcs"}
FREEZE_REQUIRED = {
    "stage_nisar_gunw_ionosphere_corrected_to_gcs",
    "analyze_landslide_kinematics",
    "analyze_flood_inundation",
    "analyze_earthquake_dpm",
    "rank_first_aid_barrios",
    "score_against_baseline",
    "get_earthquake_pair_set",
}
SAMPLE_COUNT = 10


class PlanError(ValueError):
    """No external call is allowed from an invalid measurement plan."""


def read_json(filename):
    return json.loads(Path(filename).read_text(encoding="utf-8"))


def lookup(document, fields):
    value = document
    for field in fields:
        if isinstance(value, dict) and field in value:
            value = value[field]
        elif isinstance(value, list) and isinstance(field, int) and 0 <= field < len(value):
            value = value[field]
        else:
            raise PlanError("missing source reference")
    if value is None:
        raise PlanError("missing source reference")
    return value


def resolve(value, config, catalog):
    if isinstance(value, list):
        return [resolve(item, config, catalog) for item in value]
    if not isinstance(value, dict):
        return value
    if set(value) == {"config_path"}:
        return lookup(config, value["config_path"])
    if set(value) == {"catalog_path"}:
        return lookup(catalog, value["catalog_path"])
    return {key: resolve(item, config, catalog) for key, item in value.items()}


def registered_functions(server):
    filename = ROOT / (MODULES[server].replace(".", "/") + ".py")
    tree = ast.parse(filename.read_text(encoding="utf-8"))
    functions = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and any(
            isinstance(decorator, ast.Attribute)
            and decorator.attr == "tool"
            and isinstance(decorator.value, ast.Name)
            and decorator.value.id == "mcp"
            for decorator in node.decorator_list
        ):
            functions[node.name] = node
    return tree, functions


def freeze_ready():
    config = yaml.safe_load((ROOT / "config/preregistered.yaml").read_text())
    if config.get("status") != "frozen":
        return False
    result = subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            "HEAD",
            "--",
            "config/preregistered.yaml",
            "validation/README.md",
        ],
        cwd=ROOT,
    )
    if result.returncode:
        return False
    digest = subprocess.check_output(
        ["git", "hash-object", "config/preregistered.yaml"], cwd=ROOT, text=True
    ).strip()
    validation = (ROOT / "validation/README.md").read_text(encoding="utf-8")
    return recorded_hash(validation) == digest


HASH_CELL = re.compile(r"^\s*`([0-9a-f]{40})`")


def recorded_hash(validation_text):
    """The current frozen hash: the leading backticked blob in the hash row's value cell.

    The cell may carry notes after the hash (a re-freeze, the superseded blob); only
    the backticked 40-hex value at the start of the cell is the recorded hash.
    """
    for row in validation_text.splitlines():
        if row.startswith("| `config/preregistered.yaml` hash"):
            cells = row.split("|")
            match = HASH_CELL.match(cells[2]) if len(cells) > 2 else None
            return match.group(1) if match else None
    return None


def preflight(plan):
    config = yaml.safe_load((ROOT / "config/bailasar.yaml").read_text(encoding="utf-8"))
    catalog = read_json(ROOT / "nisar_colombia_granules_2026.json")
    known_ids = {item["scene_name"] for aoi in catalog["aois"].values() for item in aoi["granules"]}
    requests = plan.get("requests")
    if not isinstance(requests, list) or not requests:
        raise PlanError("plan needs tool requests")
    seen, results = set(), []
    for request in requests:
        server, tool = request["server"], request["tool"]
        if server not in MODULES or tool in seen:
            raise PlanError("unknown server or duplicate tool request")
        seen.add(tool)
        ids = request.get("granule_ids", [])
        if not isinstance(ids, list) or any(
            not isinstance(item, str) or item not in known_ids for item in ids
        ):
            raise PlanError("request cites an ID absent from the committed gate catalog")
        if not request.get("source"):
            raise PlanError("request needs a source record")
        item = {
            "server": server,
            "tool": tool,
            "source": request["source"],
            "granule_ids": ids,
            "status": "ready",
            "blockers": [],
        }
        tree, functions = registered_functions(server)
        function = functions.get(tool)
        if function is None:
            item["blockers"].append("tool_not_registered_on_this_branch")
        else:
            arguments = resolve(request.get("arguments", {}), config, catalog)
            if not isinstance(arguments, dict):
                raise PlanError("arguments must be an object")
            names = [arg.arg for arg in function.args.args]
            # Benchmark workloads must not inherit stale sample-date/polarization defaults.
            required = set(names)
            item["required_arguments"] = names
            if not required <= arguments.keys() or not arguments.keys() <= set(names):
                item["blockers"].append("missing_or_unknown_arguments")
            item["arguments"] = arguments
        definitions = {
            target.id
            for node in tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        if "mcp" not in definitions:
            item["blockers"].append("server_bootstrap_incomplete")
        if tool in FREEZE_REQUIRED and not freeze_ready():
            item["blockers"].append("committed_preregistration_not_ready")
        if tool in WRITES and not ids:
            item["blockers"].append("staging_requires_real_input_granule_ids")
        if tool in WRITES and not os.environ.get("GCS_NISAR_BUCKET"):
            item["blockers"].append("staging_bucket_must_be_explicit")
        if server == "gee_fusion" and not ids:
            item["blockers"].append("science_requires_real_input_granule_ids")
        if item["blockers"]:
            item["status"] = "blocked"
        results.append(item)
    return results


def summarize(samples):
    if len(samples) != SAMPLE_COUNT or any(not math.isfinite(t) or t < 0 for t in samples):
        raise PlanError("budget requires the complete successful measurement set")
    p95 = float(np.quantile(samples, 0.95, method="linear"))
    return {
        "sample_count": len(samples),
        "p95_s": p95,
        "budget_s": p95 + 0.5,
        "range_s": [min(samples), max(samples)],
        "interval": None,
        "evidence": {
            "samples_s": "measured",
            "sample_count": "measured",
            "range_s": "measured",
            "p95_s": "estimate",
            "budget_s": "estimate",
        },
    }


def validate_response(tool, result, input_ids):
    envelope_provenance = None
    if isinstance(result, dict) and "state" in result:
        if result["state"] != "live":
            raise PlanError("cached, gate, error and unavailable results cannot set live budgets")
        # #122/#136 evidence envelopes carry provenance beside `data`, not inside it.
        envelope_provenance = result.get("provenance")
        result = result.get("data")
    if tool == "search_nisar_granules" and isinstance(result, list):
        if any(not isinstance(row, dict) or not row.get("scene_name") for row in result):
            raise PlanError("catalog response lacks identifiers")
        return [row["scene_name"] for row in result]
    if not isinstance(result, dict) or not result:
        raise PlanError("tool returned no valid live result")
    if tool in WRITES:
        if not input_ids or not all(
            isinstance(uri, str) and uri.startswith("gs://") for uri in result.values()
        ):
            raise PlanError("staging did not return real cloud artifact references")
        return input_ids
    provenance = envelope_provenance or result.get("provenance") or {}
    ids = provenance.get("granule_ids") if isinstance(provenance, dict) else None
    if (
        not isinstance(ids, list)
        or not ids
        or not all(isinstance(item, str) and item for item in ids)
    ):
        raise PlanError("live science result lacks granule provenance")
    if not set(input_ids) <= set(ids):
        raise PlanError("live science result omits declared input granules")
    return ids


def measure_raw(item):
    # Suppress library stdout/stderr: remote diagnostics may include signed URLs.
    samples, source_ids = [], set()
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            module = importlib.import_module(MODULES[item["server"]])
            function = getattr(module, item["tool"])
            function = inspect.unwrap(getattr(function, "fn", function))
            for _ in range(SAMPLE_COUNT):
                start = perf_counter()
                result = function(**item["arguments"])
                elapsed = perf_counter() - start
                ids = validate_response(item["tool"], result, item["granule_ids"])
                samples.append(elapsed)
                source_ids.update(ids)
        return {
            "tool": item["tool"],
            "status": "measured",
            "samples_s": samples,
            "granule_ids": sorted(source_ids),
            **summarize(samples),
        }
    except Exception as exc:
        return {
            "tool": item["tool"],
            "status": "failed",
            "samples_s": samples,
            "failure_type": type(exc).__name__,
            "budget_s": None,
        }


def apply_budgets(filename, results):
    estimates = {}
    for item in results:
        if item.get("status") != "measured":
            continue
        estimate = summarize(item.get("samples_s", []))
        if item.get("budget_s") != estimate["budget_s"]:
            raise PlanError("budget does not match the recorded live samples")
        estimates[item["tool"]] = estimate["budget_s"]
    if not estimates:
        raise PlanError("no complete live measurements; operational config is unchanged")
    raw = filename.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)
    start = next(index for index, line in enumerate(lines) if line.startswith("breaker_budgets_s:"))
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or lines[end].startswith(" ")):
        end += 1
    budgets = yaml.safe_load(raw)["breaker_budgets_s"]
    budgets.update(estimates)
    body = "".join(f"  {name}: {value}\n" for name, value in budgets.items())
    filename.write_text("".join(lines[: start + 1]) + body + "".join(lines[end:]), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--owner", choices=OWNERS)
    parser.add_argument("--watchdog-s", type=float)
    parser.add_argument("--allow-staging-writes", action="store_true")
    parser.add_argument("--apply-budgets", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/tool_latency.json")
    parser.add_argument("--worker-tool", help=argparse.SUPPRESS)
    args = parser.parse_args()
    items = preflight(read_json(args.plan))
    if args.execute and (
        not args.owner
        or not args.watchdog_s
        or not math.isfinite(args.watchdog_s)
        or args.watchdog_s <= 0
    ):
        parser.error("execution requires a cloud owner and a positive explicit watchdog duration")
    if args.apply_budgets and not args.execute:
        parser.error("offline preflight cannot write budgets")
    if args.worker_tool:
        if not args.execute:
            parser.error("worker requires explicit execution authorization")
        item = next(item for item in items if item["tool"] == args.worker_tool)
        if item["status"] != "ready" or (item["tool"] in WRITES and not args.allow_staging_writes):
            raise PlanError("worker request is blocked")
        print(json.dumps(measure_raw(item), allow_nan=False))
        return 0
    results = []
    for item in items:
        public = {
            key: value for key, value in item.items() if key not in {"arguments", "granule_ids"}
        }
        public["input_granule_ids"] = item["granule_ids"]
        public["granule_ids"] = []
        if not args.execute or item["status"] != "ready":
            public["status"] = "blocked" if item["status"] == "blocked" else "not measured"
            public["budget_s"] = None
        elif item["tool"] in WRITES and not args.allow_staging_writes:
            public.update(
                status="blocked", blockers=["staging_writes_not_authorized"], budget_s=None
            )
        else:
            command = [
                sys.executable,
                "-m",
                "mcp_servers.tool_latency",
                "--plan",
                str(args.plan.resolve()),
                "--execute",
                "--owner",
                args.owner,
                "--watchdog-s",
                str(args.watchdog_s),
                "--worker-tool",
                item["tool"],
            ]
            if args.allow_staging_writes:
                command.append("--allow-staging-writes")
            environment = dict(os.environ, OFFLINE_DEMO_MODE="0")
            try:
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=args.watchdog_s,
                    check=True,
                )
                public.update(json.loads(completed.stdout))
            except (subprocess.SubprocessError, ValueError):
                public.update(
                    status="failed", failure_type="worker_failed_or_watchdog", budget_s=None
                )
        results.append(public)
    document = {
        "command": subprocess.list2cmdline(
            ["uv", "run", "python", "-m", "mcp_servers.tool_latency", *sys.argv[1:]]
        ),
        "recorded_utc": datetime.now(UTC).isoformat(),
        "execution": "owner_live_measurements" if args.execute else "offline_preflight",
        "method": "uncached raw function; sequential successful calls; linear empirical percentile",
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if args.apply_budgets:
        apply_budgets(ROOT / "config/bailasar.yaml", results)
    print(
        json.dumps(
            {
                "report": str(args.output),
                "statuses": {item["tool"]: item["status"] for item in results},
            }
        )
    )
    return 0 if all(item["status"] == "measured" for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
