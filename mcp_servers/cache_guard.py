"""Request-matched, provenance-preserving fallback for MCP tools."""

import functools
import hashlib
import inspect
import json
import math
import os
from concurrent.futures import Future, TimeoutError
from pathlib import Path
from threading import Lock, Thread

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "bailasar.yaml"
CACHE_DIR = ROOT / "local_cache" / "tool_outputs"


def operational_config():
    with CONFIG_PATH.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def request_key(func, args, kwargs):
    bound = inspect.signature(func).bind(*args, **kwargs)
    bound.apply_defaults()
    payload = json.dumps(bound.arguments, sort_keys=True, allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def cached_output(tool_name, key):
    """Read only an exact request's pre-staged output; never derive science here."""
    try:
        record = json.loads((CACHE_DIR / tool_name / f"{key}.json").read_text(encoding="utf-8"))
        provenance = record["provenance"]
        if not isinstance(provenance, dict):
            raise ValueError("invalid provenance")
        if record["request_key"] != key or record["tool"] != tool_name:
            raise ValueError("request mismatch")
        for field in ("source", "granule_ids", "cache_build_time"):
            if not provenance.get(field):
                raise ValueError("missing provenance")
        if (
            not isinstance(provenance["granule_ids"], list)
            or not all(isinstance(item, str) and item.strip() for item in provenance["granule_ids"])
            or not isinstance(provenance["source"], str)
            or not isinstance(provenance["cache_build_time"], str)
        ):
            raise ValueError("invalid granule IDs")
        return {"state": "cached", "data": record["data"], "provenance": provenance}
    except (OSError, ValueError, KeyError, TypeError):
        return {"state": "not cached", "error": "not cached", "tool": tool_name}


def with_offline_zarr_fallback():
    """Bound caller latency and allow at most one in-flight call per tool.

    Python cannot cancel an already running synchronous operation. A timed-out
    worker continues, but no new worker is admitted until it finishes. Daemon
    workers do not block server shutdown. Mutating tools must be idempotent.
    """

    def decorator(func):
        slot = Lock()

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = request_key(func, args, kwargs)
            if os.environ.get("OFFLINE_DEMO_MODE") == "1":
                return cached_output(func.__name__, key)
            budgets = operational_config()["breaker_budgets_s"]
            budget = budgets.get(func.__name__, budgets["default"])
            if isinstance(budget, bool) or not isinstance(budget, int | float):
                raise ValueError("tool budget must be a positive finite duration")
            if not math.isfinite(budget) or budget <= 0:
                raise ValueError("tool budget must be a positive finite duration")
            if not slot.acquire(blocking=False):
                return cached_output(func.__name__, key)
            future = Future()

            def run():
                try:
                    future.set_result(func(*args, **kwargs))
                except Exception as exc:
                    future.set_exception(exc)
                finally:
                    slot.release()

            Thread(target=run, daemon=True).start()
            try:
                result = future.result(timeout=budget)
                if (
                    isinstance(result, dict)
                    and isinstance(result.get("state"), str)
                    and result["state"] in {"live", "cached", "gate result", "not cached", "error"}
                ):
                    return result
                return {"state": "live", "data": result}
            except TimeoutError:
                return cached_output(func.__name__, key)
            except Exception:
                # Remote exceptions can contain credential-bearing URLs.
                return {"state": "error", "error": "live tool failed", "tool": func.__name__}

        wrapper.__signature__ = inspect.signature(func).replace(return_annotation=dict)
        return wrapper

    return decorator


def run_server(mcp, server_name):
    config = operational_config()["mcp"]
    if config["transport"] != "sse":
        raise ValueError("MCP transport must be sse")
    mcp.run(transport="sse", host="0.0.0.0", port=config["ports"][server_name])
