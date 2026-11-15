---
title: ee.Terrain.slope needs a metric projection — slopes from a geographic-CRS DEM (FABDEM) are suspect
status: unverified
source: https://developers.google.com/earth-engine/apidocs/ee-terrain-slope
accessed: 2026-11-15
quote: ""
used_in: [scripts/build_cache.py, gee_math/landslide_insar_math.py, "feat/data-aburra-insar 9fe0077 pending review"]
verified_by: pending
supersedes: null
---

grok (Aburrá lane, #33) hit this and committed `fix(landslide): derive FABDEM slope in a meter projection` (9fe0077, unpushed, awaiting orchestrator review). Concern: `scripts/build_cache.py` computes `ee.Terrain.slope(FABDEM)` and samples pixels in EPSG:4326 — the cached `slope_deg` bands may be invalid until the fix lands and the cache is rebuilt. FABDEM elevation is in metres. Primary-source read pending.

Checked https://developers.google.com/earth-engine/apidocs/ee-terrain-slope on 2026-11-15: states that input elevation is in meters and output slope is in degrees; does not state that a metric CRS is required or that a geographic-CRS DEM yields invalid slopes. Page fetched successfully through the web tool; HTTP status was not exposed.
