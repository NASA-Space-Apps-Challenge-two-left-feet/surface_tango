# Quake C/K interpretation — E_C − E_K (tracks 11 and 47)

Measured 2026-11-15 04:00 Bogotá (2026-11-15T09:00:24Z), after the pre-registration
freeze. Every number below is **(measured)** from the command in this file, or
**(config)** from `config/preregistered.yaml` (read only; hash
`36a90fa104382f9217746ef730248ed24e223346`, `status: frozen`). The products are
**PROVISIONAL** (CRID P05023).

This is a coherence-loss **proxy contrast**. It is not a validated damage map.
**The scorecard stays uninformative** (no verified barrio damage labels, so
there is no precision@k). Unknown is not undamaged (unknown ≠ undamaged).

## Command

```
uv run python /tmp/quake_ck_interpret.py
```

Foreground, worktree `feat/quake-ck-interpretation`, wall time 644 s *(measured,
process elapsed)*. Full-precision JSON:
`local_cache/quake/ck_interpretation.json` (gitignored). The script copy is
`local_cache/quake/ck_interpret.py`.

What the command did:

- Read the frozen pairs, thresholds and bootstrap settings through
  `src/bailasar/config.py` `load_config()`. The loader hash equals
  `git hash-object config/preregistered.yaml`.
- Recomputed the co-event pass with `run_dpm_pass(γ_R, γ_C, …)` on the stored
  `local_cache/quake/dpm_track{11,47}.zarr` arrays (`coh_R`, `coh_C`,
  footprint coverage, WorldCover, the C-pair GUNW mask, `unit_id`). Stored R
  and C granule IDs match the frozen file. Recomputed `excess_e` matched the
  zarr `summary_C` exactly on both tracks.
- Did **not** use the K pair stored in those zarr files. That K is the
  pre-deviation-2 pair (it shares a date with R). Deviation 2 discards it.
- Streamed the frozen K granule with `load_gunw_window` (Earthdata, AOI window
  only, 20 m) and ran the identical control pass `run_dpm_pass(γ_K, γ_R, …)`.
- `E_C − E_K` is `adjusted_excess` in `gee_math/earthquake_dpm_math.py`.

**Baseline mismatch (config, beside every number below):** C spans 24 d; R and
K span 12 d. The Aug 1 / Aug 4 acquisitions are missing. The built-up vs
non-built excess is a relative contrast, which partly absorbs the extra
temporal decorrelation. It does not remove it.

## Method (config + the DPM code)

- Co-event: Δγ = γ_R − γ_C. Control: Δγ = γ_K − γ_R (K in the role of R, R in
  the role of C). Same masks, same standardization.
- μ and σ are the mean and population SD (ddof=0) of Δγ on valid non-built
  pixels. Z = (Δγ − μ) / σ. E = median Z(valid built-up) − median Z(valid
  non-built).
- Built-up is footprint coverage ≥ 0.50. Non-built is coverage ≤ 0.10. A unit
  is evaluated at ≥ 20 valid built-up pixels. Layover/shadow is **missing**
  (the GUNW mask is water and subswath validity only).
- Window: 4143 × 2499 px = 10,353,357 px, EPSG:32618, origin (405690, 569250) m,
  20 m posting. The frozen K window matched that grid on both tracks
  (0 coherence samples outside [0, 1]).
- Units in the cache are municipios (`FAO/GAUL/2025/level2`), not barrios.
  `validation/README.md` records that no barrio polygon set was adopted.

## Intervals

`quake.bootstrap` **(config)** asks for a barrio block, 2000 replicates, seed
`20261114`. **The barrio-block CI is null.** Reason: the frozen unit is
`barrio`, and no barrio polygons were adopted, so there is no barrio block to
draw.

The interval reported below is the same helpers (`validation/scoring.py`
`built_up_excess` and `block_bootstrap`, 2000 replicates, seed 20261114, 95%
percentile, one draw for E_C, E_K and the difference together) on the **28
C-pass evaluated municipios**. It is a municipio-block interval for this proxy.
It is not a barrio interval, and it is not a damage-label interval.

The bootstrap estimand drops pixels in the 4 excluded municipios (28 valid
built-up pixels and 119 valid non-built pixels). The module excess below keeps
those pixels. The two point estimates differ in the fourth decimal.

## Track 11 — descending, frame 86 — post-event control

