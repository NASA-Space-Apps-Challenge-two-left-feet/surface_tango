# Roadmap: BailaSAR

## Overview

Five phases, from an empty trunk to a submitted 30-second video:
1. Foundation, before any data: hooks, config, logic tests, servers, UI states.
2. The data gate: real granules, ground truth, power check, frozen pre-registration and headline, all by hour 4.
3. The science and the stack, in parallel lanes.
4. Integration and freeze.
5. Submission.

Plans inside a phase run in parallel waves. Each plan is one branch, one worktree and one PR, with an owner and files that no other plan in the same phase touches (AGENTS.md project map). The hours are measured from kickoff (hour 0). D is the official submission deadline, recorded in plan 02-07.

## Phases

- [ ] **Phase 1: Foundation (h0–h2)** — trunk ready; config loader; logic tests; SSE servers + cache_guard; tile server + panel states
- [ ] **Phase 2: Data gate and pre-registration (h2–h4)** — real granules, pairs, budgets, ground truth, power check, frozen config, headline, verified KB facts
- [ ] **Phase 3: Science and stack (h4–h14)** — cache, quake DPM, scorecard, Aburrá, La Mojana, MCP tools, agents + bulletin, slider + story
- [ ] **Phase 4: Integration and freeze (h14–D−8h)** — real-tile pipeline checks, storyboard, offline walkthrough, math-lab, cache release prep
- [ ] **Phase 5: Submission (D−8h–D)** — record and edit the video, go public, release, README and project page

## Phase Details

### Phase 1: Foundation (h0–h2)
**Goal**: Every lane can work in its own worktree on a green trunk, with the interfaces its later work plugs into.
**Depends on**: Nothing (first phase)
**Requirements**: GATE-01, GATE-02, CFG-01, SCORE-04, MCP-01, MCP-02, UI-01, UI-02, BULL-01
**Success Criteria** (what must be TRUE):
  1. PR #14 is merged; `make setup && make ci` pass on a fresh worktree
  2. Every credential is proven by one read-only call; no secret is printed
  3. Scoring logic tests with known answers pass before any data exists
  4. Both MCP servers start on :8001/:8002 (SSE); an uncached request returns "not cached"
  5. The UI shows the five panel states with no data loaded
**Plans**: 7 plans

Plans:
- [ ] 01-01: Merge baseline, `make setup`, `uv lock`, `.secrets.baseline`, hour-0 credential checks — **LEONOB2014** — `pyproject.toml`, `uv.lock`, `.secrets.baseline`, `scripts/check_credentials.py`
- [ ] 01-02: Config loader for preregistered/operational YAML; remove hardcoded thresholds and AOIs — **Jack4Codes** — `config/`, `src/bailasar/config.py`, `tests/test_config.py`
- [ ] 01-03: Known-answer tests and pure functions for ranking, precision@k, Wilson, block bootstrap, beats rule, informative gate — **Maru816** — `validation/scoring.py`, `validation/ALLOWLIST.md`, `tests/test_scoring.py`
- [ ] 01-04: Wire landslide and flood modules to the config; logic tests for the flood no-baseline rule and the noise-floor rule — **EstebanOchoaedos** — `gee_math/landslide_insar_math.py`, `gee_math/flood_polarimetric_math.py`, `tests/test_flood.py`, `tests/test_landslide.py`
- [ ] 01-05: SSE transport on both servers; cache_guard provenance, the "not cached" error and per-tool budgets from config — **alicealanapineda-byte** — `mcp_servers/`, `tests/test_cache_guard.py`
- [ ] 01-06: Bulletin allow-list, the placeholder schema and the `event_facts.json` structure — **alicealanapineda-byte** — `agents/bulletin.py`, `validation/event_facts.json`, `tests/test_bulletin.py`
- [ ] 01-07: Apply the tile-server patch to `app.py`; five panel states in the UI; remove the biomass node from the UI graph — **SaritaRpo** — `app.py`, `static/`

### Phase 2: Data gate and pre-registration (h2–h4)
**Goal**: By hour 4 we know what data exists, whether the quake scorecard can be informative, and which headline the video will carry. The frozen parameters are committed before any C-pair viewing.
**Depends on**: Phase 1 (01-01 for credentials; 01-02 for config; 01-05 for timing)
**Requirements**: GATE-03, GATE-04, GATE-05, GATE-06, GATE-07, CFG-02, KB-01, KB-02, SUB-01
**Success Criteria** (what must be TRUE):
  1. `nisar_colombia_granules_2026.json` is committed from a real run, and the gate decision table result is recorded
  2. A ground-truth source and polygons are named, or "uninformative" is recorded, by hour 4
  3. `config/preregistered.yaml` is frozen, and its hash is in `validation/README.md` before C-pair viewing
  4. The video headline is decided at hour 4 from the power check
  5. Event and NISAR KB notes are `verified`, with primary-source quotes
  6. The deadline D and the backward milestones are recorded
