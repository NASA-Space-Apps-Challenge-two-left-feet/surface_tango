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
The per-date L-vs-C table (dates, NISAR open-water px, S1 scene IDs, missed px, miss fraction), the summary miss fraction, the command and IDs, and the caveats.
