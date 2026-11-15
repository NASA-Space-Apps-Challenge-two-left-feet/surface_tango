---
title: ee.Image.resample() accepts only "bilinear" or "bicubic"; nearest neighbour is the default when resample() is not called
status: verified
source: https://developers.google.com/earth-engine/apidocs/ee-image-resample
accessed: 2026-11-15
quote: "uses bilinear or bicubic interpolation (rather than the default nearest-neighbor) to compute pixels in projections other than its native projection"
used_in: [gee_math/flood_polarimetric_math.py, scripts/build_cache.py (connectedComponents)]
verified_by: "codex (fetched 2026-11-15), pending EstebanOchoaedos spot-check"
supersedes: null
---

The quote is the error Earth Engine returned to the La Mojana HAND fetch on 2026-11-14 (reports/mojana.md first draft, measured), not text from the docs page. Categorical layers (connected components, classes, masks) must therefore skip resample() rather than ask for "nearest". To verify: read the allowed modes on the apidocs page and quote them.

The original measured error message was `Image.resample: Invalid interpolation mode: nearest.`; the front-matter quote now contains documentation text.

Verified against https://developers.google.com/earth-engine/apidocs/ee-image-resample on 2026-11-15: the description identifies nearest-neighbor as the default, and the mode argument accepts only bilinear or bicubic. Page fetched successfully through the web tool; HTTP status was not exposed.
