---
title: ee.Image.resample() accepts only "bilinear" or "bicubic"; nearest neighbour is the default when resample() is not called
status: unverified
source: https://developers.google.com/earth-engine/apidocs/ee-image-resample
accessed: 2026-11-14
quote: "Image.resample: Invalid interpolation mode: nearest."
used_in: [gee_math/flood_polarimetric_math.py, scripts/build_cache.py (connectedComponents)]
verified_by: null
supersedes: null
---

The quote is the error Earth Engine returned to the La Mojana HAND fetch on 2026-11-14 (reports/mojana.md first draft, measured), not text from the docs page. Categorical layers (connected components, classes, masks) must therefore skip resample() rather than ask for "nearest". To verify: read the allowed modes on the apidocs page and quote them.
