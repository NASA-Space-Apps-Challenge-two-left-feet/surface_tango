#!/usr/bin/env bash
# New worktree for a short-lived branch, from the latest origin/main (trunk), with the shared
# local_cache/ and .env linked from the main checkout.
#   scripts/new_worktree.sh feat/quake-dpm   ->  ../surface_tango-worktrees/feat-quake-dpm
set -euo pipefail

branch="${1:?usage: new_worktree.sh <type>/<lane>-<short-description>}"
if ! printf '%s' "$branch" | grep -Eq '^(feat|fix|perf|refactor|docs|test|build|ci|chore|style|revert)/[a-z0-9][a-z0-9.-]*$'; then
  echo "branch must be <type>/<kebab-description>, e.g. feat/quake-dpm" >&2
  exit 1
fi

# The main checkout is the first worktree git lists, also when this runs inside another worktree.
main_checkout="$(git worktree list --porcelain | sed -n '1s/^worktree //p')"
root="$(dirname "$main_checkout")/$(basename "$main_checkout")-worktrees"
dir="$root/${branch//\//-}"
mkdir -p "$root" "$main_checkout/local_cache"

git fetch origin --quiet || true
base="origin/main"
git rev-parse --verify --quiet "$base" >/dev/null || base="main"
git worktree add -b "$branch" "$dir" "$base"

ln -sfn "$main_checkout/local_cache" "$dir/local_cache"
[ -f "$main_checkout/.env" ] && ln -sfn "$main_checkout/.env" "$dir/.env"
echo "worktree ready: $dir (from $base); local_cache and .env linked"
