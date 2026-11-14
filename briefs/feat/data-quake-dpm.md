# Brief: feat/data-quake-dpm — Aug 10 2026 quake damage proxy (agent: claude-cacho)

- **Goal:** implement the coherence-loss damage proxy (DPM) for the Eje Cafetero, end to end on real GUNW, under the frozen rules.
- **Issue:** #31 (plan 03-02) · **Plan reference:** docs/designs/bailasar.md § Hazard 2; .planning/ROADMAP.md 03-02; requirements QUAKE-01..03
- **Inputs:** GUNW R/C/K pairs listed below (track 11 first, track 47 second); coherenceMagnitude at 20 m; VIDA or Google/Overture building footprints; land cover for the vegetation mask.
- **Outputs:** `gee_math/earthquake_dpm_math.py` with pure functions (unit-tested) + a CLI `python -m gee_math.earthquake_dpm_math --track 11` that writes `local_cache/quake/dpm_track11.zarr` (or COG) and `local_cache/quake/barrio_dpm.parquet`; `tests/test_earthquake_dpm.py`.
- **Files you may touch:** `gee_math/earthquake_dpm_math.py`, `tests/test_earthquake_dpm.py`, this brief.
- **Out of scope:** scoring/ranking (validation/scoring.py, Maru), GOFF surface rupture, biomass, any UI.
- **Steps:**
  1. Pure functions first, with known-answer tests: Δγ = γ_R − γ_C (unclamped); μ, σ over valid **non-built** pixels; Z = (Δγ−μ)/σ; DPM = max(Z, 0) **after** standardization; built-up ≥ 50% footprint coverage, non-built ≤ 10%; masks for vegetation, water, layover/shadow; barrio DPM_u = median Z of built-up pixels; units with < 20 built-up pixels excluded and counted.
  2. Control pass: same code on γ_K − γ_R.
  3. Stream only the AOI window of `coherenceMagnitude` (h5py + fsspec over HTTPS with the Earthdata token; no full download); align R, C, K on one grid.
  4. Run on track 11 (R = Jul 8→Jul 20, C = Jul 20→Aug 13, K = Jun 26→Jul 8). Record granule IDs, the 12 vs 24-day baseline mismatch, pixel counts, excluded units.
- **Acceptance:** `make ci` green; known-answer tests cover clamp-after-Z, non-built μ/σ, exclusion rule, NaN propagation; a real run prints granule IDs and counts *(measured)*; no C-pair statistic is interpreted before `validation/README.md` is committed (just compute and store).
- **Outward or paid actions needing approval:** none allowed (local only).
- **If blocked:** write `BLOCKED: <reason>` below and stop.

## Facts from the hour-2 gate (measured 2026-11-14, ASF search, read-only)
- NISAR public window starts 2026-06-17. All products found are **provisional** (`PR`, CRID P05023); label them PROVISIONAL.
- Eje Cafetero (quake), GUNW are **single-pol HH** (`SH`), 12-day pairs, except around the event:
  - Track 11 descending, frame 86: … Jun 26→Jul 8 (K), Jul 8→Jul 20 (R), **Jul 20→Aug 13 (C, 24-day; also an `UR` Urgent-Response copy)**, Aug 13→Aug 25 …
  - Track 47 ascending, frame 4: Jun 17→Jun 29, Jun 29→Jul 11 (K), Jul 11→Jul 23 (R), **Jul 23→Aug 16 (C, 24-day)** …
  - **C spans 24 days, R and K 12 days** (the Aug 1 / Aug 4 acquisitions are missing). Per the gate table this is "closest available, mismatch recorded": never hide it; the built-up vs non-built excess E is relative, which partly absorbs extra temporal decorrelation, but report the mismatch next to every number.
- GUNW counts in window: Aburrá 11, Eje Cafetero 11 (+UR), La Mojana 31. GCOV: 14 / 14 / 38.
- AOI bboxes [W,S,E,N] used for search (estimates until set in `config/bailasar.yaml`): Aburrá [-75.70, 6.12, -75.42, 6.45]; Eje Cafetero [-75.85, 4.40, -75.40, 5.15]; La Mojana [-75.40, 7.90, -74.20, 9.20].
- GUNW layers: coherence at 20 m and 80 m, unwrapped phase 80 m, ionosphere screen **included but not applied** (docs/kb/nisar-gunw-layers.md).
- Credentials are in the linked `.env` (Earthdata token works; GEE via `gee_math/ee_session.init_ee()`; never print values). `config/` loader (#17) is not merged yet: read `config/preregistered.yaml` with `yaml.safe_load`, never hardcode its numbers.

## Rules (from AGENTS.md, non-negotiable)
- No synthetic or fabricated data. Missing stays NaN and is marked `missing`. Tests may use small hand-written arrays with hand-computed expected values (tests/ only).
- Every number you report: *(measured)* with the command and granule IDs, or *(estimate)*. Nulls are reported.
- Touch only the files listed below. If you need anything else, write `BLOCKED: <reason>` at the end of this brief and stop.
- Commit locally with Conventional Commits (`git commit -F <file>`), one logical change per commit, body ends with `Co-Authored-By: <your agent name>` and `Refs: #<issue>`. Run `make ci` before each commit and fix failures (never `--no-verify`).
- **Do not** push, merge, switch branches, reset, stash, open PRs, write to GCS, or run paid LLM calls. The orchestrator reviews the full diff and does those.

## Report (append to the end of this file when done)
What you built, commands run with their output tail, measured numbers with IDs, what you could not do, open questions.
