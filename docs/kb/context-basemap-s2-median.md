---
title: Sentinel-2 cloud-free median is visor context, not a measurement
status: unverified
source: https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_CLOUD_SCORE_PLUS_V1_S2_HARMONIZED
accessed: 2026-11-15
quote: "Cloud Score+ outputs can be used to identify relatively clear pixels and effectively remove clouds and cloud shadows"
used_in: config/bailasar.yaml, scripts/build_context_basemap.py, static/context-basemap.js
verified_by: null
supersedes: docs/kb/context-satellite-basemap.md
---

The curtain asks the app for same-origin XYZ tiles cut from a 2025
Sentinel-2 SR median (`COPERNICUS/S2_SR_HARMONIZED`, bands B4, B3, B2).
Clear pixels are `cs_cdf >= 0.60`, the catalog example threshold.
A masked pixel stays transparent. The dark field shows through.
The stretch is display-only. This photograph is not a hazard measurement.
Planet NICFI is probed and not copied onto the public visor.
The measured scene counts and finite-pixel ratios land in
`local_cache/context-basemap/manifest.json` when the build runs.