**Plans**: 7 plans

Plans:
- [ ] 02-01: Run discovery over 3 AOIs; select R/C/K (same track, matched baseline, pre-event K); CHIRPS per date; apply the gate table — **LEONOB2014** — `scripts/discover_nisar_colombia.py`, `nisar_colombia_granules_2026.json`, `reports/gate.md`
- [ ] 02-02: Find barrio-level damage reports and official barrio polygons for Pereira/Armenia/Manizales (hard timebox hour 4) — **Maru816** — `docs/kb/data-ground-truth-*.md`, `reports/ground_truth.md`
- [ ] 02-03: Power check from polygons and ground truth only (expected units, positives, prevalence, k); record the headline decision — **Jack4Codes** — `validation/README.md`
- [ ] 02-04: Fill pair IDs and the ground-truth source in `preregistered.yaml`; set `status: frozen`; record the hash — **Jack4Codes** — `config/preregistered.yaml` (validation/README.md hash row via 02-03 owner review)
- [ ] 02-05: Verify KB facts from primary pages (USGS event ID, SGC bulletin, Granizal record, ASF NISAR notices, GUNW spec, polarimetry) and update `event_facts.json` sources — **EstebanOchoaedos** — `docs/kb/`, `validation/event_facts.json` (sources only)
- [ ] 02-06: Time 10 calls per live tool; write p95 + 0.5 s budgets — **Jack4Codes** — `config/bailasar.yaml` (`breaker_budgets_s` only), `reports/tool_latency.md`
- [ ] 02-07: Record the official submission deadline D and the backward milestones; post them in the team channel — **alicealanapineda-byte** — `docs/designs/bailasar.md` (schedule section)

### Phase 3: Science and stack (h4–h14)
**Goal**: Each hazard has a measured result or a documented null, and the stack shows them end to end through the agents.
**Depends on**: Phase 2 (frozen config; gate JSON; headline)
**Requirements**: DATA-01, DATA-02, QUAKE-01, QUAKE-02, QUAKE-03, SCORE-01, SCORE-02, SCORE-03, SLIDE-01, SLIDE-02, FLOOD-01, FLOOD-02, MCP-03, AGENT-01, BULL-02, UI-03, UI-04
**Success Criteria** (what must be TRUE):
  1. The headline-AOI cache is built from real granules; missing stays NaN and is marked `missing`
  2. The quake scorecard (or "uninformative") is computed under the frozen rules, with the control pass
  3. Aburrá shows a velocity above the noise floor or a documented null; La Mojana shows hectares with sensitivity, or the no-baseline statement
  4. `make test-dag` renders an ES/EN bulletin that passes the checker
  5. The curtain slider and story chapters show only measured outputs
**Plans**: 8 plans

Plans:
- [ ] 03-01: Build the cache for the headline AOI, then the other AOIs; pre-stage real S1/S2 tiles and GEE stats with source IDs (replace the Google basemap) — **LEONOB2014** — `scripts/prewarm_antioquia_cache.py`, `scripts/prestage_tiles.py`
- [ ] 03-02: Quake DPM: non-built Z, clamp, masks, built-up classes, barrio DPM_u, control pass — **LEONOB2014** — `gee_math/earthquake_dpm_math.py`, `tests/test_earthquake_dpm.py`
- [ ] 03-03: Scorecard on real units: rankings, precision@k + Wilson, paired block bootstrap, E_C − E_K, informative gate → `reports/scorecard.md` — **Maru816** — `validation/scoring.py`, `reports/scorecard.md`
- [ ] 03-04: Aburrá InSAR pipeline and noise-floor verdict — **LEONOB2014** — `gee_math/landslide_insar_math.py`, `reports/aburra.md`
- [ ] 03-05: La Mojana: driest-date baseline, Class 1/2, sensitivity, S1 comparison — **LEONOB2014** — `gee_math/flood_polarimetric_math.py`, `reports/mojana.md`
- [ ] 03-06: MCP tools `get_earthquake_pair_set`, `rank_first_aid_barrios`, `score_against_baseline` (wrappers over scoring) — **Jack4Codes** — `mcp_servers/`
- [ ] 03-07: LangGraph 3-agent graph; locale renderer; checker at generation and serve time; LLM cache keyed on the tool-output hash — **alicealanapineda-byte** — `agents/`
- [ ] 03-08: Curtain slider (two configs) and story map Ch1–Ch4 from measured outputs (rewrite the story patch without fabricated numbers) — **SaritaRpo** — `static/`

