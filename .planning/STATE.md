---
gsd_state_version: '1.0'
status: planning
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 30
  completed_plans: 2
  percent: 6
---
<!-- STATE-MD-SCHEMA:END:frontmatter -->

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-11-14)

**Core value:** One honest, measured radar result in a 30-second video; a null verdict is a valid headline.
**Current focus:** Phase 2: Data gate and pre-registration (h2–h4)

## Current Position

Phase: 1 of 5 (Foundation) and 2 of 5 (Data gate) in parallel
Plan: 01-01 done (#16); 02-01 done (#23, reports/gate.md); 03-01 code merged (#78, review fixes included)
Status: Acting-orchestrator handback (opencode GLM-5.3) to claude-home, 2026-11-15 ~03:2x UTC
Last activity: 2026-11-15 — merge batch: #77 (repo tooling python port), #78 (3-AOI real-data cache builder + review fixes), #79 (ASF MCP server imports without netrc); public-readiness audit completed on chore/data-public-readiness-audit (91e1721, unpushed)

Progress: [░░░░░░░░░░] 0%

## Accumulated Context

### Decisions

Decisions are logged in the PROJECT.md Key Decisions table (D1–D17 of the design doc).

### Pending Todos (handback to claude-home)

- Merged tonight (squash): #77 a2fe452 (python tooling + language rule — teammates must run `make sync && uv run pre-commit install`), #78 423f517 (cache builder; review fixes: GEE sentinel NaN, conncomp nearest, CHIRPS window from args; README cache row flipped to cached), #79 61d57c9 (ASF MCP server imports without netrc — #28 timing unblocked; tell Jack).
- Push and merge `chore/data-public-readiness-audit` (91e1721): `make sync` first (main moved), open the PR ready, merge. Verdict: READY, 0 blockers, 3 fix-before-public (license TODO, biomass leftovers, README pull quotes); finding 3 (docs/baseline story-map patches) is already resolved by #77 — say so in the PR body.
- Esteban's drafts #72–#76 are stale (opened before the 02:15–02:18 UTC batch): comment and ask for `make sync` + re-push. #74/#75/#76 would revert merged files; #72/#73 hold wanted work (config-driven thresholds; fixture harness).
- grok (Aburrá #33) is stalled: CLI device code expired (needs `grok login --device-auth`). Three unpushed commits, including the FABDEM meter-projection slope fix (9fe0077) — review it; cached `slope_deg` bands are suspect until the fix lands and the cache rebuilds (docs/kb/gee-terrain-slope-needs-metric-crs.md).
- grok2 (Mojana #34) is stalled at a trust prompt in the WRONG directory (~/Documents/Landslide_Agentic): restart it inside its surface_tango worktree. Three unpushed commits (83d458c): bounded 90 m GCOV reads, dual-pol class functions; hang diagnosis is in its brief (docs/kb/nisar-gcov-read-timeouts.md).
- After the grok lanes finish: rebuild the 3-AOI cache (regenerates conncomp with nearest resampling and reviewed slope; ~4 min per AOI, measured 2026-11-14) — never while grok2's reads run.
- Deep review of merged #65 (scripts/prestage_tiles.py) still pending (handoff item 2 from 21:22).
- Post-batch README pass, now including the "Diagrams kept current in the README" rule added to AGENTS.md/CLAUDE.md tonight: assign the mermaid Architecture / Agents & orchestration / Data-flow blocks and the animated diagrams (docs/diagrams/, script-generated; style per the owner's factored-hackathon, 30x_Blinky, Landslide_Agentic, hydroinformati-k_secop projects — approach only, nothing copied).
- Sync the KB to gbrain (/sync-gbrain): notes added tonight — earthaccess auth, CHIRPS lag, ionosphere screen applied, FABDEM slope CRS, GCOV read timeouts.

### Blockers/Concerns

- Owner-only: record the submission deadline D (plan 02-07); re-auth grok (`grok login --device-auth`); restart grok2 in the right directory; GitHub invite cancellation (needs `gh auth refresh -s admin:org` or the browser); delete the empty `anthropic-api-key` Secret Manager secret (owner OK); gcloud ADC per teammate (quota project loyal-curve-472605-g7; GCS_BUCKET=bailasar-cache-472605 in own .env plus own ANTHROPIC_API_KEY); Leonardo's Windows docker-compose gcloud mount issue.
- Unresolved from eng review: local NISAR compute vs GCS→GEE (OV9); cache-build bandwidth owner (OV13); 4 pre-registration details (OV14). Resolve before 02-04 freezes the config.
- The video depends on the agent stack (D17, accepted risk).
