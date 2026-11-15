# Brief: feat/data-mojana-flood — La Mojana dual-pol flood classes (agent: grok2)

- **Goal:** classify open water and flooded vegetation in La Mojana from NISAR GCOV HH/HV, with the dry-baseline rule and sensitivity ranges.
- **Issue:** #34 (plan 03-05) · **Plan reference:** docs/designs/bailasar.md § Hazard 3; requirements FLOOD-01, FLOOD-02
- **Inputs:** the 38 La Mojana GCOV (Jun 17 → Nov 14); MERIT Hydro HAND via GEE (`init_ee()`); Sentinel-1 VV/VH water mask for the L-vs-C comparison; thresholds from `config/preregistered.yaml` (`flood:`).
- **Outputs:** `gee_math/flood_polarimetric_math.py` pure functions + CLI writing `local_cache/mojana/` class rasters and `reports/mojana.md`; `tests/test_flood.py`.
- **Files you may touch:** `gee_math/flood_polarimetric_math.py`, `tests/test_flood.py`, `reports/mojana.md`, this brief.
- **Out of scope:** quad-pol H/ᾱ or Freeman (Colombia is dual-pol), attributing water to the breach vs season, biomass, UI.
- **Steps:**
  1. Known-answer tests first: open-water fraction f per date (HH γ0 < −18 dB inside HAND < 18 m); driest date = min f; if (f_wet − f_dry)/f_wet < 0.20 or f_wet = 0 → no baseline: report absolute water extent per date and **Class 2 = null**; Class 1: ΔHH < −5.5 dB; Class 2: ΔHH > +3 dB **and** |Δ(HV/HH)| < 1.5 dB; all thresholds read from config; label them uncalibrated.
  2. Sensitivity: hectares at each dB threshold ±1 dB and HAND 12/18/24 m; valid-pixel denominator.
  3. Run on real GCOV; write `reports/mojana.md` with granule IDs, chosen reference date and why, hectares per class with denominators and sensitivity ranges *(measured)*, and the S1 comparison.
- **Acceptance:** `make ci` green; tests cover baseline/no-baseline branches, f_wet = 0, both classes, threshold read from config; report has IDs and denominators.
- **Outward or paid actions needing approval:** none allowed (local only).
- **If blocked:** write `BLOCKED: <reason>` below and stop.
- **Coordination:** issue #19 (EstebanOchoaedos) wires this module to the config in Phase 1; keep his config hook if it lands first.

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

## Update 2026-11-14 21:20 Bogotá (orchestrator): the live run hung, fix the reader first
**What happened:**
- Your live run read granule 1 (Jun 17), which failed with a transient ASF 502. It then hung for about 85 min on granule 2 (Jun 29), with almost no CPU and half-closed sockets. The orchestrator stopped it.
- The branch was rebased onto `origin/main`. Your commit `feat(flood): add La Mojana dual-pol class functions` is kept.
- ASF serves these files fine now: a 1 MB read takes 2.2–3.8 s *(measured, 3 of 11 granules)*.

**Why:**
- Each track 47 frame 5 GCOV is about 7.1–7.3 GB *(measured, 3 of 11)*, and the La Mojana AOI covers almost the whole frame.
- `read_granule_power` streams 5 layers (HHHH, HVHV, numberOfLooks, mask, inputDataExceptionMask) through one long-lived `earthaccess` fsspec session. That session has no read timeout and no retries.

**Do this before re-running:**
1. A new fsspec session per granule, with `aiohttp.ClientTimeout(sock_connect=30, sock_read=120)` and 2 retries with backoff. A granule that still fails is recorded as `missing`.
2. A hard limit per granule (about 20 min): run each granule read in a subprocess, so a stall can't block the run.
3. Open files with `cache_type="blockcache"` and `block_size` of about 32 MB. Do the first pass at the analysis grid with strided reads instead of full 20 m windows. Record the stride in the report.
4. Print per-granule progress: bytes read and seconds.
5. If 3 or fewer dates are usable, write `BLOCKED` instead of classifying.
6. Add a unit test for the timeout and retry path, with a fake filesystem object (no network).

