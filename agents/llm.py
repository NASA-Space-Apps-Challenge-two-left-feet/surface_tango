"""Orchestrator LLM with an ordered fallback chain across OpenAI-compatible providers.

The chain lives in `config/bailasar.yaml` under `llm:` (operational, not pre-registered).
Entries whose API key is not set in the environment are skipped, so each teammate gets
the best chain their own keys allow. Agents only route tools and write placeholder prose;
they never produce numbers (AGENTS.md), so any model in the chain is interchangeable.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "bailasar.yaml"


def load_llm_config(path: Path = CONFIG_PATH) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    return cfg["llm"]


def build_models(config: dict | None = None) -> list[BaseChatModel]:
    """One chat model per chain entry whose provider key is set, in chain order."""
    load_dotenv(ROOT / ".env", override=False)
    config = config or load_llm_config()
    providers = config["providers"]
    models: list[BaseChatModel] = []
    for entry in config["chain"]:
        provider = providers[entry["provider"]]
        api_key = os.environ.get(provider["api_key_env"])
        if not api_key:
            continue
        models.append(
            ChatOpenAI(
                model=entry["model"],
                base_url=provider["base_url"],
                api_key=api_key,
                temperature=config.get("temperature", 0.0),
                timeout=config.get("timeout_s", 60),
                max_retries=config.get("max_retries", 1),
            )
        )
    if not models:
        keys = sorted({p["api_key_env"] for p in providers.values()})
        raise RuntimeError(f"no LLM provider key set; set one of {keys} in .env")
    return models


def get_orchestrator_llm(config: dict | None = None) -> Runnable:
    """Primary model with the remaining chain as fallbacks.

    `bind_tools(...)` and `with_structured_output(...)` on the result apply to every model
    in the chain, so it can be passed to `create_react_agent` like a single chat model.
    """
    models = build_models(config)
    primary, rest = models[0], models[1:]
    return primary.with_fallbacks(rest) if rest else primary
