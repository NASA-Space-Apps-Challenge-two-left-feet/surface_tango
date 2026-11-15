# Aburrá landslide InSAR — noise-floor result

**Label: PROVISIONAL.** Granules below are ASF provisional (`PR`) GUNW products.
Granizal (2025-06-24) predates the NISAR record and is not a detection here.
HKLSI is not computed.

## Verdict

kept downslope rates on 88517 pixels; noise floor 9.105 mm (17 pairs)

Noise floor: 9.105 mm *(measured)*.
Denominator: 17 pairs with a finite stable-pixel residual RMS,
out of 17 single-pol HH granules returned by the search
(17 GUNW hits before the SH filter; 0 UR copies of a PR pair were not reprocessed).
Pixels with a kept downslope rate: 88517.
That count is the sum of two native grids that were not resampled onto each other.
Ascending track 47 frame 5: 46009 of 176859 pixels (grid 457×387).
Descending track 11 frame 85: 42508 of 176859 pixels (grid 457×387).
Sign of the kept downslope rate (positive = downhill): ascending 21737 positive and 24272 negative; descending 23271 positive and 19237 negative.
Grid sizes are from `local_cache/aburra/stacks/*.npz`; sign counts are from `local_cache/aburra/summary.json` *(measured)*.

## Reproduce

```
uv run python -m gee_math.landslide_insar_math
```

Measured 2026-11-14 21:10 Bogotá (UTC−5); log time 2026-11-15T02:10:16Z.
Search: `asf.geo_search`, platform NISAR, processingLevel GUNW,
bbox [W, S, E, N] = [-75.7, 6.12, -75.42, 6.45] from `1_aburra_medellin_bello`, start 2026-06-17T00:00:00Z, end 2026-11-14T23:59:59Z.

## Method

- Ionosphere screen subtracted from `unwrappedPhase` (the screen ships unapplied).
- Stratified troposphere: LOS-vs-elevation least squares on valley-floor pixels
  (FABDEM slope ≤ 5.0°), inside the reference
  connected component, outside layover and shadow. Those pixels are the noise
  sample and are excluded from detection.
- Reference component: largest label other than 0 and fill 65535.
- d_LOS = −λ Δφ / 4π with λ = 0.24 m. Positive LOS points toward the sensor.
  The product spec states radians and the LOS unit vector; it does not state
  the phase sign. The sign used here is the ISCE convention cited in
  `los_displacement_mm`.
- Downslope projection uses FABDEM slope and aspect and the granule LOS unit
  vector. |cos ξ| < 0.2 stays missing.
- A rate is kept only where |LOS| exceeds that pair's residual RMS and the
  downslope sign agrees on two pairs that do not share an acquisition date,
  on the same native grid. Ascending and descending grids are not resampled
  onto each other.
- `config/preregistered.yaml` landslide block: absent (no landslide key).
- AOI `1_aburra_medellin_bello` read from `config/bailasar.yaml`: [-75.7, 6.12, -75.42, 6.45].

## Pairs

