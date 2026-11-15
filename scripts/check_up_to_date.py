#!/usr/bin/env python3
"""pre-commit guard: refuse to commit on a branch that is behind origin/develop.

Fix with `make sync` (fetch + rebase onto origin/develop). Offline: warn and allow.
Standard library only, so it runs before `uv sync`.
"""

from __future__ import annotations

import os
import subprocess
import sys


def git(*args: str, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, timeout=timeout, check=False
    )


def fetch_develop() -> bool:
    for timeout in (15, None):  # one quick try, then one without a limit
        try:
            if git("fetch", "--quiet", "origin", "develop", timeout=timeout).returncode == 0:
                return True
        except subprocess.TimeoutExpired:
            continue
    return False


def main() -> int:
    if os.environ.get("BAILASAR_SKIP_SYNC_CHECK") == "1":  # CI sets this
        return 0
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "HEAD"
    if branch in {"main", "develop"}:  # main is guarded by no-commit-to-branch
        return 0
    if not fetch_develop():
        print(
            "sync-check: could not reach origin (offline?); commit allowed, "
            "run 'make sync' when back online.",
            file=sys.stderr,
        )
        return 0
    if git("merge-base", "--is-ancestor", "origin/develop", "HEAD").returncode != 0:
        behind = git("rev-list", "--count", "HEAD..origin/develop").stdout.strip()
        print(
            f"sync-check: '{branch}' is {behind} commit(s) behind origin/develop.", file=sys.stderr
        )
        print(
            "Run 'make sync' (rebases your branch onto origin/develop), then commit again.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
