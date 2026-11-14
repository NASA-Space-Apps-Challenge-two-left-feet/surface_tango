# Requirements: BailaSAR

**Defined:** 2026-11-14
**Core Value:** One honest, measured radar result in a 30-second video; a null verdict is a valid headline.

## v1 Requirements

### Setup and data gate (GATE)
- [ ] **GATE-01**: The baseline (PR #14) is merged on `main`; `make setup` installs the hooks; `uv.lock` and `.secrets.baseline` are committed
- [ ] **GATE-02**: An hour-0 checklist proves the Earthdata, GEE, GCS and LLM credentials, each with one read-only call; no secret value is printed
- [ ] **GATE-03**: `nisar_colombia_granules_2026.json` exists from a real discovery run over the 3 AOIs (Jun 17 → Nov 14 2026). Each granule records its ID, product, dates, track/frame, polarizations, version, ionosphere layer and coherence posting
- [ ] **GATE-04**: The R/C/K quake pairs are selected (same track, matched baseline, pre-event K), with CHIRPS per acquisition; the gate decision table is applied and recorded
- [ ] **GATE-05**: Per-tool breaker budgets (p95 + 0.5 s from 10 calls each) are written to `config/bailasar.yaml`
- [ ] **GATE-06**: By hour 4, a ground-truth source (barrio-level damage reports, named and dated) and barrio polygons are found, or "scorecard uninformative" is pre-registered
- [ ] **GATE-07**: By hour 4, a power check (expected units, positives, prevalence, k) is done without viewing C-pair coherence, and the video headline is decided and recorded

### Config and pre-registration (CFG)
- [ ] **CFG-01**: One loader module serves `config/preregistered.yaml` and `config/bailasar.yaml`; no thresholds or AOIs are hardcoded elsewhere
- [ ] **CFG-02**: `preregistered.yaml` is frozen (status: frozen) and its `git hash-object` is recorded in `validation/README.md` before any C-pair viewing

### Data cache (DATA)
- [ ] **DATA-01**: The cache for the headline AOI is built from real granules; missing bands are NaN, marked `missing`; provenance comes from the manifest
- [ ] **DATA-02**: Sentinel-1/2 tiles (real S2, not Google basemap) and GEE stats are pre-staged for every demo view, with source IDs
- [ ] **DATA-03**: `make fetch-cache` plus a release asset (split <2 GB, provenance manifest), published only on the owner's go-ahead

### Quake damage proxy (QUAKE)
- [ ] **QUAKE-01**: Δγ = γ_R − γ_C, Z-scored on non-built pixels; DPM = max(Z, 0) clamped after standardization; vegetation, water and layover masked
- [ ] **QUAKE-02**: Built-up (≥50%) / non-built (≤10%) pixel classes come from footprints; barrio DPM_u is the median Z of ≥20 built-up pixels; excluded units are counted
- [ ] **QUAKE-03**: The control pass on γ_K − γ_R uses the same code
- [ ] **QUAKE-04**: A pipeline check runs on fixtures cut from real cached tiles

### Scoring and scorecard (SCORE)
- [ ] **SCORE-01**: Radar and baseline rankings follow the frozen formula; precision@k with Wilson CI
- [ ] **SCORE-02**: A paired barrio-block bootstrap (seeded); built-up excess E; the beats rule needs all 3 conditions (incl. E_C − E_K CI > 0)
- [ ] **SCORE-03**: The informative gate (≥30 units, ≥5 positives, 10–70% prevalence); no-K and post-K branches never claim "beats"
- [ ] **SCORE-04**: Known-answer pytest with hand-written arrays (tests/ only, listed in ALLOWLIST.md)

### Aburrá landslides (SLIDE)
- [ ] **SLIDE-01**: GUNW phase − the provided ionosphere screen − a stratified troposphere fit; layover mask; LOS → downslope projection
- [ ] **SLIDE-02**: Noise-floor test (|rate| > stable RMS and the sign agrees on 2 pairs), else "no motion detected above X mm (n pairs)"; HKLSI labelled uncalibrated

### La Mojana flood (FLOOD)
- [ ] **FLOOD-01**: A driest-date baseline (HH < −18 dB inside HAND < 18 m); no-baseline branch → absolute water extent, and Class 2 is null
- [ ] **FLOOD-02**: Class 1/2 rules from config; hectares with denominators; ±1 dB and HAND 12/18/24 sensitivity; comparison with the S1 water mask

### MCP servers (MCP)
- [ ] **MCP-01**: Two FastMCP processes on :8001/:8002 with SSE transport (apply the transport patch)
- [ ] **MCP-02**: cache_guard serves only real cached tiles with provenance; an uncached request gets an explicit "not cached" error; per-tool budgets come from config
- [ ] **MCP-03**: `get_earthquake_pair_set`, `rank_first_aid_barrios`, `score_against_baseline` as thin wrappers over `validation/scoring.py`

### Agents and bulletin (AGENT, BULL)
- [ ] **AGENT-01**: LangGraph: ingestion → landslide/earthquake/flood → cross_hazard_synthesis (biomass removed from the graph); `make test-dag` green
- [ ] **BULL-01**: Placeholder-only LLM prose; sensor names allow-listed; unit names rendered via placeholders; `event_facts.json` with primary sources
- [ ] **BULL-02**: ES/EN locale renderer; checker at generation and at serve time (digit, missing key, hash); LLM cache keyed on the tool-output hash

### Frontend (UI)
- [ ] **UI-01**: Local Zarr tile server in `app.py` (apply the patch)
- [ ] **UI-02**: Five panel states (live, cached, not cached, gate result, error); never blank
- [ ] **UI-03**: Curtain slider in two configs (Aburrá/La Mojana: S2/S1/NISAR; quake: post-event S2 / pre coherence / co-event loss + ranked columns)
- [ ] **UI-04**: Story map Ch1–Ch4 resequenced, with no fabricated numbers; labels PROVISIONAL / cached / SI badge; no NASA logos
- [ ] **UI-05**: Math-lab corrections (modules 1–5); first cut if time runs short

### Video and submission (VID, SUB)
- [ ] **VID-01**: Storyboard locked to the hour-4 headline; every on-screen number comes from `validation/` output
- [ ] **VID-02**: Offline `make pitch` walkthrough of every demo view before recording
- [ ] **VID-03**: ≤30 s video, Spanish VO + English subtitles, AI disclosure, agency credits, no NASA logos, no one under 18
- [ ] **SUB-01**: Deadline D recorded; milestones freeze D−8h, record D−6h, edit D−4h, publish D−2h
- [ ] **SUB-02**: Full-history secret scan → repo public → cache release → project page (owner go-ahead at each step)
- [ ] **SUB-03**: README with quickstart, AI disclosure, agency citations (NASA, ISRO, ESA, JAXA only if used), data sources

### Knowledge base (KB)
- [ ] **KB-01**: Event facts verified from primary sources (USGS event ID, SGC bulletin, Granizal record) and quoted in `docs/kb/`
- [ ] **KB-02**: NISAR facts (record window, GUNW layers, polarization) verified against ASF/NASA pages and quoted

## v2 Requirements

- **BIO-01**: Biomass agent (RFDI, WFR, GEDI L4A GBR) and root cohesion in the Factor of Safety
- **SBAND-01**: S-band fusion if Bhoonidhi shows Colombia acquisitions
- **RUPT-01**: GOFF rupture for a future shallow event
- **QPOL-01**: Quad-pol decompositions where available
- **REPLAY-01**: "What radar knew" pass-by-pass replay
- **CASCADE-01**: Coseismic landslide inventory for the Aug 10 event
- **PDF-01**: UNGRD/DAGRD PDF briefing

## Out of Scope

| Feature | Reason |
|---------|--------|
| RSLC → coherence (ISCE3) | Not feasible in 30 h |
| Streamable HTTP MCP | Owner kept SSE (D4) |
| Agent-free render path for the video | Owner kept the agent stack (D17) |
| Bulletin prose LLM eval | Optional, not approved |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| GATE-01, GATE-02, CFG-01, SCORE-04, MCP-01, MCP-02, UI-01, UI-02, BULL-01 | Phase 1 | Pending |
| GATE-03, GATE-04, GATE-05, GATE-06, GATE-07, CFG-02, KB-01, KB-02, SUB-01 | Phase 2 | Pending |
| DATA-01, DATA-02, QUAKE-01, QUAKE-02, QUAKE-03, SCORE-01, SCORE-02, SCORE-03, SLIDE-01, SLIDE-02, FLOOD-01, FLOOD-02, MCP-03, AGENT-01, BULL-02, UI-03, UI-04 | Phase 3 | Pending |
| QUAKE-04, VID-01, VID-02, UI-05, DATA-03 | Phase 4 | Pending |
| VID-03, SUB-02, SUB-03 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 43 total
- Mapped to phases: 43
- Unmapped: 0

---
*Requirements defined: 2026-11-14*
*Last updated: 2026-11-14 after GSD Core ingest of docs/designs/bailasar.md*
