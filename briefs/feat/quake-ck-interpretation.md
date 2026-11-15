# Brief: feat/quake-ck-interpretation — interpret the now-unsealed quake C/K damage proxy (agent: grok)

- **Goal:** now that the pre-registration is **frozen** (`status: frozen`, hash `36a90fa…`), the co-event (C) and control (K) coherence statistics are **unsealed by rule**. Compute and report the damage-proxy excess **E_C − E_K** for both quake tracks, under the pre-registered method, with every honesty caveat the design and the deviation ledger require. Hazard-modeling lane (LEONOB2014).
- **Issue:** #31 / #32 (quake damage proxy & scorecard interpretation). **Reference:** `gee_math/earthquake_dpm_math.py` (`run_dpm_pass`, `evaluate_units`, the C/K passes), `reports/quake_dpm.md`, `validation/README.md` (deviations 1 and 2, the frozen pairs and `control_K_timing`), `local_cache/quake/dpm_track{11,47}.zarr` (the stored passes).

## Context you must honor
- **Frozen pairs (validation/README.md):** track 47 K is pre-event; **track 11 K is post-event** (`control_K_timing: post_event`) — the design's fallback, because frame 086 had no other pre-event pair. So track 11 is reported as **"radar vs baseline, post-event control only"**; condition 3 of the beats rule cannot be met; expect residual demolition/debris/aftershock change. Never write "radar beats baseline" on either track.
- **Scorecard is uninformative (#24/#25):** no verified barrio damage labels, so there is no precision@k. This task reports the **excess E_C − E_K** (built-up vs non-built coherence-loss contrast, C relative to K), not a validated damage detection. The baseline mismatch (C 24 d vs R/K 12 d) is disclosed beside every number.
- **No synthetic data; the pairs and thresholds are frozen** — read them from `config/preregistered.yaml`, never change them.

## Steps
1. From the stored passes in `local_cache/quake/dpm_track{11,47}.zarr` (or re-run the DPM CLI if needed, foreground), compute per track: the built-up excess E_C and E_K (the measured μ/σ/median-Z-by-class and the excess the modules already produce), and **E_C − E_K**, with the barrio-block bootstrap CI if the scoring helpers are available (`validation/scoring.py` `block_bootstrap`, `built_up_excess`) — read-only use of the merged scoring library; do not modify it.
2. Write `reports/quake_dpm_interpretation.md`: per track, E_C, E_K, E_C − E_K with its CI (or null + reason if the bootstrap is not applicable), unit counts and denominators, the baseline-mismatch disclosure, the track-11 post-event-control caveat, and the explicit statement that the scorecard remains uninformative (unknown ≠ undamaged). Every number *(measured)* with the command + scene IDs.
3. A one-line verdict per track: whether E_C − E_K excludes zero (a coherence-loss contrast consistent with co-event damage), stated as a **proxy contrast, PROVISIONAL**, never a validated damage map.

## Acceptance
- `make ci` green; a hand-written-array test for the E_C − E_K computation if you add a helper (no network).
- `reports/quake_dpm_interpretation.md` has E_C, E_K, E_C − E_K (+ CI or null+reason) for both tracks, with denominators, the mismatch and post-event-control caveats, and the uninformative-scorecard statement.
- No number lacks a source; nothing claims "beats baseline".

## Rules
- Read the frozen `config/preregistered.yaml`; never edit it.
- Files you may touch: `gee_math/earthquake_dpm_math.py` (only if you need a read-only excess helper), `tests/test_earthquake_dpm.py`, `reports/quake_dpm_interpretation.md`, this brief. Writing `local_cache/quake/*` is fine. Do not touch `validation/scoring.py`, `config/`, or other lanes.
- Earth Engine via `init_ee()` if a re-run is needed; foreground; stalled granule → `missing`.
- `make sync` before each commit. Do **not** push, merge, switch branches, reset, stash, open PRs or run `gh`.

## If blocked
Write `BLOCKED: <reason>` and stop.

## Report (append when done)
Per track: E_C, E_K, E_C − E_K (+ CI or reason), denominators, the command and scene IDs, and the PROVISIONAL proxy-contrast verdict with its caveats.

### Done 2026-11-15 04:00 Bogotá (09:00 UTC)

Command: `uv run python /tmp/quake_ck_interpret.py` (644 s). Frozen hash
`36a90fa104382f9217746ef730248ed24e223346`. Stored zarr K was the pre-deviation-2
pair and was not used. Full write-up: `reports/quake_dpm_interpretation.md`.

Baseline mismatch on both tracks: C 24 d vs R/K 12 d. Scorecard stays
uninformative (unknown ≠ undamaged). Barrio-block CI is null: no barrio
polygons were adopted. The intervals below are municipio-block (28 GAUL ADM2
units, 2000 replicates, seed 20261114), the blocks the stored passes actually
have.

- **Track 11** (post-event K, frame 86, 2026-08-25→09-06). Module excess,
  denominators 211,820 built-up / 104,579 non-built valid px (316,399 valid /
  10,353,357): E_C = 0.023600793702112727, E_K = −0.34736395358340544,
  E_C − E_K = 0.37096474728551815. Municipio-block 95% CI for the
  evaluated-unit difference (0.3716128433194328; 211,792 / 104,460 px, 28
  units) is [−0.042198226415787556, 0.8086851739942996] and includes zero.
  Scenes: R `…025_011_D_086_026…20260708…20260720…`, C `…026_011_D_086_028…20260720…20260813…`,
  K `…029_011_D_086_030…20260825…20260906…`. **Verdict:** proxy contrast,
  PROVISIONAL; does not exclude zero; radar vs baseline, post-event control
  only.
- **Track 47** (pre-event K, frame 4, 2026-06-17→06-29). Module excess,
  denominators 211,820 / 104,578 (316,398 / 10,353,357): E_C =
  0.049449170280001765, E_K = −0.09524659058894129, E_C − E_K =
  0.14469576086894306. Municipio-block 95% CI (evaluated-unit difference
  0.14446231216014016; 211,792 / 104,459 px, 28 units) is
  [−0.2738907074230475, 0.49018740038578146] and includes zero. Scenes: R
  `…025_047_A_004_026…20260711…20260723…`, C `…026_047_A_004_028…20260723…20260816…`,
  K `…023_047_A_004_024…20260617…20260629…`. **Verdict:** proxy contrast,
  PROVISIONAL; does not exclude zero; pre-event control; not a validated
  damage map.

README was not edited (outside this brief's file list).
