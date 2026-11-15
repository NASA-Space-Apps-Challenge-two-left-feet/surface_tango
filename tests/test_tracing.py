"""LangSmith switch: off without a key, on with one, never leaks the key."""

import os

import pytest

from agents import tracing

KEYS = ("LANGSMITH_API_KEY", "LANGSMITH_TRACING", "LANGSMITH_PROJECT")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    return tmp_path / "missing.env"  # no .env is read in these tests


def test_off_without_key(clean_env):
    status = tracing.configure_tracing({"project": "p"}, env_path=clean_env)
    assert status == "langsmith: off (LANGSMITH_API_KEY not set)"
    assert "LANGSMITH_TRACING" not in os.environ


def test_on_with_key_sets_project_and_hides_key(clean_env, monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2-test-value")
    status = tracing.configure_tracing({"project": "surface-tango"}, env_path=clean_env)
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_PROJECT"] == "surface-tango"
    assert "lsv2-test-value" not in status


def test_env_project_wins_over_config(clean_env, monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "x")
    monkeypatch.setenv("LANGSMITH_PROJECT", "my-sandbox")
    tracing.configure_tracing({"project": "surface-tango"}, env_path=clean_env)
    assert os.environ["LANGSMITH_PROJECT"] == "my-sandbox"


def test_explicit_opt_out_is_respected(clean_env, monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "x")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    status = tracing.configure_tracing({"project": "p"}, env_path=clean_env)
    assert status.startswith("langsmith: off")
    assert os.environ["LANGSMITH_TRACING"] == "false"


def test_config_can_disable(clean_env, monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "x")
    status = tracing.configure_tracing({"enabled": False}, env_path=clean_env)
    assert status == "langsmith: disabled in config/bailasar.yaml"


def test_run_metadata_tags_mode():
    meta = tracing.run_metadata("cached")
    assert meta["tags"] == ["bailasar", "cached"]
    assert meta["metadata"]["mode"] == "cached"