**Verdict:** proxy contrast, **PROVISIONAL**. E_C − E_K does **not** exclude
zero: the municipio-block 95% CI is [−0.042198226415787556,
0.8086851739942996] and includes zero. Report this track as **radar vs
baseline, post-event control only**. The third condition of the claim rule
cannot be met. Not a validated damage map. The scorecard stays uninformative
(unknown ≠ undamaged).

**Baseline mismatch:** C 24 d vs R 12 d and K 12 d.

K is post-event **(config, `control_K_timing: post_event`)**: 2026-08-25 →
2026-09-06, after the 2026-08-10 event and after R. The control formula is
still Δγ = γ_K − γ_R, so this difference is later-pair coherence minus
earlier-pair coherence, not a pre-event loss. Residual demolition, debris
removal and aftershock change are expected.

| Role | Granule | Dates | Baseline |
|---|---|---|---|
| R | `NISAR_L2_PR_GUNW_025_011_D_086_026_4000_SH_20260708T232913_20260708T232947_20260720T232912_20260720T232946_P05023_N_F_J_001` | 2026-07-08 → 07-20 | 12 d |
| C | `NISAR_L2_PR_GUNW_026_011_D_086_028_4000_SH_20260720T232912_20260720T232946_20260813T232911_20260813T232945_P05023_N_F_J_001` | 2026-07-20 → 08-13 | 24 d |
| K | `NISAR_L2_PR_GUNW_029_011_D_086_030_4000_SH_20260825T232910_20260825T232945_20260906T232910_20260906T232945_P05023_N_F_J_001` | 2026-08-25 → 09-06 | 12 d |

Discarded stored K (not used):
`NISAR_L2_PR_GUNW_024_011_D_086_025_4000_SH_20260626T232913_20260626T232948_20260708T232913_20260708T232947_P05023_N_F_J_001`.

K read *(measured)*: reference time 2026-08-25T23:29:10Z, secondary
2026-09-06T23:29:10Z, frame 86, descending, grid match true.

| Quantity | C (co-event) | K (post-event control) |
|---|---|---|
| μ of Δγ on non-built | 0.05542755259975544 | 0.12733539015661768 |
| σ (population) | 0.13198575342851507 | 0.21024219829185478 |
| reference pixels (denominator of μ, σ) | 104,579 | 104,579 |
| median Z built-up | −0.004830991233112686 | −0.4770495765616436 |
| median Z non-built | −0.028431784935225413 | −0.12968562297823816 |
| valid pixels | 316,399 / 10,353,357 | 316,399 / 10,353,357 |
| valid built-up pixels (denominator of the built-up median) | 211,820 | 211,820 |
| valid non-built pixels (denominator of the non-built median) | 104,579 | 104,579 |
| units evaluated / total | 28 / 32 | 28 / 32 |
| E (module, all valid pixels) | **0.023600793702112727** | **−0.34736395358340544** |

**E_C − E_K (module) = 0.37096474728551815** *(measured)*. Denominators are the
pixel counts in the table. Baseline mismatch: C 24 d vs R/K 12 d.

Evaluated-municipio estimand (the one the interval resamples): E_C =
0.02338944533283596 (211,792 built-up / 104,460 non-built), E_K =
−0.34822339798659685 (211,792 / 104,460), **E_C − E_K = 0.3716128433194328**.
28 blocks. Bootstrap draw time 263 s *(measured)*.

| Estimand | 95% municipio-block CI | Includes 0? |
|---|---|---|
| E_C | [−0.06690698058757691, 0.08814959728060137] | yes |
| E_K | [−0.7592794555131437, 0.002782382151069027] | yes |
| E_C − E_K | [−0.042198226415787556, 0.8086851739942996] | yes |

Barrio-block CI: **null** (no adopted barrio polygons).

The positive point estimate is mostly −E_K. E_K is negative and large; E_C is
about 0.024 and its own interval includes zero. A negative control excess on a
post-event K is not a clean pre-event contrast.

Excluded municipios, both passes, same built-up counts *(measured)*: Belen De
Umbria 10 px, La Virginia 14, Caicedonia 0, Cartago 4. All are under the
20-pixel rule. Names are the stored parquet `unit_name` for those `unit_id`s
(21, 22, 29, 31).

## Track 47 — ascending, frame 4 — pre-event control

