---
title: MERIT Hydro hnd is height above the nearest drainage, not a surveyed water depth
status: unverified
source: https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1
accessed: 2026-11-15
quote: "Hydrologically adjusted elevations, also know as \"hand\" (height above the nearest drainage)."
used_in: [mcp_servers/flood_display.py, app.py, static/story-map.js]
verified_by: pending
supersedes: null
---

The Earth Engine catalog describes band `hnd` as height above the nearest drainage. The La Mojana overlay paints that band on measured open-water pixels and says so in the legend. The frozen `flood.hand_max_m` gate is only the pale end of the display ramp. It is not an inundation depth, and a wet pixel with no HAND value stays a flat blue. A teammate still needs to confirm the quote against the catalog page.
