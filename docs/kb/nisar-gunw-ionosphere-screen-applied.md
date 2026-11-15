---
title: BailaSAR applies the GUNW ionosphere phase screen — los_disp_mm = -(λ/4π)·(unwrappedPhase − ionospherePhaseScreen), λ = 240 mm
status: verified
source: https://nisar-docs.asf.alaska.edu/gunw/
accessed: 2026-11-15
quote: "The estimated ionospheric phase screen is included in the product but not applied to the data layers"
used_in: [scripts/build_cache.py, gee_math/earthquake_dpm_math.py, gee_math/landslide_insar_math.py]
verified_by: opencode-acting-orchestrator (measured)
supersedes: null
---

The product ships the screen unapplied (see nisar-gunw-layers.md); our pipeline applies it: `scripts/build_cache.py` subtracts the screen before the millimetre conversion (merged in #78). Measured: `los_disp_mm` and `gunw_phase_corr` cached with granule provenance and honest finite ratios for six GUNW granules (eje R/C/K, Aburrá ×2, Mojana ×1; `local_cache/<aoi>/manifest.json`). This complements, not supersedes, nisar-gunw-layers.md.