| Granule | Track | Ref → sec | Δt days | n stable | RMS mm | n eligible | n |LOS|>RMS |
|---|---|---|---:|---:|---:|---:|---:|
| NISAR_L2_PR_GUNW_023_047_A_005_024_4000_SH_20260617T103906_20260617T103941_20260629T103906_20260629T103940_P05023_N_F_J_001 | 47 ASCENDING fr 5 | 2026-06-17 → 2026-06-29 | 12.00 | 26456 | 7.728 | 99158 | 37440 |
| NISAR_L2_PR_GUNW_024_011_D_085_025_4000_SH_20260626T232840_20260626T232914_20260708T232839_20260708T232914_P05023_N_F_J_001 | 11 DESCENDING fr 85 | 2026-06-26 → 2026-07-08 | 12.00 | 29583 | 9.105 | 112729 | 43089 |
| NISAR_L2_PR_GUNW_024_047_A_005_025_4000_SH_20260629T103906_20260629T103940_20260711T103905_20260711T103939_P05023_N_F_J_001 | 47 ASCENDING fr 5 | 2026-06-29 → 2026-07-11 | 12.00 | 24158 | 5.465 | 89985 | 31386 |
| NISAR_L2_PR_GUNW_025_011_D_085_026_4000_SH_20260708T232839_20260708T232914_20260720T232838_20260720T232913_P05023_N_F_J_001 | 11 DESCENDING fr 85 | 2026-07-08 → 2026-07-20 | 12.00 | 28170 | 10.133 | 97905 | 32636 |
| NISAR_L2_PR_GUNW_025_047_A_005_026_4000_SH_20260711T103905_20260711T103939_20260723T103904_20260723T103939_P05023_N_F_J_001 | 47 ASCENDING fr 5 | 2026-07-11 → 2026-07-23 | 12.00 | 26586 | 8.290 | 74627 | 32164 |
| NISAR_L2_PR_GUNW_026_011_D_085_028_4000_SH_20260720T232838_20260720T232913_20260813T232837_20260813T232912_P05023_N_F_J_001 | 11 DESCENDING fr 85 | 2026-07-20 → 2026-08-13 | 24.00 | 26819 | 10.584 | 87202 | 31173 |
| NISAR_L2_PR_GUNW_026_047_A_005_028_4000_SH_20260723T103904_20260723T103939_20260816T103903_20260816T103937_P05023_N_F_J_001 | 47 ASCENDING fr 5 | 2026-07-23 → 2026-08-16 | 24.00 | 29084 | 8.218 | 98882 | 37254 |
| NISAR_L2_PR_GUNW_028_011_D_085_029_4000_SH_20260813T232837_20260813T232912_20260825T232837_20260825T232911_P05023_N_F_J_001 | 11 DESCENDING fr 85 | 2026-08-13 → 2026-08-25 | 12.00 | 29613 | 9.577 | 113127 | 48781 |
| NISAR_L2_PR_GUNW_028_047_A_005_029_4000_SH_20260816T103903_20260816T103937_20260828T103903_20260828T103937_P05023_N_F_J_001 | 47 ASCENDING fr 5 | 2026-08-16 → 2026-08-28 | 12.00 | 29175 | 7.898 | 104144 | 41490 |
| NISAR_L2_PR_GUNW_029_011_D_085_030_4000_SH_20260825T232837_20260825T232911_20260906T232837_20260906T232911_P05023_N_F_J_001 | 11 DESCENDING fr 85 | 2026-08-25 → 2026-09-06 | 12.00 | 29614 | 10.676 | 113294 | 35877 |
| NISAR_L2_PR_GUNW_029_047_A_005_030_4000_SH_20260828T103903_20260828T103937_20260909T103903_20260909T103937_P05023_N_F_J_001 | 47 ASCENDING fr 5 | 2026-08-28 → 2026-09-09 | 12.00 | 29597 | 6.027 | 112450 | 41967 |
| NISAR_L2_PR_GUNW_030_011_D_085_031_4000_SH_20260906T232837_20260906T232911_20260918T232837_20260918T232911_P05023_F_F_J_001 | 11 DESCENDING fr 85 | 2026-09-06 → 2026-09-18 | 12.00 | 29581 | 6.879 | 113236 | 40820 |
| NISAR_L2_PR_GUNW_030_047_A_005_031_4000_SH_20260909T103903_20260909T103937_20260921T103903_20260921T103937_P05023_N_F_J_001 | 47 ASCENDING fr 5 | 2026-09-09 → 2026-09-21 | 12.00 | 29517 | 9.535 | 110675 | 43465 |
| NISAR_L2_PR_GUNW_031_011_D_085_032_4000_SH_20260918T232837_20260918T232911_20260930T232837_20260930T232911_P05023_N_F_J_001 | 11 DESCENDING fr 85 | 2026-09-18 → 2026-09-30 | 12.00 | 27859 | 18.463 | 98795 | 25922 |
| NISAR_L2_PR_GUNW_031_047_A_005_032_4000_SH_20260921T103903_20260921T103937_20261003T103903_20261003T103937_P05023_N_F_J_001 | 47 ASCENDING fr 5 | 2026-09-21 → 2026-10-03 | 12.00 | 29517 | 9.243 | 111118 | 40602 |
| NISAR_L2_PR_GUNW_032_011_D_085_033_4000_SH_20260930T232837_20260930T232911_20261012T232837_20261012T232912_P05023_N_F_J_001 | 11 DESCENDING fr 85 | 2026-09-30 → 2026-10-12 | 12.00 | 28480 | 13.173 | 90136 | 23983 |
| NISAR_L2_PR_GUNW_032_047_A_005_033_4000_SH_20261003T103903_20261003T103937_20261015T103903_20261015T103937_P05023_N_F_J_001 | 47 ASCENDING fr 5 | 2026-10-03 → 2026-10-15 | 12.00 | 29574 | 6.017 | 111775 | 38281 |