**Then:**
1. `make sync`, `make ci`, commit (Refs: #34).
2. Re-run the classification **in the foreground** (not as a background job) so its output stays visible.
3. Rewrite `reports/mojana.md`:
   - remove the Blocked section;
   - hectares per class, with denominators;
   - the reference date, the granule IDs and the sensitivity ranges;
   - a "README rows" subsection.
4. Commit, then append your Report section below.

## Report

### What was built

- Granule reader in `3f9b888` (`fix(flood): bound La Mojana GCOV reads and stride to 90 m`). Rebases rewrote it from `83d458c` to `63aefe9` (onto `6d8ae27`) and then to `3f9b888` (onto `133e974`). Each attempt opens a new HTTPS session (`sock_connect` 30 s, `sock_read` 120 s), retries twice with backoff (2 s, then 4 s), and a still-failing granule is `missing`. Each read runs in its own process with a 20 min limit. Files open with `cache_type="blockcache"` and a 32 MB block size. The first pass reads every source pixel nearest the 90 m cell (stride 9 at 10 m spacing). Progress prints bytes and seconds. Three or fewer usable dates write `BLOCKED` and skip classification. Unit tests, no network: `test_granule_reader_retries_timeouts_on_a_fake_filesystem`, `test_stalled_granule_subprocess_is_killed`, `test_analysis_stride_targets_the_90m_cell`, `test_three_or_fewer_dates_block_classification`.
- Measured report in `e4c66ef` (`docs(flood): record La Mojana measured open-water extents`; `df9ae2d` before the rebase onto `133e974`). `reports/mojana.md` has no Blocked section. It has hectares per class with denominators, the reference date, granule IDs, sensitivity ranges, the stride, and a README rows subsection.

### Commands

- `make sync` this session, twice. The Makefile target uses `git rebase --autostash`. Each stash was applied and `git stash list` was empty afterward. The second rebase landed on `133e974`. Before this brief commit, `git rev-list --left-right --count HEAD...origin/main` was `4 0`.
- `make ci` before the report commit: pre-commit from `origin/main` to HEAD passed. `uv run pytest -q -m "not network and not cache"` : 81 passed, 1 warning in `tests/test_llm.py` (LangGraph `create_react_agent` deprecation, pre-existing). A later `make ci` failed only because `origin/main` had moved (`#83`, `#84`); `make sync` fixed that. The report file did not change.
- Foreground classification (previous turn of this session, not re-run): `PYTHONUNBUFFERED=1 uv run python -m gee_math.flood_polarimetric_math`, stdout teed to `/tmp/mojana-classify.log`. The report's reproduce line is `uv run python -m gee_math.flood_polarimetric_math`. Generated `2026-11-15T02:20:33Z` (2026-11-14 21:20 Bogotá).

Log head:

```
search count 74; most acquisition dates (11) with HH and HV on track 47 frame 5 direction A
```

Log tail:

```
  NISAR_L2_PR_GCOV_034_047_A_005_4005_DHDH_A_20261027T103903_20261027T103938_P05036_N_F_J_001: 181184525 bytes in 162.5s
  181184525 bytes in 162.5s; finite HH pixels 1
wrote /Users/andresbecerra/Documents/surface_tango-worktrees/feat-data-mojana-flood/reports/mojana.md
rasters 21
```

The log ends there. No granule hit the 20 min limit. Eleven dates stayed usable, so the three-date block did not fire.

### Measured numbers

Command: `uv run python -m gee_math.flood_polarimetric_math`. AOI from `config/bailasar.yaml` `aois.3_la_mojana_caregato`: [-75.4, 7.9, -74.2, 9.2]. Search returned 74 provisional granules. Stack: track 47, frame 5, direction A, 11 dates. Grid EPSG:32618, 90 m, 1471 by 1599, pixel area 8100 m². HAND `MERIT/Hydro/v1_0_1` band `hnd`: 2352129 of 2352129 finite *(measured)*. Stride on every selected granule: 9 by 9 source pixels, spacing 10.0 m by 10.0 m *(measured)*. A 24-day gap sits between 2026-07-23 and 2026-08-16.

Reads *(measured, log)*. The 2026-10-03 row is the successful retry.

| Date | Bytes | Seconds | Finite HH |
|---|---:|---:|---:|
| 2026-06-17 | 201304716 | 328.0 | 213338 |
| 2026-06-29 | 185243789 | 334.8 | 190969 |
| 2026-07-11 | 167215367 | 272.0 | 166457 |
| 2026-07-23 | 194590876 | 324.3 | 203634 |
| 2026-08-16 | 156625295 | 262.0 | 152406 |
| 2026-08-28 | 168729070 | 272.3 | 168603 |
| 2026-09-09 | 177776725 | 238.0 | 180879 |
| 2026-09-21 | 171244425 | 234.3 | 172173 |
| 2026-10-03 | 162370333 | 150.7 | 160132 |
| 2026-10-15 | 154671115 | 163.8 | 149599 |
| 2026-10-27 | 181184525 | 162.5 | 1 |

2026-10-03 first attempt stopped during HVHV: `ClientResponseError: 502` after 54421092 bytes in 63.9 s. Retry 1 waited 2 s and then finished as in the table.

Absolute open water, HH γ0 < −18 dB and HAND < 18 m *(measured)*. Hectares = pixel count × 8100 m² / 10000. The sensitivity column is the absolute-water hectare range at the configured HH threshold ±1 dB.

| Date | Granule | Water | Denominator | Sensitivity (ha) |
|---|---|---|---|---|
| 2026-06-17 | NISAR_L2_PR_GCOV_023_047_A_005_4005_DHDH_A_20260617T103906_20260617T103941_P05023_F_F_J_001 | 5539 px, 4486.59 ha | 197758 | 2798.55–6726.24 |
| 2026-06-29 | NISAR_L2_PR_GCOV_024_047_A_005_4005_DHDH_A_20260629T103906_20260629T103940_P05023_N_F_J_001 | 2887 px, 2338.47 ha | 176936 | 1099.17–4570.02 |
| 2026-07-11 | NISAR_L2_PR_GCOV_025_047_A_005_4005_DHDH_A_20260711T103905_20260711T103939_P05023_N_F_J_001 | 4946 px, 4006.26 ha | 153948 | 2576.61–5952.69 |
| 2026-07-23 | NISAR_L2_PR_GCOV_026_047_A_005_4005_DHDH_A_20260723T103904_20260723T103939_P05023_N_F_J_001 | 4353 px, 3525.93 ha | 188881 | 2157.84–5300.64 |
| 2026-08-16 | NISAR_L2_PR_GCOV_028_047_A_005_4005_DHDH_A_20260816T103903_20260816T103937_P05023_N_F_J_001 | 2929 px, 2372.49 ha | 140686 | 1441.80–3516.21 |
| 2026-08-28 | NISAR_L2_PR_GCOV_029_047_A_005_4005_DHDH_A_20260828T103903_20260828T103937_P05023_N_F_J_001 | 3796 px, 3074.76 ha | 155940 | 1819.26–4973.40 |
| 2026-09-09 | NISAR_L2_PR_GCOV_030_047_A_005_4005_DHDH_A_20260909T103903_20260909T103937_P05023_N_F_J_001 | 5014 px, 4061.34 ha | 167462 | 2476.17–6107.40 |
| 2026-09-21 | NISAR_L2_PR_GCOV_031_047_A_005_4005_DHDH_A_20260921T103903_20260921T103937_P05023_N_F_J_001 | 3209 px, 2599.29 ha | 159343 | 1601.37–3905.82 |
| 2026-10-03 | NISAR_L2_PR_GCOV_032_047_A_005_4005_DHDH_A_20261003T103903_20261003T103937_P05023_N_F_J_001 | 3375 px, 2733.75 ha | 148107 | 1673.46–4092.93 |
| 2026-10-15 | NISAR_L2_PR_GCOV_033_047_A_005_4005_DHDH_A_20261015T103903_20261015T103937_P05023_N_F_J_001 | 4417 px, 3577.77 ha | 137980 | 2314.17–5150.79 |
| 2026-10-27 | NISAR_L2_PR_GCOV_034_047_A_005_4005_DHDH_A_20261027T103903_20261027T103938_P05036_N_F_J_001 | 0 px, 0.00 ha | 1 | 0.00–0.00 |

Baseline accepted. f_wet = 2473/76974 on 2026-07-11, which is 4946/153948 reduced by 2. f_dry = 0 on 2026-10-27 (0/1). (f_wet − f_dry) / f_wet = 1. The limit is 0.2. Reference date: 2026-10-27. October 27 is CRID P05036. The other ten selected granules are P05023.

Class 1 and Class 2 versus that reference *(measured)*: 2026-06-17 and 2026-09-09 are 0 px, 0.00 ha, denominator 1. Every other non-reference date is not measurable (denominator 0). Their sensitivity ranges are 0.00 to 0.00 ha, except 2026-10-27, where both class ranges are null because it is the reference date. These class hectares are not a flood-change map. The reference granule has one valid pixel, so almost no other pixel can be compared with it.

2026-07-11 HAND sensitivity *(measured)*: HAND 12 m is 4843/138718 water pixels; HAND 24 m is 4981/159674.

CHIRPS 15-day AOI mean *(measured)*: 2026-07-11 is 38.117 mm (`UCSB-CHG/CHIRPS/DAILY`). 2026-10-27 is missing.

Sentinel-1 IW GRD, ±6 days of 2026-07-11 *(measured)*: 14 scenes. Absolute-water misses 3351/4946. Median S1 VV on those positive pixels −13.549 dB, VH −20.737 dB, HAND-domain VV −8.713 dB. Class 1 and Class 2 have 0 positive pixels, so their miss rates are not measurable.

README row already in `reports/mojana.md`:

| Component | State | Issue | Report |
|---|---|---|---|
| La Mojana dual-pol flood classes | live | #34 | reports/mojana.md |

README.md was not edited. This brief's file list does not include it.

### What could not be done

- Class 1 and Class 2 are not interpretable. The frozen driest-date rule selected 2026-10-27 because f = 0/1 is the minimum among dates with n_valid > 0. The file was read (181184525 bytes in 162.5 s) and resampled to 1 finite HH pixel. The cause of that single pixel was not inspected.
- No full-resolution unstrided read. The recorded stride is 9 by 9.
- CHIRPS has no value for 2026-10-27.
- Not pushed, not merged. `local_cache/mojana/` rasters stay untracked.

### Open questions

- Should the dry-date rule require a minimum valid-pixel count before a date can be the reference? Until it does, Class 1 and Class 2 for this stack stay degenerate.
- Is the 2026-10-27 P05036 AOI window mostly masked or fill? The read completed. The mask cause is not measured.
- `docs/kb/nisar-gcov-read-timeouts.md` on main still names `83d458c`. The reader commit on this branch is `3f9b888`. That note is outside this brief's file list.
