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
Plan: 01-01 done (#16); 02-01 done (#23, reports/gate.md); 03-01 code merged (#78, review fixes included); diagrams current (#89)
Status: claude-home offline; opencode GLM-5.3 acting orchestrator (owner-delegated, from 06:17 UTC 2026-11-15). Previous snapshot: claude-home, refreshed 2026-11-15 05:18 UTC.
Since ~04:45 UTC, all squash-merged into main:
- **Sarita:** #105 mission control loads the staged tiles.
- **Fixes:** #106 flood timeout on Windows. #108 Esteban's type annotations.
- **Esteban:** #107 his fixture harness core; #72/#73 closed as superseded (reasons on the PRs).
- **#109 Aburrá lane:** the orchestrator calibrated the keep-rule against a sign-flip null. Verdict: **no motion detected above 9.105 mm (17 pairs)**; kept fraction below the null mean on both tracks.
- **#111 quake DPM v2** (opencode): both tracks, sealed C/K statistics, pyarrow, pluggable units; track 11 reproduces #64 exactly.
- **#110 Jack's MCP scoring wrappers.**
- #65 deep-reviewed (correct; window constant should move to config).
- #113, #114: both README diagrams fixed (overlaps cleared, content current), reviewed as rendered images.
- #115: the landslide module reads and verifies `landslide.noise_floor`. `VALLEY_FLOOR_MAX_SLOPE_DEG` (5.0) and `MIN_ABS_COS_XI` (0.2) are still code constants and should enter the pre-registration at the freeze (#26).

Session 3 (opencode acting orchestrator, 06:17–06:45 UTC), squash-merged:
- **#130 pre-registration freeze** (Jack; squash 3166d0f). Verified before merge: recorded blob `b4f9cb89910e78fa7ad9fd53a2a4b3fca437b438` recomputed and matches; diff vs the deviation-1 anchor `8d91f1d` contains only the three listed changes (noise_floor #72, pair fill #86, freeze + uninformative ground truth); 299 offline tests at the PR head. **C/K statistics unsealed by rule.** Issues #24/#26 closed (#25 already closed).
- **#132 quake depth displayable** (Esteban; squash e818fba): `depth_km` 116, the USGS preferred-origin estimate 116.13 km rounded half-up, labelled "USGS estimate"; SGC 105 km evidence-only. 301 offline tests at the head. Follow-up: the agents lane updates `status/agents-mcp.md`.
- README pass in the same session (this PR): the freeze-pending rows correctly say frozen.

#### Headline results now on main (all PROVISIONAL)
- **La Mojana (headline, #102):** open water per date measured (e.g. 2026-06-17: 4,486.59 ha, 5,539 of 197,758 valid px). Sentinel-1 missed 3,351 of 4,946 NISAR open-water px on 2026-07-11. Change classes degenerate (reference date had 1 valid px).
- **Aburrá:** calibrated null, no motion above 9.105 mm.
- **Quake:** scorecard uninformative (no barrio labels); damage proxy cached for tracks 11 and 47; C/K statistics unsealed at the freeze (#130), artifacts pending the data lane.

#### Open work, in order
1. ~~Jack: fix #86, then freeze #26~~ **done** (#86 as #126's pair fill; freeze #130).
2. ~~Alice: rewire the fusion tools~~ **done via #126** (evidence adapters; no module imports). Remaining Alice work: #36 LangGraph/bulletin rendering.
3. Sarita: #37 slider and story map on La Mojana; lock storyboard #39 to the ratified headline.
4. ~~Esteban: flood harness port (#38 done as #121), kb-quake-depth (#123/#129/#132 done)~~.
5. Orchestrator: rebuild the cache now that both hazard lanes merged (conncomp nearest-resampling, metric slope), then re-stage the team release.
6. opencode (in flight, no self-merge): `feat/data-flood-quake-evidence` per its brief — flood + quake evidence serializers in `scripts/write_hazard_evidence.py` + tests; artifacts into `local_cache/mojana/` and `local_cache/eje_cafetero/`; the C/K gate keys on the current prereg status (frozen → `coherence_statistics` included). Ready for review within the hour; push + PR by the orchestrator.

#### Agents
grok and grok2 are idle (their lanes are merged). opencode is acting orchestrator + executing the flood/quake evidence brief. Antigravity is idle.

Progress: [░░░░░░░░░░] 0%

## Accumulated Context

### Decisions

Decisions are logged in the PROJECT.md Key Decisions table (D1–D17 of the design doc).

### Pending Todos (handback to claude-home, in order)

1. **Review Jack's two ready PRs.** #86 `feat/config-fill-preregistered-pairs` (quake R/C/K pair IDs per track, from the hour-2 gate) and #87 `feat/agents-mcp-tool-latency` (search_nisar_granules breaker budget from timed calls — this is the #28 budget measurement landing; check the evidence, and that config/bailasar.yaml's breaker default flips from estimate to measured). Both are based on branches made this evening — require `make sync` + re-push if behind origin/main before merging.
2. **Visually review the two animated diagrams on the GitHub README** — docs/diagrams/architecture.svg and lakehouse.svg. The opencode session cannot view images, so it validated structure only (XML well-formed, rsvg-convert renders, 63 offline tests green; #89). Check: the flows actually animate on the README (CSS `@keyframes` inside the SVG — the pattern is verified on the owner's factored repo, which GitHub camo serves unmodified), no node/label collisions, the grey-dashed items still match the status table. Any fix goes in scripts/diagrams/*.py + `make diagrams` (deterministic regeneration, guards in tests/test_diagrams.py).
3. **grok lanes: both recovered, still ahead of their remotes.** aburrá `fa8dcfc` (ahead 25, behind 1) and mojana `74007f5` (ahead 29, behind 1); both trees clean. Behind-1s are stale remote brief docs (2178e2b, fffaf64 — early brief pushes before the lanes rewrote their briefs): reconcile by rebase, then push — do not force-push blind. Review at least: aburrá 9aa36a7 (FABDEM meter-projection slope fix — cached slope_deg stays suspect until it lands; docs/kb/gee-terrain-slope-needs-metric-crs.md) and reports/aburra.md (noise floor 9.105 mm · 17 pairs · 88,517 px, PROVISIONAL — keep the provisional label); mojana's bounded 90 m GCOV reads, dual-pol classes, and the appended classification report.
4. **After the grok lanes merge: rebuild the cache** (~4 min per AOI, measured 2026-11-14). It must regenerate conncomp bands with #78's nearest resampling and the reviewed slope — never rebuild while grok2's reads run. Re-verify manifests (finite ratios) and update the README cache numbers if they shift.
5. **Esteban:** #72/#73 remain stale (make sync + re-push or close; #74–#76 already closed by author). New drafts: #88 submission text, #90 kb english gloss — review against the evidence and branding rules.
6. **Deep review of merged #65 (scripts/prestage_tiles.py)** still pending.
7. **Post-batch README pass** per the AGENTS.md "Diagrams kept current in the README" rule: mermaid blocks are current through #89; add each lane's status row as it merges; measured stickers stay linked to their reports.
8. **/sync-gbrain** — the KB now holds 15+ notes (tonight's 5: earthaccess auth, CHIRPS lag, ionosphere screen applied, FABDEM slope CRS, GCOV read timeouts).

### Settled in session 2 — do not redo

- **Audit published (#83) with a session addendum rechecked at 6d8ae27:** findings 1 (no LICENSE, README TODO) and 2 (biomass wiring at agents/orchestrator.py:132,141,145 + static/index.html:283,356) remain open; finding 3 narrowed to `docs/baseline/unapplied_patches/story_map_hud.html:33` (tour.js already gone). gitleaks 8.30.1 rescan of `fc52bfd..6d8ae27`: 6 commits, ~100.65 KB, no leaks (94 ms). Verdict READY, 0 blockers. Fix-before-public list: license, biomass wiring, hud numbers.
- **Mermaid parse error explained:** a `;` inside Note/message text is a statement terminator, everything after it becomes INVALID (#82, was line 35 of the orchestration sequence). All three README mermaid blocks parse via mermaid-cli 12.2.0.
- ** Animated-diagram rule (AGENTS.md, changed in #89):** script-generated SVG into docs/diagrams/ via `make diagrams`; CSS `@keyframes` inside the file animate on the GitHub README; `prefers-reduced-motion` required; decks/asset stores strip CSS — render `rsvg-convert` PNG/GIF for those; numbers in a diagram must be measured with sources named in the footer; never draw dropped/unbuilt components as built.
- **Honour markers in the diagrams:** grey dashed = not built yet / branch-under-review (SSE serving, UI panels, the 9.105 mm noise floor until its lane merges); red dashed = recorded gaps never fabricated (late CHIRPS windows, eje gcov_hvhv_post single-pol, C-pair 24-day mismatch); biomass is not depicted.

### Transfer notes (pitfalls, tools, limits — from the opencode sessions)

- **Silent SVG truncation bug class:** an unparenthesized multi-line string literal after `return` drops its continuation silently (no lint fires; found live in the lakehouse glyph code). Guard shipped: tests/test_diagrams.py::test_both_svgs_are_well_formed_xml parses both builds with ElementTree.
- The word `synthesiz*` is banned anywhere under scripts/ etc. by tests/test_repo_rules.py (the no-synthetic scanner) — write "fabricated" in prose there; the README is outside the scanner.
- zsh pitfalls: unquoted `===` in echo dies; missing trailing newlines trigger the fix-end-of-files hook auto-fix (re-stage + re-commit). commitizen `cz` exit 16 lies — verify the files, not the exit code.
- Tools verified on this machine: `npx -y @mermaid-js/mermaid-cli` 12.2.0 (offline mermaid parsing), rsvg-convert 2.62.3, gitleaks 8.30.1.
- The opencode session cannot view images and cannot webfetch the private repo (use `gh api`). That is why the diagram visual review is delegated (item 2).
- Identity (user-confirmed): project **Surface Tango**, team **two left feet**, challenge *Dancing with the SARs*, engine code name `bailasar`. Both diagrams carry this header.

### Blockers/Concerns

- Owner-only: record the submission deadline D (plan 02-07; blocks reviewing #88 properly); license decision (audit finding 1); biomass gate-or-remove decision (finding 2); GitHub invite cancellation (`gh auth refresh -s admin:org`); delete the empty `anthropic-api-key` secret; per-teammate gcloud ADC (quota project `loyal-curve-472605-g7`; `GCS_BUCKET=bailasar-cache-472605` in each own .env); Leonardo's Windows docker-compose gcloud mount; make the GCS cache bucket public-read before reviewers run `make fetch-cache`.
- grok stall items from the previous handback are RESOLVED (both lanes commit again; tmux shows grok running).
- Unresolved from eng review: local NISAR compute vs GCS→GEE (OV9); cache-build bandwidth owner (OV13); 4 pre-registration details (OV14). Resolve before 02-04 freezes the config.
- The video depends on the agent stack (D17, accepted risk).
