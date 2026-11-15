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


def _vertex_model(entry: dict, provider: dict, config: dict) -> BaseChatModel | None:
    """Gemini via Vertex AI, authenticated with ADC (the same identity as init_ee).

    No API key: uses Application Default Credentials and the GCP project. Lazily
    imported and ADC-checked, so a missing library or unset ADC skips this entry
    (like a missing key) instead of breaking the chain.
    """
    project = os.environ.get(provider.get("project_env", "GCP_PROJECT_ID"))
    if not project:
        return None
    try:
        import google.auth
        from langchain_google_vertexai import ChatVertexAI

        google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    except Exception:
        return None
    return ChatVertexAI(
        model=entry["model"],
        project=project,
        location=os.environ.get("VERTEX_LOCATION", provider.get("location", "us-central1")),
        temperature=config.get("temperature", 0.0),
        max_retries=config.get("max_retries", 1),
    )


def build_models(config: dict | None = None) -> list[BaseChatModel]:
    """One chat model per chain entry that is usable, in chain order.

    An OpenAI-compatible entry needs its provider key in the environment; a
    ``vertex`` entry needs ADC and a GCP project. Unusable entries are skipped.
    """
    load_dotenv(ROOT / ".env", override=False)
    config = config or load_llm_config()
    providers = config["providers"]
    models: list[BaseChatModel] = []
    for entry in config["chain"]:
        provider = providers[entry["provider"]]
        if provider.get("type") == "vertex":
            model = _vertex_model(entry, provider, config)
            if model is not None:
                models.append(model)
            continue
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
        keys = sorted({p["api_key_env"] for p in providers.values() if p.get("api_key_env")})
        raise RuntimeError(
            f"no usable LLM provider; set one of {keys} in .env, or enable Vertex AI "
            "(gcloud services enable aiplatform.googleapis.com) with ADC + GCP_PROJECT_ID"
        )
    return models


def get_orchestrator_llm(config: dict | None = None) -> Runnable:
    """Primary model with the remaining chain as fallbacks.

    `bind_tools(...)` and `with_structured_output(...)` on the result apply to every model
    in the chain, so it can be passed to `create_react_agent` like a single chat model.
    """
    models = build_models(config)
    primary, rest = models[0], models[1:]
    return primary.with_fallbacks(rest) if rest else primary
