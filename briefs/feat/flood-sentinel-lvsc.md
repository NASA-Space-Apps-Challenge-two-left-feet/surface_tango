# Brief: feat/flood-sentinel-lvsc — the full La Mojana L-band vs C-band comparison (agent: grok2)

- **Goal:** strengthen the video headline (La Mojana flood, #102) by extending the NISAR L-band vs Sentinel-1 C-band open-water comparison from the single 2026-07-11 date to **every usable date**, quantifying how much open water C-band misses that L-band sees. This is the central "why L-band" evidence of the 30-second story. Hazard-modeling / flood lane (LEONOB2014).
- **Issue:** #34 (follow-up). **Reference:** `gee_math/flood_polarimetric_math.py` (`compare_s1`, `absolute_water_counts`, the stack), `reports/mojana.md` (the existing single-date comparison and the open-water-per-date table), `local_cache/mojana/` (cube, provenance.json with per-date counts and granule IDs).

## Context
- The existing comparison (one date, 2026-07-11) found Sentinel-1 missed 3,351 of 4,946 NISAR open-water pixels *(measured)*. Generalize it across all 10–11 usable NISAR dates.
- Sentinel-1 is `COPERNICUS/S1_GRD` (record actual scene IDs, pass, date bounds per date). NISAR open water is the cached HH mask per date (counts are in `local_cache/mojana/provenance.json`).
- All thresholds are uncalibrated and frozen — read from `config/preregistered.yaml`; never change them. No synthetic data; a date with no matching S1 scene is recorded "no S1 within window", never zero-filled.

## Steps
1. For each NISAR date with open water, find the nearest Sentinel-1 IW GRD scene(s) within ±N days (state N), and compute, on the NISAR-open-water pixels: how many S1 also flags as water (by the stated S1 threshold) and how many it **misses**, with the denominator (NISAR open-water pixel count that date). Foreground.
2. Extend `reports/mojana.md` (a new "L-band vs C-band, all dates" section) or write `reports/mojana_lvsc.md`: a per-date table — date, NISAR open-water px, S1 scene IDs, S1-missed px, miss fraction — all *(measured, PROVISIONAL, uncalibrated)*, with denominators. A summary line: the median/range miss fraction across dates.
3. Keep the honest caveats: uncalibrated thresholds; seasonal + breach water not separated; the change classes remain degenerate (do not re-open that — it is a frozen-rule issue, #26).

## Acceptance
- `make ci` green; a hand-written-array test for the per-date miss-fraction computation (no network).
- The report has the per-date L-vs-C table with denominators and S1 scene IDs, and the summary miss fraction, all measured.
- No number lacks a source; no fabricated or zero-filled dates.

## Rules
- Read the frozen `config/preregistered.yaml`; never edit it. The driest-date/change-class rule is frozen — do not touch it.
- Files you may touch: `gee_math/flood_polarimetric_math.py` (comparison only), `tests/test_flood.py`, `reports/mojana.md` or `reports/mojana_lvsc.md`, this brief. Writing `local_cache/mojana/*` comparison outputs is fine; do **not** touch `provenance.json` or the cube bands other agents depend on.
- Earth Engine via `init_ee()`; foreground; stalled granule → `missing`. Don't `.resample("nearest")`.
- `make sync` before each commit. Do **not** push, merge, switch branches, reset, stash, open PRs or run `gh`.

## If blocked
Write `BLOCKED: <reason>` and stop.

## Report (append when done)

Command: `uv run python -m gee_math.flood_polarimetric_math --lvsc`
Generated (UTC): 2026-11-15T09:12:42Z
Report: `reports/mojana_lvsc.md` (full scene ID, pass, start, end, and relative orbit for every scene). Comparison JSON, gitignored: `local_cache/mojana/lvsc_comparison.json`.
Frozen config sha256 read at run time: `8d61252171e05762856b94a0adca521ae6822e91d948b3deaf1edeb171893ea5`.
Provenance file sha recorded in that report, file not written: generated 2026-11-15T02:20:33Z, config sha256 `c17c0ced08701ba05fb9ad94fd42d6e7882e87ed733d496c0b5b46370b4fcc65`. After the run the provenance file sha256 was `996c1e64b96b1a480b2b1e2a36dbefda3bd860cf6612f89cfdee77b3f52dea6a`.

Method, same construction as the published 2026-07-11 row in `reports/mojana.md`. N = 6 days. For each date the composite is the median of every `COPERNICUS/S1_GRD` IW scene with VV and VH whose `filterDate` window is the NISAR date minus 6 days inclusive through the NISAR date plus 6 days exclusive. The VV cut is the frozen L-band value `flood.open_water_abs_hh_db` = -18.0 dB. It is not an S1 calibration. A miss is a NISAR open-water pixel whose S1 VV is finite and is not below that cut. The denominator is the count of NISAR open-water pixels with finite S1 VV. Sampling is `ee.data.computePixels` onto the cached grid. No `.resample("nearest")`.

All counts below are *(measured, PROVISIONAL, uncalibrated)*. On every measurable date the finite-S1 denominator equals the NISAR open-water count (no missing S1 on open water). Scene IDs are the product names returned by the collection; the full list is in the report.

| Date | NISAR open-water px | S1 scenes | S1 also water | S1 missed | Miss fraction |
|---|---:|---:|---:|---:|---|
| 2026-06-17 | 5539 | 16 | 1953 | 3586 | 3586/5539 |
| 2026-06-29 | 2887 | 18 | 714 | 2173 | 2173/2887 |
| 2026-07-11 | 4946 | 14 | 1595 | 3351 | 3351/4946 |
| 2026-07-23 | 4353 | 14 | 1620 | 2733 | 2733/4353 |
| 2026-08-16 | 2929 | 11 | 1298 | 1631 | 1631/2929 |
| 2026-08-28 | 3796 | 12 | 1366 | 2430 | 2430/3796 |
| 2026-09-09 | 5014 | 14 | 1718 | 3296 | 3296/5014 |
| 2026-09-21 | 3209 | 12 | 1149 | 2060 | 2060/3209 |
| 2026-10-03 | 3375 | 10 | 1484 | 1891 | 1891/3375 |
| 2026-10-15 | 4417 | 12 | 1791 | 2626 | 2626/4417 |
| 2026-10-27 | 0 | not compared | not measurable | not measurable | no NISAR open water (denominator 0) |

2026-07-11 reproduces the published row: 3351 misses out of 4946, from 14 IW GRD scenes *(measured, this command and `reports/mojana.md`)*.

Summary over the 10 measurable dates. Sorted by fraction, then date: 2026-08-16 1631/2929, 2026-10-03 1891/3375, 2026-10-15 2626/4417, 2026-07-23 2733/4353, 2026-08-28 2430/3796, 2026-09-21 2060/3209, 2026-06-17 3586/5539, 2026-09-09 3296/5014, 2026-07-11 3351/4946, 2026-06-29 2173/2887. The count is even, so the median is the mean of the two central fractions: (2430/3796 + 2060/3209) / 2 = 7808815/12181364 (0.641046) *(measured, PROVISIONAL, uncalibrated)*. Range: minimum 1631/2929 on 2026-08-16; maximum 2173/2887 on 2026-06-29. 2026-10-27 is not in the median. It has 0 open-water pixels and 1 valid pixel. It is not a zero miss.

NISAR granules, one per date, from `provenance.json` (read only):

- 2026-06-17: `NISAR_L2_PR_GCOV_023_047_A_005_4005_DHDH_A_20260617T103906_20260617T103941_P05023_F_F_J_001`
- 2026-06-29: `NISAR_L2_PR_GCOV_024_047_A_005_4005_DHDH_A_20260629T103906_20260629T103940_P05023_N_F_J_001`
- 2026-07-11: `NISAR_L2_PR_GCOV_025_047_A_005_4005_DHDH_A_20260711T103905_20260711T103939_P05023_N_F_J_001`
- 2026-07-23: `NISAR_L2_PR_GCOV_026_047_A_005_4005_DHDH_A_20260723T103904_20260723T103939_P05023_N_F_J_001`
- 2026-08-16: `NISAR_L2_PR_GCOV_028_047_A_005_4005_DHDH_A_20260816T103903_20260816T103937_P05023_N_F_J_001`
- 2026-08-28: `NISAR_L2_PR_GCOV_029_047_A_005_4005_DHDH_A_20260828T103903_20260828T103937_P05023_N_F_J_001`
- 2026-09-09: `NISAR_L2_PR_GCOV_030_047_A_005_4005_DHDH_A_20260909T103903_20260909T103937_P05023_N_F_J_001`
- 2026-09-21: `NISAR_L2_PR_GCOV_031_047_A_005_4005_DHDH_A_20260921T103903_20260921T103937_P05023_N_F_J_001`
- 2026-10-03: `NISAR_L2_PR_GCOV_032_047_A_005_4005_DHDH_A_20261003T103903_20261003T103937_P05023_N_F_J_001`
- 2026-10-15: `NISAR_L2_PR_GCOV_033_047_A_005_4005_DHDH_A_20261015T103903_20261015T103937_P05023_N_F_J_001`
- 2026-10-27: `NISAR_L2_PR_GCOV_034_047_A_005_4005_DHDH_A_20261027T103903_20261027T103938_P05036_N_F_J_001`

Caveats. Thresholds are uncalibrated and were not edited. Seasonal water and Caregato breach water are not separated. Change classes were not recomputed; they stay degenerate under the frozen reference-date rule (issue #26). No date was zero-filled. A date with no IW scene would have been recorded `no S1 within window`; none of these dates was that case. `provenance.json` and the cube bands were not written. On 2026-08-28 the collection returned two pairs of scene IDs that share a start and an end. Both IDs stayed in the median: `S1D_IW_GRDH_1SDV_20260901T231413_20260901T231442_004391_0081E7_6E7B` and `S1D_IW_GRDH_1SDV_20260901T231413_20260901T231442_004391_0081E7_B95A` (2026-09-01T23:14:13Z to 2026-09-01T23:14:42Z); `S1D_IW_GRDH_1SDV_20260901T231442_20260901T231507_004391_0081E7_6B12` and `S1D_IW_GRDH_1SDV_20260901T231442_20260901T231507_004391_0081E7_98E2` (2026-09-01T23:14:42Z to 2026-09-01T23:15:07Z). That can give one acquisition two votes in the median. The scenes were not dropped and the date was not recomputed.

`make ci` after `make sync` onto `7a1dde7`: the pre-commit range `origin/main..HEAD` passed. Offline tests: 429 passed, 3 failed. The failures are `tests/test_web_pitch.py` (`test_facts_keep_their_report_line_and_source`, `test_story_evidence_holds_placeholders_not_numbers`, `test_storyboard_shots_cover_thirty_seconds_and_map_to_cards`). `video/report_facts.py` looks for verdict rows that start with `| Track `. `reports/aburra.md` on this trunk, from `1906fde` (#155), has a `| Stack |` verdict table instead. This branch does not change `reports/aburra.md`, `video/report_facts.py`, or `tests/test_web_pitch.py`. The flood tests in that same run passed.
