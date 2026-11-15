# Quake damage-proxy over the Chocó epicenter AOI — measured, PROVISIONAL

**This is additional coverage, not the frozen scorecard.** It runs the pre-registered
damage-proxy method over an operational AOI centred on the M7.4 epicenter
(San José del Palmar, Chocó; USGS `us6000tjl2`), to ask whether NISAR L-band —
which images this optical/C-band-blind region — carries any co-event
coherence-loss signal there. The frozen scorecard AOIs and pairs are unchanged
(`config/preregistered.yaml`, `status: frozen`). Every number below is
*(measured)* with its command, scene IDs and denominator. **The result is a
null: there is no positive co-event coherence-loss excess over control here.**

- **Command:** `uv run python -m gee_math.earthquake_dpm_math --track 11 --aoi -76.70 4.40 -75.95 5.25 --out-dir local_cache/choco_epicenter`
- **Generated (UTC):** 2026-11-15T14:37:08Z
- **Frozen config sha1 read at run time:** `36a90fa104382f9217746ef730248ed24e223346` (`status: frozen`); thresholds `built_up>=0.5`, `non_built<=0.1`, `min_built_up_px=20`.
- **AOI `[W,S,E,N]`:** `[-76.70, 4.40, -75.95, 5.25]` (operational `4_choco_epicenter_quake`, `config/bailasar.yaml`; CLI `--aoi` override). Not a frozen scorecard AOI.
- **Outputs (git-ignored):** `local_cache/choco_epicenter/dpm_track11.zarr` (4691×4168, zarr v3), `local_cache/choco_epicenter/dpm_units_track11.parquet` (29 unit rows, 2 excluded), `local_cache/choco_epicenter/dpm_run.log`.

## Pairs — discovered on track 11 (ASF read-only fallback)

The frozen quake catalog has no pairs over this AOI window, so the module fell
back to an ASF read-only search and discovered the track-11 frame-086 triplet
(the same frame that carries the Aburrá track-11 scorecard pairs), evaluated
here over the Chocó AOI window:

| Role | Granule | Span |
|---|---|---|
| R (pre-event reference) | `NISAR_L2_PR_GUNW_025_011_D_086_026_4000_SH_20260708T232913_20260708T232947_20260720T232912_20260720T232946_P05023_N_F_J_001` | 2026-07-08 → 2026-07-20 (12 d) |
| C (co-event) | `NISAR_L2_PR_GUNW_026_011_D_086_028_4000_SH_20260720T232912_20260720T232946_20260813T232911_20260813T232945_P05023_N_F_J_001` | 2026-07-20 → 2026-08-13 (24 d) |
| K (control) | `NISAR_L2_PR_GUNW_029_011_D_086_030_4000_SH_20260825T232910_20260825T232945_20260906T232910_20260906T232945_P05023_N_F_J_001` | 2026-08-25 → 2026-09-06 (12 d) |

- **Baseline mismatch (disclosed next to every number):** C spans **24 d** while R and K span **12 d** each.
- **K is a POST-EVENT control** (2026-08-25 → 2026-09-06, after the co-event window). As the design and `validation/README.md` record for track 11 (`control_K_timing: post_event`), this is "radar vs baseline, **post-event control only**"; condition 3 of the beats rule cannot be met, and a post-event control can itself carry demolition, debris, aftershock or reconstruction change.

## Measured passes

Units are FAO GAUL 2025 ADM2 municipios (official barrio/vereda polygons pending,
`validation/README.md`): **29 total, 27 evaluated, 2 excluded** (El Cantón del
San Pablo and Tadó, each 0 built-up valid px < 20). The excess within a pass is
`E = median_z(built-up) − median_z(non-built)`.

| Pass | valid px / total | built-up / non-built valid px | μ | σ | median Z built-up | median Z non-built | **E** |
|---|---|---|---:|---:|---:|---:|---:|
| C (co-event) | 68,763 / 19,552,088 | 30,864 / 37,899 | 0.129150 | 0.196600 | −0.282007 | −0.140485 | **E_C = −0.141523** |
| K (control, post-event) | 68,731 / 19,552,088 | 30,835 / 37,896 | −0.004920 | 0.169823 | 0.408135 | −0.013590 | **E_K = +0.421725** |

**E_C − E_K = −0.563247** *(measured)*.

### Municipio-block interval

Per-unit built-up contrast `d_u = median_z_built(C) − median_z_built_control(K)`
over the 27 evaluated municipios, mean and percentile 95% CI from a
municipio-block bootstrap (2000 replicates, seed 20261114, `validation/scoring.py`
`block_bootstrap`; the driver was a scratch file, not committed):

- point evaluated-unit difference = **−0.686117**
- 95% municipio-block CI = **[−0.912049, −0.456434]** — **excludes zero, on the negative side**.

## Verdict (PROVISIONAL proxy contrast — a null, not a signal)

- **There is no positive co-event coherence-loss excess over control at the epicenter AOI.** The contrast is significantly **negative** (E_C − E_K = −0.563; evaluated-unit CI [−0.912, −0.456] excludes zero below it). This does **not** support a co-event damage detection, and it is the **opposite** of "radar beats baseline" — which is not claimed here and cannot be, on a post-event control.
- **Confounds that make even the sign uninterpretable as damage:** K is a post-event control (its built-up change may reflect post-event activity, inflating E_K); the C pair spans 24 d vs 12 d for R/K; the scorecard remains **uninformative** (no verified barrio damage labels — **unknown ≠ undamaged**); units are ADM2 municipios, not barrios.
- **What this run does establish (the real result):** NISAR L-band **covers the optical- and C-band-blind Chocó epicenter** with a clean R/C/K interferometric triplet that processes end-to-end over the epicenter AOI (68,763 valid px in the co-event pass). The epicenter chapter's evidence is **coverage**, demonstrated at the epicenter itself — not a damage map. See `reports/quake_extended_aois.md` and `reports/quake_epicenter_gate.md` for the full epicenter coverage.

_No number here lacks a source; nothing claims "beats baseline"; a null is reported as a null._
