---
title: GUNW carries coherence at 20 m and 80 m, unwrapped phase at 80 m, and an ionosphere phase screen that is included but not applied
status: verified
source: https://nisar-docs.asf.alaska.edu/gunw/
accessed: 2026-11-14
quote: "The estimated ionospheric phase screen is included in the product but not applied to the data layers"
used_in: [gee_math/earthquake_dpm_math.py, gee_math/landslide_insar_math.py, scripts/prewarm_antioquia_cache.py]
verified_by: EstebanOchoaedos
supersedes: null
---

The opened ASF GUNW guide supports the title's layer postings (documented product specifications, rather than measured spatial resolution): coherence at 20 m and 80 m, and unwrapped phase at 80 m. It also lists the wrapped interferogram, connected components, offset layers, and ionospheric screen uncertainty.
The screen is not applied by default; inspect the processing metadata for each product before applying any correction. Posting does not establish independent resolving power.

Quote retrieved by Codex from the primary page on 2026-11-14; to be spot-checked by EstebanOchoaedos before merge.
