#!/usr/bin/env bash
# pre-commit guard: refuse to commit on a branch that is behind origin/main.
# Fix with `make sync` (fetch + rebase onto origin/main). Offline: warn and allow.
set -uo pipefail

[ "${BAILASAR_SKIP_SYNC_CHECK:-}" = "1" ] && exit 0      # CI sets this
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo HEAD)"
[ "$branch" = "main" ] && exit 0                         # main is guarded by no-commit-to-branch

if ! timeout 15 git fetch --quiet origin main 2>/dev/null && ! git fetch --quiet origin main 2>/dev/null; then
  echo "sync-check: could not reach origin (offline?); commit allowed, run 'make sync' when back online." >&2
  exit 0
fi

if ! git merge-base --is-ancestor origin/main HEAD; then
  behind="$(git rev-list --count HEAD..origin/main)"
  echo "sync-check: '$branch' is $behind commit(s) behind origin/main." >&2
  echo "Run 'make sync' (rebases your branch onto origin/main), then commit again." >&2
  exit 1
fi
