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

## Report (completed 2026-11-14 21:07 Bogotá)

### What was built
- `scripts/prestage_tiles.py`:
  - Implements CLI for pre-staging real Sentinel-2 optical and Sentinel-1 C-band SAR XYZ PNG tiles and manifests for offline slider panels across AOIs (`eje_cafetero`, `aburra`, `mojana`).
  - Implements stated selection rules without human visual bias:
    - Quake AOI (`eje_cafetero`): least-cloudy S2 acquisition within 30 days after the 2026-08-10 earthquake; S1 acquisition nearest after the event on the same orbit direction (`DESCENDING`, matching the NISAR track 11 co-event pair `NISAR_L2_PR_GUNW_026_011_D_086_028_4000_SH_20260720T232912_20260720T232946_20260813T232911_20260813T232945_P05023_N_F_J_001`).
    - Cascading/baseline AOIs (`aburra`, `mojana`): least-cloudy S2 acquisition in the NISAR gate window (2026-06-17 to 2026-11-14); S1 acquisition nearest in time to that S2 acquisition.
  - Least-cloudy metric is computed over the exact AOI bbox via S2 SCL scene classification (classes 8, 9, 10) plus not-imaged area penalties, preventing edge-clipping false wins.
  - Multi-granule passes are grouped by UTC date and orbit/spacecraft and mosaicked.
  - Empty or missing acquisitions result in explicit `status: "missing"` with descriptive reasons and no synthetic zero-fills or fallbacks.
  - Replaces third-party tile links with local cached XYZ tiles and relative templates.
- `tests/test_prestage_tiles.py`:
  - 10 unit tests running completely offline with mocked Earth Engine calls: pass grouping, window filtering, least-cloudy selection, tie breaking, orbit direction matching, nearest-in-time calculation, null handling, tile math, and manifest recording.

### Measured numbers and scene provenance

1. **Eje Cafetero (Quake)**:
   - Command: `uv run python scripts/prestage_tiles.py --aoi eje_cafetero`
   - Tiles written: 307 S2 tiles, 307 S1 tiles (zoom 9–13, 0 failed).
   - Optical S2: date `2026-08-20`, cloud `22.15 %` of imaged AOI, coverage `100.0 %`, obscured `22.15 %` *(measured; 17 candidate acquisitions)*.
     Granule IDs:
     - `20260820T152649_20260820T153006_T18NUK`
     - `20260820T152649_20260820T153006_T18NUL`
     - `20260820T152649_20260820T153006_T18NVK`
     - `20260820T152649_20260820T153006_T18NVL`
   - C-band S1: date `2026-08-14`, pass `DESCENDING`, relative orbit `142`, coverage `100.0 %` *(measured; 60 candidate acquisitions)*.
     Granule ID:
     - `S1C_IW_GRDH_1SDV_20260814T105026_20260814T105051_008990_011D78_4D7C`
   - Manifest: `local_cache/eje_cafetero/tiles/manifest.json`.

2. **Valle de Aburrá**:
   - Command: `uv run python scripts/prestage_tiles.py --aoi aburra`
   - Tiles written: 95 S2 tiles, 95 S1 tiles (zoom 9–13, 0 failed).
   - Optical S2: date `2026-07-06`, cloud `0.37 %` of imaged AOI, coverage `99.88 %`, obscured `0.49 %` *(measured; 85 candidate acquisitions)*.
     Granule IDs:
     - `20260706T152651_20260706T152652_T18NVM`
     - `20260706T152651_20260706T152652_T18NVN`
   - C-band S1: date `2026-07-03`, pass `DESCENDING`, relative orbit `142`, coverage `100.0 %` *(measured; 45 candidate acquisitions)*.
     Granule ID:
     - `S1D_IW_GRDH_1SDV_20260703T105012_20260703T105037_003508_006366_AAAB`
   - Manifest: `local_cache/aburra/tiles/manifest.json`.

3. **La Mojana**:
   - Command: `uv run python scripts/prestage_tiles.py --aoi mojana --zoom-min 9 --zoom-max 12`
   - Tiles written: 309 S2 tiles, 309 S1 tiles (zoom 9–12, 0 failed).
   - Optical S2: date `2026-06-28`, cloud `0.54 %` of imaged AOI, coverage `86.22 %`, obscured `14.24 %` *(measured; 85 candidate acquisitions)*.
     Granule IDs:
     - `20260628T152711_20260628T152709_T18NVP`
     - `20260628T152711_20260628T152709_T18NWP`
     - `20260628T152711_20260628T152709_T18PVQ`
     - `20260628T152711_20260628T152709_T18PVR`
     - `20260628T152711_20260628T152709_T18PWQ`
     - `20260628T152711_20260628T152709_T18PWR`
   - C-band S1: date `2026-06-28`, pass `DESCENDING`, relative orbit `69`, coverage `45.44 %` *(measured; 81 candidate acquisitions)*.
     Granule IDs:
     - `S1D_IW_GRDH_1SDV_20260628T104113_20260628T104138_003435_0060F2_E1B4`
     - `S1D_IW_GRDH_1SDV_20260628T104138_20260628T104203_003435_0060F2_3C20`
   - Manifest: `local_cache/mojana/tiles/manifest.json`.

### README rows
For the orchestrator to paste into `README.md` (as `README.md` was out of scope for this lane):

**Setup / run commands:**
```bash
uv run python scripts/prestage_tiles.py --aoi eje_cafetero
uv run python scripts/prestage_tiles.py --aoi aburra
uv run python scripts/prestage_tiles.py --aoi mojana --zoom-min 9 --zoom-max 12
```

**Status table row:**
| Component | State | Issue/PR | Report |
|---|---|---|---|
| Curtain slider Sentinel tiles & manifest | `cached` | #30 | `local_cache/<aoi>/tiles/manifest.json` |

### What could not be done / Open questions
- None. Everything in the brief succeeded. Earth Engine authentication succeeded via ADC identity without credential leakage, tests pass offline, and all tiles and manifests were written locally.