### Phase 4: Integration and freeze (h14–D−8h)
**Goal**: The demo runs offline end to end from real data, and the video script is locked to the true outcome.
**Depends on**: Phase 3
**Requirements**: QUAKE-04, VID-01, VID-02, UI-05, DATA-03
**Success Criteria** (what must be TRUE):
  1. Pipeline checks pass on fixtures cut from real cached tiles
  2. The storyboard uses only numbers from `reports/` and `validation/`
  3. `make pitch` with the network off renders every demo view with the right panel states
  4. `make fetch-cache` works from a fresh clone (release asset staged, not published)
**Plans**: 5 plans

Plans:
- [ ] 04-01: Real-tile fixture pipeline checks for quake, landslide and flood — **EstebanOchoaedos** — `tests/fixtures/`, `tests/test_pipeline_*.py`
- [ ] 04-02: Lock the storyboard to the hour-4 headline and the measured outcome; mark placeholder frames — **SaritaRpo** — `video/storyboard.md`
- [ ] 04-03: Offline `make pitch` walkthrough checklist with the network disabled — **Maru816** — `tests/e2e_pitch.md`
- [ ] 04-04: Math-lab corrections (modules 1–5); first cut if time runs short — **SaritaRpo** — `static/mathlab/`
- [ ] 04-05: Cache release assets (split <2 GB, provenance manifest) and `make fetch-cache`; staged, not published — **EstebanOchoaedos** — `Makefile` (cache targets), `scripts/fetch_cache.sh`

### Phase 5: Submission (D−8h–D)
**Goal**: The judged deliverables are submitted on time, honestly and safely.
**Depends on**: Phase 4
**Requirements**: VID-03, SUB-02, SUB-03
**Success Criteria** (what must be TRUE):
  1. The ≤30 s video with Spanish VO and English subtitles is hosted with a public link
  2. The full-history secret scan is clean before the repo goes public
  3. The README carries the quickstart, AI disclosure and agency citations
**Plans**: 4 plans

Plans:
- [ ] 05-01: Record the video at D−6h from mission control — **SaritaRpo** — `video/`
- [ ] 05-02: Spanish VO, English subtitles, AI disclosure and credits; edit at D−4h — **Maru816** — `video/subtitles/`, `video/vo/`
- [ ] 05-03: README, AI disclosure, agency citations, data sources; project page text — **EstebanOchoaedos** — `README.md`, `docs/submission.md`
- [ ] 05-04: Secret scan → repo public → cache release → submit (owner go-ahead at each step) — **LEONOB2014** — release only

## Load per person (plans)

Cloud rule: GEE processing and GCP buckets/VMs are worked only by LEONOB2014, Jack4Codes and EstebanOchoaedos (they hold the accounts). LEONOB2014 owns the three hazard models.

| Person | P1 | P2 | P3 | P4 | P5 | Total |
|---|---|---|---|---|---|---|
| LEONOB2014 (orchestrator, data gate, hazard modeling) | 01-01 | 02-01 | 03-01, 03-02, 03-04, 03-05 | — | 05-04 | 7 |
| Jack4Codes (config, pre-registration, cloud tools) | 01-02 | 02-03, 02-04, 02-06 | 03-06 | — | — | 5 (+ GCP setup #48) |
| EstebanOchoaedos (module prep, KB, cloud cache checks, README) | 01-04 | 02-05 | — | 04-01, 04-05 | 05-03 | 5 |
| Maru816 (scoring, ground truth, VO) | 01-03 | 02-02 | 03-03 | 04-03 | 05-02 | 5 |
| alicealanapineda-byte (MCP offline, agents, bulletin, schedule) | 01-05, 01-06 | 02-07 | 03-07 | — | — | 4 |
| SaritaRpo (UI, video) | 01-07 | — | 03-08 | 04-02, 04-04 | 05-01 | 5 |

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/7 | Not started | - |
| 2. Data gate | 0/7 | Not started | - |
| 3. Science and stack | 0/8 | Not started | - |
| 4. Integration and freeze | 0/5 | Not started | - |
| 5. Submission | 0/4 | Not started | - |
