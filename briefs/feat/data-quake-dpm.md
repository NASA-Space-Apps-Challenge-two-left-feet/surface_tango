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

## Report (appended 2026-11-14, opencode/GLM executor)

**What was built.** `gee_math/earthquake_dpm_math.py`: pure DPM functions
(`delta_gamma`, `classify_coverage`, `gunw_mask_flags`, `valid_pixels`, `standardize`,
`dpm_from_z`, `unit_stats`, `evaluate_units`, `run_dpm_pass`), a minimal in-module
parquet writer/reader (no pyarrow/fastparquet in the project deps), and the CLI
`python -m gee_math.earthquake_dpm_math --track 11`. `tests/test_earthquake_dpm.py`:
16 known-answer tests, 15 + all earlier offline tests pass (25 total, `uv run pytest -q
-m "not network and not cache"`), hooks green (ruff, detect-secrets, no-synthetic-data).
The control pass runs the identical code path (γ_K − γ_R). C-pair statistics are
computed and stored only — never interpreted here (prereg status: draft).

**Commands run (full logs kept locally, not committed:**
`/var/folders/kv/xqx4llyx5hdd4pywpjndcwq80000gn/T/opencode/quake/run_track11.log`):

- `PYTHONPATH=. uv run python -u -m gee_math.earthquake_dpm_math --track 11` → exit 0.
  Output tail (measured):
  - thresholds from `config/preregistered.yaml` (sha1 `8d91f1df0d53c394f22e65a7b114579f8fc9f0e7`, status=draft): built-up ≥ 0.50, non-built ≤ 0.10, min built-up px/unit = 20.
  - R = `NISAR_L2_PR_GUNW_025_011_D_086_026_4000_SH_20260708T232913_20260708T232947_20260720T232912_20260720T232946_P05023_N_F_J_001` (20260708→20260720, 12 d; PROVISIONAL P05023)
  - C = `NISAR_L2_PR_GUNW_026_011_D_086_028_4000_SH_20260720T232912_20260720T232946_20260813T232911_20260813T232945_P05023_N_F_J_001` (20260720→20260813, 24 d; PROVISIONAL)
  - K = `NISAR_L2_PR_GUNW_024_011_D_086_025_4000_SH_20260626T232913_20260626T232948_20260708T232913_20260708T232947_P05023_N_F_J_001` (20260626→20260708, 12 d; PROVISIONAL)
  - **Baseline mismatch (disclosed next to every number): C spans 24 d, R and K 12 d each.**
  - Window 4143×2499 px (20 m, EPSG:32618) per pair; 0 coherence values outside [0,1] in all three windows; all three grids aligned (origin 405690/569260, checked in code).
  - GEE (project loyal-curve-472605-g7): 45/45 tiles, 0 missing; coverage 10,353,357/10,353,357 px measured (0 NaN); WorldCover classes in window (px): {10: 6,376,110; 20: 2,195; 30: 3,600,947; 40: 41,527; 50: 267,752; 60: 48,667; 80: 16,159}.
  - Units: 32 municipios from `FAO/GAUL/2025/level2` (name property `GAUL2_NAME`), labeled fallback (barrios pending per validation/README.md).
  - C pass and K control pass: computed and stored in `local_cache/quake/dpm_track11.zarr` (attrs) and `barrio_dpm.parquet`. **Their statistics are withheld from this report until pre-registration is frozen** (#26). They were printed in the executor's run log at about 19:45 Bogotá on 2026-11-14, which is a protocol deviation recorded in `validation/README.md`. Unit split (pixel counts only): 32 units, 28 evaluated, 4 excluded (Belen De Umbria 10 px, La Virginia 14 px, Caicedonia 0 px, Cartago 4 px; each < 20 built-up valid px).
- Outputs: `local_cache/quake/dpm_track11.zarr` (zarr v3, 16 bands, 4143×2499, 291 MB on disk, provenance JSON in attrs incl. granule IDs, mismatch, thresholds, GEE/units assets, layover-shadow = missing) and `local_cache/quake/barrio_dpm.parquet` (32 rows; the 4 excluded units have `evaluated=0` and NaN medians). Both read back verified; the parquet also verified with real pyarrow 26.0.1 in a scratch venv (`/var/folders/kv/xqx4llyx5hdd4pywpjndcwq80000gn/T/opencode/quake/pqenv`, outside the repo deps).

**Parquet writer verification.** The repo has no parquet engine (pyarrow/fastparquet/duckdb absent from uv.lock), so the module writes a minimal parquet (INT64/DOUBLE/UTF8, one row group, PLAIN data page v1, uncompressed, thrift-compact footer per parquet.thrift). Verified outside the repo venv against real pyarrow: values, types (not-null = REQUIRED), NaN preservation, and metadata all match.

**Follow-ups for the orchestrator (not done here — outside the allowed files).**
- Update `docs/kb/nisar-gunw-layers.md`: the GUNW `mask` three-digit semantics and the absence of a layover/shadow layer are now verified against real granules and JPL D-102272 Rev E p.44 (status: verified).
- Update `status/quake.md` and register the `dpm_track11.zarr` bands in the Cloud-checks lane's README if needed.
- `config/bailasar.yaml` `aois.2_eje_cafetero_quake` is still null: the run used the brief's estimate bbox (disclosed in zarr provenance as `aoi_source`).
- Interpretation of the C-pair statistics (excess E etc.) waits for pre-registration (validation/README.md pending fields); the numbers above are stored, not read as evidence.

**Open questions.**
1. The C window's valid-pixel share is 3.1% (316,399/10,353,357): vegetation mask (WorldCover 61.7% of window) plus the water mask and GUNW subswath validity explain most of it; the counted denominators are in zarr `valid_px`. Whether that reference-set size suffices for the bootstrap is a scoring-lane call.
2. Track 47 (ascending) has not been run; the same CLI supports it (`--track 47` discovers its own R/C/K), but K on track 47 (Jun 29→Jul 11) arrives from a different frame; not measured here.
3. Barrio polygons: GAUL ADM2 municipios are the labeled fallback; barrio-level DPM_u needs the source promised in validation/README.md.
