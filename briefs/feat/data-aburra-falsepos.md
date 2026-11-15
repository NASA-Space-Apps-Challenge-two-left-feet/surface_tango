# Brief: feat/data-aburra-falsepos — Aburrá stable-pixel false-positive rate (agent: grok)

- **Goal:** strengthen the merged Aburrá null verdict (#109) with the one calibration it is missing: the keep-rule's **empirical false-positive rate on the stable valley-floor pixels**. The sign-flip null is already in `main`; the stable-pixel rate needs a live re-run because the stable mask is not in the cached pair files.
- **Issue:** #33 (follow-up to #109). **Reference:** `reports/aburra.md` (the "Not done" note names exactly this gap), `gee_math/landslide_insar_math.py` (`noise_floor`, `calibrate_keep_rule`, `run_aburra`).
- **Why it matters:** the keep-rule keeps ~25% of hillslope pixels on pure noise. #109 showed the hillslope kept fraction sits **below** the sign-flip null, so the verdict is "no motion above 9.105 mm (17 pairs)". The stable-pixel false-positive rate is the second, independent confirmation: the rule applied to pixels that are known-stable should keep a similar fraction. If stable ≈ hillslope kept fractions, the hillslope signal is noise — confirming the null.

## What to build
1. In `gee_math/landslide_insar_math.py`, during `run_aburra` (live), apply the **same `noise_floor` keep-rule to the stable valley-floor pixels** (the pixels already identified as the tropo/noise sample, slope ≤ `valley_floor_max_slope_deg`, inside the reference component, outside layover/shadow). Compute the kept fraction there per track, with its denominator (number of stable pixels).
2. Write the result into `local_cache/aburra/calibration.json` (extend it) and into `reports/aburra.md`:
   - per track: stable-pixel kept fraction and denominator, next to the existing hillslope kept fraction and the sign-flip null (mean, p95).
   - a one-line verdict: the hillslope kept fraction is consistent with the stable-pixel false-positive rate → the null holds (or, if hillslopes clearly exceed stable, flag it as candidate, PROVISIONAL, never "detected").
3. Keep the headline verdict unchanged unless the evidence changes it; a null stays a valid result.

## Acceptance
- `make ci` green; a known-answer test (hand-written arrays) that the stable-pixel false-positive helper returns the kept fraction / denominator correctly (no network).
- `reports/aburra.md` shows the stable-pixel false-positive rate per track with denominators, beside the hillslope and sign-flip-null numbers, all *(measured, PROVISIONAL)*.
- The live re-run command and its output tail (counts/fractions only) are in your report.

## Rules (AGENTS.md)
- No synthetic or fabricated data; the calibration only re-applies the rule to real stable pixels and reorders/flips real values — never generate pixel values.
- Every number *(measured)* with its denominator; a null is reported.
- Read thresholds from `config/preregistered.yaml` (`landslide.noise_floor`, `landslide.valley_floor_max_slope_deg` if present); don't hardcode.
- Files you may touch: `gee_math/landslide_insar_math.py`, `tests/test_landslide.py`, `reports/aburra.md`, this brief. Nothing else.
- Earth Engine via `gee_math/ee_session.init_ee()`; run the live job in the **foreground**; a stalled granule is recorded `missing` (see `docs/kb/nisar-gcov-read-timeouts.md`).
- `make sync` before each commit; `make ci` before you finish. Commit locally (`Refs: #33`, `Co-Authored-By: grok`). Do **not** push, merge, switch branches, reset, stash, open PRs or run `gh` — the orchestrator does those.

## If blocked
Write `BLOCKED: <reason>` at the end of this file and stop.

## Report (append when done)
What you built, the live command and its output tail (fractions + denominators only), the stable-vs-hillslope-vs-null comparison, and the verdict.
