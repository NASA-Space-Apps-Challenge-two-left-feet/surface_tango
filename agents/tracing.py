"""LangSmith tracing for the LangGraph agents, switched on by the key in `.env`.

LangChain and LangGraph trace every run (graph nodes, LLM calls, MCP tool calls through
langchain-mcp-adapters) once `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` are in the
environment. This module sets those from `.env` plus `config/bailasar.yaml` → `tracing:`
so every entry point sends runs to one shared project. Without a key it does nothing and the
agents run untraced. The key is never printed or logged.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "bailasar.yaml"


def load_tracing_config(path: Path = CONFIG_PATH) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    return cfg.get("tracing") or {}


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() or None


def configure_tracing(config: dict | None = None, env_path: Path = ROOT / ".env") -> str:
    """Enable LangSmith tracing when a key is set; return a one-line status (no secrets)."""
    load_dotenv(env_path, override=False)
    config = config if config is not None else load_tracing_config()
    if not config.get("enabled", True):
        os.environ["LANGSMITH_TRACING"] = "false"
        return "langsmith: disabled in config/bailasar.yaml"
    if not os.environ.get("LANGSMITH_API_KEY"):
        return "langsmith: off (LANGSMITH_API_KEY not set)"
    if os.environ.get("LANGSMITH_TRACING", "").lower() == "false":
        return "langsmith: off (LANGSMITH_TRACING=false in .env)"
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ.setdefault("LANGSMITH_PROJECT", config.get("project", "surface-tango"))
    return f"langsmith: tracing to project {os.environ['LANGSMITH_PROJECT']}"


def run_metadata(mode: str) -> dict:
    """Tags and metadata attached to each graph run, so traces are filterable by mode and commit."""
    return {
        "tags": ["bailasar", mode],
        "metadata": {"mode": mode, "git_sha": _git_sha(), "app": "surface-tango"},
    }
