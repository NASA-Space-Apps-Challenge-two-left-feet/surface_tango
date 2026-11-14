# Makefile
SHELL := /bin/bash
COMPOSE := docker compose

.PHONY: help setup sync worktree check test ci up pitch prewarm test-dag logs down clean

help: ## Show available Space Apps Medellín operational commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ==============================================================================
# Development (AGENTS.md: trunk-based, one worktree per branch, local CI gate)
# ==============================================================================
setup: ## uv env + pre-commit and commit-msg hooks + .env from template
	uv sync --all-extras
	uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
	@[ -f .env ] || cp .env.example .env
	@mkdir -p local_cache

sync: ## Bring your branch up to date: rebase onto origin/main (fast-forward on main)
	@git fetch origin
	@if [ "$$(git rev-parse --abbrev-ref HEAD)" = "main" ]; then git pull --ff-only origin main; \
	else git rebase --autostash origin/main; fi

worktree: ## New worktree from the latest origin/main: make worktree BRANCH=feat/quake-dpm
	@test -n "$(BRANCH)" || (echo "BRANCH is required, e.g. make worktree BRANCH=feat/quake-dpm" && exit 1)
	scripts/new_worktree.sh "$(BRANCH)"

check: ## Every pre-commit hook on every file (identical to CI)
	uv run pre-commit run --all-files

test: ## Tests that need no network or cache (what CI runs)
	uv run pytest -q -m "not network and not cache"

ci: ## Local CI gate: run before opening, marking ready or updating a PR
	SKIP=no-commit-to-branch uv run pre-commit run --from-ref origin/main --to-ref HEAD
	$(MAKE) test

# ==============================================================================
# Stack
# ==============================================================================
up: ## Boot full stack in LIVE mode (GEE + NASA S3 + cache_guard circuit breaker) on http://localhost:8000
	OFFLINE_DEMO_MODE=0 $(COMPOSE) --profile live up --build -d
	@echo "🚀 Live Mission Control running at http://localhost:8000"

pitch: ## Boot full stack in PITCH mode (offline: local Zarr v3 cache + hashed LLM cache)
	OFFLINE_DEMO_MODE=1 $(COMPOSE) --profile pitch up -d
	@echo "⚡ Pitch Mode Active (Air-Gapped Zarr v3 + Cached LLM) at http://localhost:8000"

prewarm: ## Force rebuild of the Antioquia Zarr v3 Data Cube and local COGs
	$(COMPOSE) build cache-warmer
	$(COMPOSE) run --rm cache-warmer python scripts/prewarm_antioquia_cache.py

test-dag: ## Run the agent graph end to end (3 hazard agents + cross-hazard synthesis)
	$(COMPOSE) exec sars-web-orchestrator python -m agents.orchestrator

logs: ## Tail real-time logs across both FastMCP servers and the LangGraph orchestrator
	$(COMPOSE) --profile live logs -f

down: ## Stop all running containers cleanly
	$(COMPOSE) --profile live --profile pitch down

clean: ## Stop containers and wipe temporary build artifacts (preserves local_cache)
	$(COMPOSE) --profile live --profile pitch down --rmi local
