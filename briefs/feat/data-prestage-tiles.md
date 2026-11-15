# Brief: feat/data-prestage-tiles — real Sentinel-1/2 tiles and GEE stats for offline demo (agent: opencode GLM-5.3)

- **Goal:** pre-stage the optical and C-band panels of the curtain slider from real Sentinel scenes, chosen by a stated rule, so `make pitch` works offline.
- **Issue:** #30 (plan 03-01, part DATA-02) · **Plan reference:** docs/designs/bailasar.md § Frontend curtain slider; requirement DATA-02
- **Inputs:** `init_ee()`; collections `COPERNICUS/S2_SR_HARMONIZED`, `COPERNICUS/S1_GRD`; AOI bboxes above; event date 2026-08-10.
- **Outputs:** `scripts/prestage_tiles.py --aoi {aburra,eje_cafetero,mojana}` that writes XYZ PNG tiles (zoom range set in arguments) under `local_cache/<aoi>/tiles/{s2,s1}/` and `local_cache/<aoi>/tiles/manifest.json` (scene IDs, dates, cloud %, selection rule); `tests/test_prestage_tiles.py`.
- **Files you may touch:** `scripts/prestage_tiles.py`, `tests/test_prestage_tiles.py`, this brief.
- **Out of scope:** NISAR bands (feat/data-cache-builder), the frontend, GCS uploads.
- **Steps:**
  1. Scene rule, stated in the manifest: for the quake, the **least-cloudy S2 scene within 30 days after 2026-08-10**, and the S1 scene nearest after the event on the same orbit direction; for Aburrá/La Mojana, the least-cloudy S2 and nearest S1 in the NISAR window. **Never** pick a cloudy scene on purpose; the panel shows whatever the rule returns.
  2. Replace the Google basemap (`mt1.google.com`) used as "optical_s2" in the generated manifest: it is not Sentinel-2.
  3. Tests with mocked EE responses (no network): rule picks min cloud within the window; manifest records IDs and the rule text; empty collection → "missing", no fallback.
- **Acceptance:** `make ci` green; a run for `--aoi eje_cafetero` prints scene IDs, dates and cloud % *(measured)* and writes tiles + manifest.
- **Outward or paid actions needing approval:** none (local only).
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

## Update 2026-11-14 19:55 Bogotá (orchestrator): reassigned, go
Agent: **Antigravity (project B)** (was opencode GLM-5.3, which is busy on the quake DPM brief). Nothing has been done on this branch beyond the brief.
- Earth Engine: use `gee_math/ee_session.init_ee()` (ADC identity, `GCP_PROJECT_ID` from `.env`). Never print credentials.
- Start with `--aoi eje_cafetero` (the headline), then Aburrá, then La Mojana. The frontend (SaritaRpo, #37) shows "not cached" until your manifest lands, so the manifest schema (scene ID, date, cloud %, rule text, `missing`) matters more than zoom depth: keep zoom modest (for example 9–13) and record the range.
- Your worktree was synced onto the latest `origin/main` by the orchestrator. Run `make sync` again before every commit.
- AOIs now live in `config/bailasar.yaml` under `aois:` (`1_aburra`, `2_eje_cafetero_quake`, `3_la_mojana_caregato`). Read them from there with `yaml.safe_load`; don't copy the bboxes into code.
- The gate catalog is `nisar_colombia_granules_2026.json` at the repo root (not under `local_cache/`). `scripts/discover_nisar_colombia.py` is the reference for parsing NISAR names (stream, product, polarization, dates).
- Ruff no longer checks line length (E501 is ignored; the formatter owns it). Don't spend time wrapping lines.
- New README rule (AGENTS.md "README kept current"): `README.md` is not in your file list, so don't edit it. Instead, add a short "README rows" subsection to your Report with the setup/run command and the Status-table row (component · state · issue · report) for the orchestrator to paste.
- Run long jobs (live downloads, GEE exports) in the foreground, or poll them to completion. The CLI ends background work after its wait timeout.

## Report (append to the end of this file when done)
What you built, commands run with their output tail, measured numbers with IDs, what you could not do, open questions.
