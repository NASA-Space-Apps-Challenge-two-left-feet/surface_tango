"""Integration-branch guards, using temporary local Git repositories only."""

import importlib.util
import subprocess
from pathlib import Path


def test_freshness_checks_develop_even_when_main_is_unchanged(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts/check_up_to_date.py"
    spec = importlib.util.spec_from_file_location("sync_guard", script)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"

    def git(*args):
        return subprocess.run(["git", *args], check=True, capture_output=True, text=True)

    git("init", "--bare", str(remote))
    git("init", "-b", "main", str(repo))
    monkeypatch.chdir(repo)
    git("config", "user.name", "Workflow test")
    git("config", "user.email", "workflow@example.invalid")
    git("-c", "core.hooksPath=", "commit", "--allow-empty", "-m", "initial")
    git("remote", "add", "origin", str(remote))
    git("push", "origin", "main", "main:develop")
    git("checkout", "-b", "feat/workflow-test")
    monkeypatch.delenv("BAILASAR_SKIP_SYNC_CHECK", raising=False)
    assert guard.main() == 0
    git("checkout", "-b", "develop")
    git("-c", "core.hooksPath=", "commit", "--allow-empty", "-m", "integration advances")
    git("push", "origin", "develop")
    git("checkout", "feat/workflow-test")
    assert guard.main() == 1
    git("rebase", "origin/develop")
    assert guard.main() == 0