## Notes on the pairs

No urgent-response copy of a provisional pair was returned by the search.
The hour-2 gate catalog `nisar_colombia_granules_2026.json` lists 20 Aburrá GUNW at `aois.1_aburra_medellin_bello.counts.GUNW`: 17 `PR` and 3 `UR` *(measured by reading that file)*.
The three UR names share dates with PR pairs on track 11 frame 85 and are not an extra independent sample:
`NISAR_L2_UR_GUNW_026_011_D_085_028_4000_SH_20260720T232838_20260720T232913_20260813T232837_20260813T232912_P05023_F_F_J_001` (2026-07-20 → 2026-08-13),
`NISAR_L2_UR_GUNW_028_011_D_085_029_4000_SH_20260813T232837_20260813T232912_20260825T232837_20260825T232915_P05023_F_F_J_001` (2026-08-13 → 2026-08-25),
`NISAR_L2_UR_GUNW_029_011_D_085_030_4000_SH_20260825T232837_20260825T232911_20260906T232837_20260906T232911_P05023_F_F_J_001` (2026-08-25 → 2026-09-06).
Temporal-baseline mismatch (not a 12-day pair; |Δt − 12| > 1 day), kept visible:
- NISAR_L2_PR_GUNW_026_011_D_085_028_4000_SH_20260720T232838_20260720T232913_20260813T232837_20260813T232912_P05023_N_F_J_001: Δt = 24.00 days (2026-07-20 → 2026-08-13) *(measured)*.
- NISAR_L2_PR_GUNW_026_047_A_005_028_4000_SH_20260723T103904_20260723T103939_20260816T103903_20260816T103937_P05023_N_F_J_001: Δt = 24.00 days (2026-07-23 → 2026-08-16) *(measured)*.
Product wavelength c/centerFrequency = 0.241963 m *(measured)*. Displacement uses λ = 0.24 m as fixed by the brief.

## Stacks

- track 47 frame 5 ASCENDING: 9 pairs on one grid, 46009 pixels kept, stack median RMS 7.898 mm *(measured)*.
- track 11 frame 85 DESCENDING: 8 pairs on one grid, 42508 pixels kept, stack median RMS 10.359 mm *(measured)*.

## FABDEM

GEE projects/sat-io/open-datasets/FABDEM; ee.Terrain.products after EPSG:3857 at 30 m. Grid 387×456 at ~80 m. Median elevation 2207.4 m on 176472/176472 finite pixels *(measured)*. AOI-center `reduceRegion` elevation 1509.0 m *(measured)*.

## Open limitations

- Cross-track sign agreement is not tested: each track keeps its native grid.
- The radar-grid LOS vector is the cell nearest the AOI center at the height nearest the FABDEM median, not the D-102272 §6 per-pixel interpolation.
- The 1-sigma RMS test is the rule in the brief. Valley-floor pixels are excluded from detection because they define that RMS.
- No granule after the last secondary date in the table intersects this box inside the search window.
