# AGENTS.md — BailaSAR (NASA Space Apps 2026, "Dancing with the SARs")

Rules for every coding agent working in this repo: Claude Code, Codex, Antigravity/Gemini, OpenCode, Grok. The design and every decision live in `docs/designs/bailasar.md`. Read it before you change behavior.

## Non-negotiables
- **No synthetic or fabricated data**, anywhere: code, cache, tiles, numbers, video. A missing pixel stays missing (NaN, shown as "no data"). Never write a generator that fills gaps.
  - The only exception: small hand-written arrays with hand-computed expected values, used by pure-logic tests in `tests/` and listed in `validation/ALLOWLIST.md`.
- **Agents never produce numbers.** LLM text uses `{placeholders}` rendered from tool outputs; event constants come from `validation/event_facts.json`.
- **Frozen parameters live only in `config/preregistered.yaml`.** Its hash is recorded in `validation/README.md`. Do not edit it after pre-registration. Operational settings (AOI tiling, breaker budgets, ports) go in `config/bailasar.yaml`. Never hardcode thresholds or AOIs anywhere else.
- **Report nulls honestly.** If a result is uninformative or not significant, say so on screen with its denominators.
- **Secrets:** credentials come only from environment variables (see `.env.example`). Never commit `.env`, `secrets/` or `local_cache/`.
- **Branding:** no NASA logos, flags or identifiers in generated media or UI headers. No likeness of anyone under 18. Put the "SI-Assisted Analytics" badge on AI-written bulletins.

## Architecture (decided; see the decision ledger in the design doc)
- Two FastMCP servers as separate processes, **SSE transport**: `mcp-nisar-asf` on :8001, `mcp-gee-fusion` on :8002.
- `mcp_servers/cache_guard.py` wraps every tool. On a timeout it serves only real pre-staged tiles, with provenance (`source`, granule IDs, cache build time). An uncached request returns an explicit "not cached" error.
- LangGraph: `nisar_ingestion` → landslide / earthquake / flood agents → `cross_hazard_synthesis` (biomass is a TODO).
- Every UI panel renders one of: live · cached · not cached · gate result · error. Never blank.

## Lane ownership (one owner per folder; see the GitHub issues)
| Lane | Owns |
|---|---|
| Data + gate | repo root, `scripts/`, `pyproject.toml`, `.gitignore`, `.env.example`, `validation/README.md`, Makefile cache targets, `README.md` |
| Quake science | `config/`, `gee_math/earthquake_dpm_math.py`, `validation/scoring.py`, `validation/ALLOWLIST.md` |
| Aburrá + Flood | `gee_math/landslide_insar_math.py`, `gee_math/flood_polarimetric_math.py` |
| Agents/MCP | `mcp_servers/`, `agents/`, `validation/event_facts.json` |
| Frontend + video | `web/` (or `static/`), `app.py`, `video/` |

Edit only files your lane owns. Each person owns their own `tests/test_*.py`. Need a change in another lane? Open an issue or ask its owner.

## Commands
- `make test`: pytest (unit and known-answer tests)
- `make test-dag`: end-to-end run of the agent graph
- `make prewarm` / `make fetch-cache`: build or download the real-data cache
- `make up` (live) · `make pitch` (fully offline from cache)

## Gates
- **Hour 2:** the real `nisar_colombia_granules_2026.json` exists. Branch on the decision table in the design doc.
- **Hour 4:** a damage-report source and barrio polygons are found (or the scorecard is pre-registered as "uninformative"), the power check is done, and the video headline is decided. Do not view co-event (C-pair) coherence before `validation/README.md` is committed.

## AI disclosure
This project is built with Claude Code + gstack, OpenAI Codex, Google Antigravity/Gemini, OpenCode (GLM), Grok and LangGraph. Keep this list current in the README and the submission.
