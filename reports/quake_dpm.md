# Quake damage proxy map (DPM) — tracks 11 and 47 (#31, plan 03-02)

Run offline-on-main-trunk agent: opencode GLM-5.3, branch `feat/quake-dpm-v2`,
Nov 14–15 2026 (times Bogotá UTC−5). Every number below is **(measured)** from
the two listed commands, or **(config)** from `config/preregistered.yaml` /
`config/bailasar.yaml`. **No C/K-pass statistic (μ, σ, median Z, excess E,
per-unit DPM, quantiles) appears in this report: C/K statistics are sealed
until the pre-registration freeze (status=draft).**

## Commands

| Track | Command |
|---|---|
| 11 | `uv run python -m gee_math.earthquake_dpm_math --track 11` |
| 47 | `uv run python -m gee_math.earthquake_dpm_math --track 47` |

Both ran in the foreground on 2026-11-14/15 with the network read paths
(ASF search, Earthdata windowed HDF5 reads, Earth Engine tiles) and the
shared loader for all parameters.

## Pairs (hour-2 gate catalog, verified against ASF discovery)

Pairs come from `nisar_colombia_granules_2026.json` → `quake_triplets` (the
gate's frozen choice); each run re-ran the read-only ASF discovery as a
cross-check and both runs printed *verified: ASF discovery returns the same
triplet (measured, read-only)*. Baseline days are **disclosed metadata**, not
sealed statistics.

| Track | Role | Granule ID | Dates | Baseline |
|---|---|---|---|---|
| 11 | R | `NISAR_L2_PR_GUNW_025_011_D_086_026_4000_SH_20260708T232913_20260720T232912_P05023_N_F_J_001` | 2026-07-08 → 07-20 | 12 d |
| 11 | C | `NISAR_L2_PR_GUNW_026_011_D_086_028_4000_SH_20260720T232912_20260813T232911_P05023_N_F_J_001` | 2026-07-20 → 08-13 | 24 d |
| 11 | K | `NISAR_L2_PR_GUNW_024_011_D_086_025_4000_SH_20260626T232913_20260708T232913_P05023_N_F_J_001` | 2026-06-26 → 07-08 | 12 d |
| 47 | R | `NISAR_L2_PR_GUNW_025_047_A_004_026_4000_SH_20260711T103831_20260723T103830_P05023_N_F_J_001` | 2026-07-11 → 07-23 | 12 d |
| 47 | C | `NISAR_L2_PR_GUNW_026_047_A_004_028_4000_SH_20260723T103830_20260816T103829_P05023_N_F_J_001` | 2026-07-23 → 08-16 | 24 d |
| 47 | K | `NISAR_L2_PR_GUNW_024_047_A_004_025_4000_SH_20260629T103831_20260711T103831_P05023_N_F_J_001` | 2026-06-29 → 07-11 | 12 d |

- **Baseline mismatch (disclosed, gate decision):** C spans 24 d while R and K
  span 12 d on both tracks (the Aug 1 / Aug 4 acquisitions are missing). The
  built-up vs non-built excess is relative, which partly absorbs the extra
  decorrelation; the mismatch rides along in provenance and in every consumer.
- **K frame (measured):** track 47 K is frame 4, the same frame as its R and C
  (4/4/4); track 11 is frame 86 for all three pairs (86/86/86). No K arrived
  from a different frame.
- All granules are provisional (`PR`, CRID P05023).

## Grid and pixel counts (measured)

Window: **4143 × 2499 px = 10,353,357 px** at 20 m posting, EPSG:32618, for
both tracks (each GUNW grid clipped to the same AOI bbox). Coverage and masks:
footprint coverage measured on 10,353,357/10,353,357 px (0 missing tiles
across 45 GEE tiles; input-layer maximum coverage fraction 1.000); coherence
outside [0,1]: 0 px → NaN on all six granule reads; coh pixels converted to
NaN stay NaN.

| Count (px) | Track 11 | Track 47 |
|---|---|---|
| window total | 10,353,357 | 10,353,357 |
| valid | **316,399** | 316,398 |
| valid built-up | 211,820 | 211,820 |
| valid non-built (reference) | 104,579 | 104,578 |

The 1-px difference between tracks sits in Pereira's non-built set
(24,789 px on track 11 vs 24,788 on track 47) — one pixel's validity differs
between the two tracks' GUNW masks/coherence. Disclosed, not smoothed away.

**Track 11 vs #64 (acceptance check): (measured) identical** — 32 units, 28
evaluated, 4 excluded; valid 316,399 of 10,353,357 px; same four excluded
units with the same built-up pixel counts (10/14/0/4). The rerun under the new
code (shared loader, catalog pairs, pyarrow) reproduces the merged pipeline.

WorldCover classes in the window (px, measured, same window both tracks):
tree cover 10: 6,376,110; 20: 2,195; 30: 3,600,947; 40: 41,527; 50: 267,752;
60: 48,667; water 80: 16,159. The layover/shadow mask is **missing** (the NISAR
GUNW has no such layer, JPL D-102272 Rev E p.44; recorded `missing`, never
invented).

## Units (measured counts; no DPM values)

Source (both tracks): GEE asset `FAO/GAUL/2025/level2`, name property
`GAUL2_NAME` (municipio; the labeled GAUL ADM2 fallback — barrio/vereda
polygons are pending per `validation/README.md`), EPSG:4326 source CRS,
rasterized at 20 m pixel centers onto the DPM grid. Exclusion rule **(config)**:
`quake.min_built_up_pixels_per_unit = 20` valid built-up pixels.

**32 units total; 28 evaluated; 4 excluded** (same set on both tracks).
Exclusions: Belen de Umbria 10 built-up px; La Virginia 14; Caicedonia 0;
Cartago 4 — all `< 20` valid built-up pixels, counted and carried in the
parquet with `evaluated = 0`.

| Unit (GAUL2_NAME) | built-up px t11 | built-up px t47 | non-built px t11 | non-built px t47 | evaluated |
|---|---|---|---|---|---|
| Anserma | 153 | 153 | 293 | 293 | yes |
| Belalcazar | 812 | 812 | 168 | 168 | yes |
| Manizales | 38,752 | 38,752 | 12,680 | 12,680 | yes |
| Palestina | 2,135 | 2,135 | 739 | 739 | yes |
| Neira | 177 | 177 | 57 | 57 | yes |
| Risaralda | 353 | 353 | 188 | 188 | yes |
| San Jose | 253 | 253 | 130 | 130 | yes |
| Villamaria | 6,594 | 6,594 | 3,553 | 3,553 | yes |
| Viterbo | 32 | 32 | 393 | 393 | yes |
| Chinchina | 5,196 | 5,196 | 1,622 | 1,622 | yes |
| Filandia | 1,869 | 1,869 | 971 | 971 | yes |
| Buenavista | 37 | 37 | 2 | 2 | yes |
| Calarca | 8,942 | 8,942 | 3,699 | 3,699 | yes |
| Armenia | 35,046 | 35,046 | 7,969 | 7,969 | yes |
| La Tebaida | 3,616 | 3,616 | 1,699 | 1,699 | yes |
| Montenegro | 4,321 | 4,321 | 1,430 | 1,430 | yes |
| Quimbaya | 3,800 | 3,800 | 924 | 924 | yes |
| Salento | 1,865 | 1,865 | 5,993 | 5,993 | yes |
| Circasia | 4,262 | 4,262 | 1,696 | 1,696 | yes |
| Cordoba | 52 | 52 | 107 | 107 | yes |
| Belen De Umbria | 10 | 10 | 37 | 37 | **no** (< 20 px) |
| La Virginia | 14 | 14 | 50 | 50 | **no** (< 20 px) |
| Marsella | 1,657 | 1,657 | 270 | 270 | yes |
| Pereira | 54,169 | 54,169 | 24,789 | 24,788 | yes |
| Santa Rosa De Cabal | 9,675 | 9,675 | 24,805 | 24,805 | yes |
| Dosquebradas | 24,239 | 24,239 | 5,302 | 5,302 | yes |
| Cajamarca | 1,494 | 1,494 | 2,473 | 2,473 | yes |
| Ibague | 28 | 28 | 1,960 | 1,960 | yes |
| Caicedonia | 0 | 0 | 23 | 23 | **no** (< 20 px) |
| Alcala | 1,541 | 1,541 | 393 | 393 | yes |
| Cartago | 4 | 4 | 9 | 9 | **no** (< 20 px) |
| Ulloa | 722 | 722 | 155 | 155 | yes |

## Outputs (local_cache/quake/, git-ignored; sizes `du -sh`, measured)

| Output | Size | Content |
|---|---|---|
| `dpm_track11.zarr` | 291 MB | zarr v3, 4143×2499: coh R/C/K, Δγ, Z, DPM, coverage, landcover, GUNW mask, class masks, unit_id; provenance attrs (incl. sealed summary attrs) |
| `dpm_units_track11.parquet` | 8.0 KB | pyarrow; 32 rows |
| `dpm_track47.zarr` | 293 MB | same layout, track 47 triplet |
| `dpm_units_track47.parquet` | 8.0 KB | pyarrow; 32 rows |

**C/K statistics sealed until pre-registration freeze (status=draft).** The
per-unit DPM values (`median_z_built`, `median_z_built_control`) live only in
the parquet and zarr above; nothing in this report, the UI, the README or any
commit interprets them. The seal lifts only when the loader reports
`is_frozen` (validation/README.md records the hash).

## How #32 (scoring) consumes this

- **Unit parquet per track:** `local_cache/quake/dpm_units_track{11,47}.parquet`
  (pyarrow, one row group, all columns REQUIRED). Columns: `unit_id` (int64,
  1..32, in source-feature order — the stable GAUL feature index, unique),
  `unit_name` (utf8), `unit_type` (utf8), `unit_source` (utf8, `asset:…` or
  `file:<path>`), `evaluated` (int64 1/0), `n_built_up_valid_px` (int64),
  `n_non_built_valid_px` (int64), `median_z_built` and `median_z_built_control`
  (double, NaN = excluded/undefined). NaN is a value, never null.
- **Eligibility:** select `evaluated = 1` (28 per track), count the excluded 4,
  and mask invalid pixels before calling `validation/scoring.py` (which takes
  only pre-registered values + named observations).
- **k comes from `config/preregistered.yaml` via
  `cfg.prereg("quake.k_rule")` (config: fraction 0.10, minimum 5).** With the
  measured 28 evaluated units: 0.10 × 28 = 2.8 → 3 after round-up, the minimum
  5 applies, so **k = 5 (computed from config + the measured denominator)** per
  the rounding/minimum/cap conventions in `validation/ALLOWLIST.md`.
- The baseline mismatch (C 24 d vs R/K 12 d) must be disclosed next to any
  scorecard number that consumes this (gate decision table, `reports/gate.md`).

## README rows (for the orchestrator)

| Component | State | Issue/PR | Report |
|---|---|---|---|
| Quake DPM, track 11 (R/C/K GUNW coherence loss, municipios) | live (read-only ASF/GEE; outputs cached) | #31 / this branch | `reports/quake_dpm.md` |
| Quake DPM, track 47 (same pipeline, ascending frame 4) | live (read-only ASF/GEE; outputs cached) | #31 / this branch | `reports/quake_dpm.md` |
| Quake unit parquet (pyarrow, per-track, sealed medians until freeze) | cached (`local_cache/quake/dpm_units_track*.parquet`) | #31 | same |

Notes for the pass: the merged PR should also delete the stale
`PENDING_WIRING` entry for `gee_math/earthquake_dpm_math.py` in
`tests/test_config.py` (its AOI is now read through the shared loader; the
file is no longer allowlisted, but the entry's removal belongs to the config
lane that owns that test). `mcp_servers/gee_fusion_mcp.py` still imports
`compute_earthquake_dpm_and_rupture`, a function that does not exist in
`gee_math/earthquake_dpm_math.py` — pre-existing on main, outside this
branch's scope (mcp lane).

## Run provenance summary

Both runs used: AOI `[-75.85, 4.40, -75.40, 5.15]` (config/bailasar.yaml
`aois.2_eje_cafetero_quake` via `src/bailasar/config.py`);
`config/preregistered.yaml` sha1 `24343020812977afe49c8495fc10113cd2c95af4`
(loader git-blob hash), **status draft**; thresholds built-up ≥ 0.50, non-built
≤ 0.10, min 20 built-up px per unit (config). One fresh Earthdata HTTPS
filesystem per granule (socket connect 30 s / read 120 s, 3 attempts, 32 MB
block cache, `docs/kb/nisar-gcov-read-timeouts.md` pattern); no granule
stalled or went missing (missing_granules = [] both runs). Full provenance,
including the sealed summaries, is in each `.zarr`'s `provenance` attr.
