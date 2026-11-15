---
title: La Picacha LOS is a window of the Aburrá raster
status: verified
source: reports/aburra.md
accessed: 2026-11-15
quote: "No motion detected above 9.105 mm (17 pairs)."
used_in: scripts/window_parent_cache.py, app.py, mcp_servers/evidence.py
verified_by: uv run python scripts/window_parent_cache.py la_picacha
supersedes: null
---

The La Picacha display raster is the native cells of `aburra_los_disp_mm.tif`
that meet the configured barrio bbox. The valley sign-flip test is not rerun
on that window, so the early-warning light stays Not assessed.
A different parent granule or a barrio-specific pair test would replace this note.
