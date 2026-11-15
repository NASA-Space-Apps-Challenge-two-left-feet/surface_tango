"""Orchestrator LLM chain: order, key skipping, and fallback-aware tool/structured binding."""

import pytest
from langchain_core.runnables import RunnableWithFallbacks
from langchain_core.tools import tool
from pydantic import BaseModel

from agents import llm as llm_mod

CONFIG = {
    "temperature": 0.0,
    "providers": {
        "a": {
            "base_url": "https://a.example/v1",
            "api_key_env": "TEST_KEY_A",  # pragma: allowlist secret
        },
        "b": {
            "base_url": "https://b.example/v1",
            "api_key_env": "TEST_KEY_B",  # pragma: allowlist secret
        },
    },
    "chain": [
        {"provider": "a", "model": "model-1"},
        {"provider": "b", "model": "model-2"},
        {"provider": "a", "model": "model-3"},
    ],
}


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch):
    monkeypatch.setattr(llm_mod, "load_dotenv", lambda *a, **k: None)
    for k in ("TEST_KEY_A", "TEST_KEY_B"):
        monkeypatch.delenv(k, raising=False)


def test_chain_order_and_skips_missing_keys(monkeypatch):
    monkeypatch.setenv("TEST_KEY_A", "test-not-a-real-key")
    models = llm_mod.build_models(CONFIG)
    assert [m.model_name for m in models] == ["model-1", "model-3"]


def test_no_keys_raises(monkeypatch):
    with pytest.raises(RuntimeError, match="no usable LLM provider"):
        llm_mod.build_models(CONFIG)


def test_single_model_has_no_fallback_wrapper(monkeypatch):
    monkeypatch.setenv("TEST_KEY_B", "test-not-a-real-key")
    assert not isinstance(llm_mod.get_orchestrator_llm(CONFIG), RunnableWithFallbacks)


def test_tools_and_structured_output_bind_on_every_fallback(monkeypatch):
    monkeypatch.setenv("TEST_KEY_A", "test-not-a-real-key")
    monkeypatch.setenv("TEST_KEY_B", "test-not-a-real-key")
    chain = llm_mod.get_orchestrator_llm(CONFIG)
    assert isinstance(chain, RunnableWithFallbacks) and len(chain.fallbacks) == 2

    @tool
    def ping(x: int) -> int:
        """Echo."""
        return x

    bound = chain.bind_tools([ping])
    assert isinstance(bound, RunnableWithFallbacks)
    assert all("tools" in r.kwargs for r in [bound.runnable, *bound.fallbacks])

    class Out(BaseModel):
        text: str

    assert isinstance(chain.with_structured_output(Out), RunnableWithFallbacks)


def test_create_react_agent_accepts_the_chain(monkeypatch):
    from langgraph.prebuilt import create_react_agent

    monkeypatch.setenv("TEST_KEY_A", "test-not-a-real-key")
    monkeypatch.setenv("TEST_KEY_B", "test-not-a-real-key")

    @tool
    def ping(x: int) -> int:
        """Echo."""
        return x

    create_react_agent(llm_mod.get_orchestrator_llm(CONFIG), tools=[ping])


def test_repo_config_chain_is_well_formed():
    cfg = llm_mod.load_llm_config()
    assert cfg["chain"], "empty chain"
    for entry in cfg["chain"]:
        assert entry["provider"] in cfg["providers"]


# --- Vertex Gemini provider (ADC-based) ---------------------------------------

VERTEX_CFG = {
    "temperature": 0.0,
    "providers": {
        "vertex": {"type": "vertex", "project_env": "GCP_PROJECT_ID", "location": "us-central1"},
        "featherless": {
            "base_url": "https://x/v1",
            "api_key_env": "FEATHERLESS_API_KEY",  # pragma: allowlist secret
        },  # pragma: allowlist secret
    },
    "chain": [
        {"provider": "vertex", "model": "gemini-2.5-flash"},
        {"provider": "featherless", "model": "m"},
    ],
}


def test_vertex_entry_built_with_adc(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "proj-x")
    for k in ("FEATHERLESS_API_KEY",):
        monkeypatch.delenv(k, raising=False)
    sentinel = object()
    monkeypatch.setattr(llm_mod, "_vertex_model", lambda *a, **k: sentinel)
    models = llm_mod.build_models(VERTEX_CFG)
    assert models == [sentinel]  # vertex built, featherless skipped (no key)


def test_vertex_skipped_without_project_or_lib(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.setenv("FEATHERLESS_API_KEY", "k")
    # no project -> _vertex_model returns None; featherless provides the model
    models = llm_mod.build_models(VERTEX_CFG)
    assert len(models) == 1  # only featherless


def test_no_usable_provider_mentions_vertex(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.delenv("FEATHERLESS_API_KEY", raising=False)
    import pytest

    with pytest.raises(RuntimeError, match="Vertex"):
        llm_mod.build_models(VERTEX_CFG)
