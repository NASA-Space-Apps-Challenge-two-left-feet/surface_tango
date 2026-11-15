# Brief: feat/data-cache-builder — real-data cache for all three AOIs (agent: antigravity)

- **Goal:** generalize the cache builder from one AOI to the three agreed AOIs, real granules only, with a provenance manifest.
- **Issue:** #30 (plan 03-01, part DATA-01) · **Plan reference:** docs/designs/bailasar.md § Data layer; requirement DATA-01
- **Inputs:** `scripts/prewarm_antioquia_cache.py` (synthesizer already removed; missing → NaN + "missing"); the gate catalog `local_cache/**/nisar_colombia_granules_2026.json` (produced by the orchestrator on feat/gate-nisar-discovery; if absent, call `asf_search` yourself with the bboxes above); `init_ee()` for FABDEM/CHIRPS.
- **Outputs:** the builder takes `--aoi {aburra,eje_cafetero,mojana}`; writes `local_cache/<aoi>/` COGs + one Zarr per AOI + `manifest.json` (every band: source granule ID or GEE asset ID, version PR/validated, acquisition dates, or "missing"); `tests/test_cache_builder.py`.
- **Files you may touch:** `scripts/prewarm_antioquia_cache.py` (you may rename it to `scripts/build_cache.py` and keep a thin wrapper), `tests/test_cache_builder.py`, this brief.
- **Out of scope:** Sentinel-1/2 tiles (feat/data-prestage-tiles), any modeling math, GCS uploads, UI.
- **Steps:**
  1. Tests first (hand-written arrays): a band that fails to load is NaN and "missing" in the manifest; coverage check counts finite pixels; manifest lists IDs for every band.
  2. Read AOIs from one place (a dict at the top for now, matching the bboxes above) so the config loader can replace it later.
  3. Remove the hardcoded CHIRPS dates (2026-10-29..11-13): take the window from the arguments; CHIRPS daily is published weeks late, so record "missing" instead of failing.
  4. Build the Eje Cafetero cache first (track 11 R/C/K coherence), then Aburrá, then La Mojana.
- **Acceptance:** `make ci` green; a run for `--aoi eje_cafetero` writes a manifest whose every band has a granule/asset ID or "missing" *(measured file list + sizes)*; `rg 'np\.random|synthesiz' scripts/` is empty.
- **Outward or paid actions needing approval:** none (local only; no GCS writes).
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

## Update 2026-11-14 19:55 Bogotá (orchestrator): not started, go
Agent: **Antigravity (project A)**. Nothing has been done on this branch beyond the brief.
- The quake R/C/K selection is in the catalog under `quake_triplets` (tracks 11 and 47) and in `reports/gate.md`. Use those scene names; don't reselect.
- Order still holds: Eje Cafetero first (headline), then Aburrá, then La Mojana. The La Mojana flood agent (grok2) reads GCOV live on track 47 frame 5; don't duplicate its classification, only cache the bands.
- Your worktree was synced onto the latest `origin/main` by the orchestrator. Run `make sync` again before every commit.
- AOIs now live in `config/bailasar.yaml` under `aois:` (`1_aburra`, `2_eje_cafetero_quake`, `3_la_mojana_caregato`). Read them from there with `yaml.safe_load`; don't copy the bboxes into code.
- The gate catalog is `nisar_colombia_granules_2026.json` at the repo root (not under `local_cache/`). `scripts/discover_nisar_colombia.py` is the reference for parsing NISAR names (stream, product, polarization, dates).
- Ruff no longer checks line length (E501 is ignored; the formatter owns it). Don't spend time wrapping lines.
- New README rule (AGENTS.md "README kept current"): `README.md` is not in your file list, so don't edit it. Instead, add a short "README rows" subsection to your Report with the setup/run command and the Status-table row (component · state · issue · report) for the orchestrator to paste.
- Run long jobs (live downloads, GEE exports) in the foreground, or poll them to completion. The CLI ends background work after its wait timeout.

## Report (append to the end of this file when done)
What you built, commands run with their output tail, measured numbers with IDs, what you could not do, open questions.
