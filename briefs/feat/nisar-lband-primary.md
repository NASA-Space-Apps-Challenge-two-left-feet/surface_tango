# Brief: feat/nisar-lband-primary

- **Goal:** NISAR L-band is present, cached, and visibly the primary analysis layer wherever the platform claims an analysis. Downstream NISAR subproducts used by the heuristics are cached and cited, or the panel says not cached.
- **Issue:** none yet. Orchestrator handoff, 2026-11-15. Executor: Codex.
- **Files you may touch:** `app.py` panel status and tile routes, `static/index.html`, `static/story-map.js`, `static/aoi-nav.js`, `mcp_servers/evidence.py` only if a subproduct is dropped on the way to the envelope, `tests/` for the display contract, `README.md` status rows, `status/frontend-video.md`.
- **Out of scope:** New GEE or ASF processing. Fabricating an L-band raster for an AOI that has no granule. Editing `config/preregistered.yaml` or `validation/scoring.py`. Repainting the decision layer (that work is on `feat/decision-layer`).

## What "primary" means

Panel 3 is the NISAR L-band panel. Its label already says `NISAR L-band · PROVISIONAL`. The audit has to prove the pixels behind that label are the L-band product for the AOI on screen, and that Sentinel-2 and Sentinel-1 stay context. A chapter must not open on an optical tile while the caption claims NISAR.

## Check, in this order

1. Inventory `local_cache/<aoi>/` for mojana, aburra, eje_cafetero, la_picacha, choco_epicenter, valle_del_cauca. Record which of these files exist: GCOV or open-water mask, GUNW or landslide evidence, `quake_evidence_track11.json`, `quake_evidence_track47.json`, tile manifest. Write the inventory into the PR body. Do not invent a row.
2. For each file that exists, name the granule IDs already inside it. The Mojana headline granule is `NISAR_L2_PR_GCOV_023_047_A_005_4005_DHDH_A_20260617T103906_20260617T103941_P05023_F_F_J_001` (`reports/mojana.md`). Confirm the UI's 17 June mask cites that id.
3. Trace the UI. `GET` the tile or mask the L-band panel requests for La Mojana, Aburrá, and Eje Cafetero. The response must be the cached L-band artifact, with provenance. If the handler falls through to Sentinel or to an empty canvas, fix the route.
4. Subproducts the heuristics consume must be the same files the panel can show, or the decision card must say the layer is not cached:
   - Flood: open-water extent from GCOV (`analyze_flood_inundation`).
   - Landslide: GUNW kinematics (`analyze_landslide_kinematics`).
   - Earthquake: per-track DPM window (`analyze_earthquake_dpm`), tracks 11 and 47. Pixel counts are a window, not hectares.
5. Where the cache has no L-band product (expected today for La Picacha, and for Chocó and Valle if their evidence files are absent), the panel state is `not cached`. Do not borrow another AOI's raster.

## Acceptance

- A test or a documented curl shows the L-band panel URL for mojana, aburra, and eje_cafetero returns 200 and a body whose provenance matches the cache artifact.
- The on-screen label stays PROVISIONAL for provisional (`PR`) granules.
- No number is added in JavaScript.
- `make sync` before commit. Commit locally. Do not push.

## Paste-in prompt

```
You are the executor on Surface Tango. Read AGENTS.md, then briefs/feat/nisar-lband-primary.md, and do only that.

Work in a new worktree from latest origin/main:
  cd /Users/andresbecerra/Documents/surface_tango && make worktree BRANCH=feat/nisar-lband-primary
  cd /Users/andresbecerra/Documents/surface_tango-worktrees/feat-nisar-lband-primary

Audit and fix the mission-control display so the NISAR L-band product is what panel 3 shows for every AOI that has one in local_cache. Sentinel-2 and Sentinel-1 stay context. Downstream subproducts (GCOV open water, GUNW landslide kinematics, quake DPM windows for tracks 11 and 47) must be the cached artifacts the panel and the envelopes already use. If an AOI has no L-band artifact, the panel says not cached. Never copy another AOI's raster and never zero-fill.

Run make sync before you commit. Commit locally. Do not push, merge, or edit config/preregistered.yaml.
```
