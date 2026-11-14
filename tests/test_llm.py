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
    with pytest.raises(RuntimeError, match="no LLM provider key"):
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
