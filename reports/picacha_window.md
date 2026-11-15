# La Picacha LOS window

**Label: PROVISIONAL.** This is a native-grid window of the Aburrá LOS raster.
It is not a new noise-floor test and it is not a barrio motion detection.

## What was measured

Command: `uv run python scripts/window_parent_cache.py la_picacha`

Parent raster: `local_cache/aburra/cogs/aburra_los_disp_mm.tif`

Granule: `NISAR_L2_PR_GUNW_032_047_A_005_033_4000_SH_20261003T103903_20261003T103937_20261015T103903_20261015T103937_P05023_N_F_J_001`

Child bbox, from `config/bailasar.yaml` key `6_la_picacha_landslide`:
[-75.6404, 6.2313, -75.6191, 6.2367]

| Quantity | Value | Denominator |
|---|---:|---|
| Finite pixels in the window | 312 | 312 native parent pixels |
| Window median LOS | -141.124 mm | 312 finite pixels |
| Parent median LOS | -140.723 mm | 262,144 finite pixels |
| Sentinel-2 tiles copied | 6 | tiles whose footprint meets the bbox |
| Sentinel-1 tiles copied | 6 | tiles whose footprint meets the bbox |
| Zoom-13 pixel centers inside the bbox, observed | 3,844 | 3,844 (optical and C-band, each) |

The window median sits next to the parent median. The Aburrá valley test remains
**no motion detected above 9.105 mm (17 pairs)** (`uv run python -m gee_math.landslide_insar_math`,
[reports/aburra.md](aburra.md)). That test was not repeated on these 312 pixels.
The decision card for La Picacha stays **Not assessed**.

Sentinel scenes are the Aburrá scenes, copied as bytes: optical 2026-07-06 and
C-band 2026-07-03. Scene ids stay in `local_cache/la_picacha/tiles/manifest.json`.
