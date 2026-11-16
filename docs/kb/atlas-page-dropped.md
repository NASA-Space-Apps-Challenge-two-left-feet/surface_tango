---
title: The regional cube page is not part of the observatory
status: verified
source: https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango/pull/213
accessed: 2026-11-15
quote: "feat(web): add the atlas regional cube explorer"
used_in: app.py, static/index.html, README.md
verified_by: removal of the /cube route and the header link
supersedes: docs/kb/atlas-display-native-grid.md
---

The atlas page at `/cube` and its catalog API were removed after pull
request #213. Science Zarr stores under each area of interest stay.
The local check record `reports/regional-cube-local.json` stays as the
measurement from before the page was dropped.