**Verdict:** proxy contrast, **PROVISIONAL**. E_C − E_K does **not** exclude
zero: the municipio-block 95% CI is [−0.2738907074230475, 0.49018740038578146]
and includes zero. The control is pre-event (2026-06-17 → 06-29, no date shared
with R or C). Not a validated damage map. The scorecard stays uninformative
(unknown ≠ undamaged).

**Baseline mismatch:** C 24 d vs R 12 d and K 12 d.

| Role | Granule | Dates | Baseline |
|---|---|---|---|
| R | `NISAR_L2_PR_GUNW_025_047_A_004_026_4000_SH_20260711T103831_20260711T103906_20260723T103830_20260723T103905_P05023_N_F_J_001` | 2026-07-11 → 07-23 | 12 d |
| C | `NISAR_L2_PR_GUNW_026_047_A_004_028_4000_SH_20260723T103830_20260723T103905_20260816T103829_20260816T103904_P05023_N_F_J_001` | 2026-07-23 → 08-16 | 24 d |
| K | `NISAR_L2_PR_GUNW_023_047_A_004_024_4000_SH_20260617T103836_20260617T103907_20260629T103831_20260629T103907_P05023_N_F_J_001` | 2026-06-17 → 06-29 | 12 d |

Discarded stored K (not used):
`NISAR_L2_PR_GUNW_024_047_A_004_025_4000_SH_20260629T103831_20260629T103907_20260711T103831_20260711T103906_P05023_N_F_J_001`.

K read *(measured)*: reference time 2026-06-17T10:38:36Z, secondary
2026-06-29T10:38:31Z, frame 4, ascending, grid match true.

| Quantity | C (co-event) | K (pre-event control) |
|---|---|---|
| μ of Δγ on non-built | 0.05310495780907121 | 0.06270885303311313 |
| σ (population) | 0.129474730943598 | 0.16241908413892348 |
| reference pixels (denominator of μ, σ) | 104,578 | 104,578 |
| median Z built-up | 0.005926250291631346 | −0.13815357936590836 |
| median Z non-built | −0.04352291998837042 | −0.04290698877696707 |
| valid pixels | 316,398 / 10,353,357 | 316,398 / 10,353,357 |
| valid built-up pixels | 211,820 | 211,820 |
| valid non-built pixels | 104,578 | 104,578 |
| units evaluated / total | 28 / 32 | 28 / 32 |
| E (module, all valid pixels) | **0.049449170280001765** | **−0.09524659058894129** |

**E_C − E_K (module) = 0.14469576086894306** *(measured)*. Baseline mismatch:
C 24 d vs R/K 12 d.

Evaluated-municipio estimand: E_C = 0.04941590946104785 (211,792 built-up /
104,459 non-built), E_K = −0.0950464026990923 (211,792 / 104,459), **E_C − E_K
= 0.14446231216014016**. 28 blocks. Bootstrap draw time 262 s *(measured)*.

| Estimand | 95% municipio-block CI | Includes 0? |
|---|---|---|
| E_C | [−0.09003777348001929, 0.1463689150655679] | yes |
| E_K | [−0.35387453202139146, 0.20017264639440094] | yes |
| E_C − E_K | [−0.2738907074230475, 0.49018740038578146] | yes |

Barrio-block CI: **null** (no adopted barrio polygons).

The one-pixel gap versus track 11 is in the non-built valid set (104,578 vs
104,579), the same gap already recorded for the co-event pass in
`reports/quake_dpm.md`. Excluded municipios match track 11: Belen De Umbria
10, La Virginia 14, Caicedonia 0, Cartago 4.

## What this does not say

- No directional claim is made on either track. Both municipio-block intervals
  for E_C − E_K include zero. Track 11 could not support that claim anyway:
  its control is post-event.
- The scorecard stays uninformative. There is no precision@k, because there
  are no verified barrio damage labels (`reports/ground_truth.md`,
  `validation/README.md`). The 28 evaluated municipios are a pixel-count
  filter, not damage labels. Unknown ≠ undamaged.
- Deviation 1 (`validation/README.md`): C-pass statistics were seen on
  2026-11-14, before this file existed, while the pre-registration was still
  draft. This report is the post-freeze record of those co-event passes plus
  the replacement K.
- Deviation 2: the frozen K pairs replaced the pairs that shared a date with
  R. Old-K statistics are not in the numbers above.

## README

Not edited. The brief's file list does not include it. A status-table row for
this interpretation belongs in the orchestrator's README pass.
