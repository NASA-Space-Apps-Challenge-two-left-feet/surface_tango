#!/usr/bin/env python3
"""New worktree for a short-lived branch, from the latest origin/main (trunk).

The shared local_cache/ and .env are linked from the main checkout.
    python3 scripts/new_worktree.py feat/quake-dpm  ->  ../surface_tango-worktrees/feat-quake-dpm
Standard library only, so it runs before `uv sync`.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BRANCH_RE = re.compile(
    r"^(feat|fix|perf|refactor|docs|test|build|ci|chore|style|revert)/[a-z0-9][a-z0-9.-]*$"
)


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=check)


def main_checkout() -> Path:
    """The main checkout is the first worktree git lists, also from inside another worktree."""
    first = git("worktree", "list", "--porcelain").stdout.splitlines()[0]
    return Path(first.removeprefix("worktree "))


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: new_worktree.py <type>/<lane>-<short-description>", file=sys.stderr)
        return 1
    branch = argv[0]
    if not BRANCH_RE.match(branch):
        print("branch must be <type>/<kebab-description>, e.g. feat/quake-dpm", file=sys.stderr)
        return 1

    main_dir = main_checkout()
    root = main_dir.parent / f"{main_dir.name}-worktrees"
    target = root / branch.replace("/", "-")
    root.mkdir(parents=True, exist_ok=True)
    (main_dir / "local_cache").mkdir(exist_ok=True)

    git("fetch", "origin", "--quiet", check=False)
    base = "origin/main"
    if git("rev-parse", "--verify", "--quiet", base, check=False).returncode != 0:
        base = "main"
    added = subprocess.run(["git", "worktree", "add", "-b", branch, str(target), base], check=False)
    if added.returncode != 0:
        return added.returncode

    for name in ("local_cache", ".env"):
        source = main_dir / name
        link = target / name
        if source.exists() and not link.exists():
            link.symlink_to(source)
    print(f"worktree ready: {target} (from {base}); local_cache and .env linked")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
