# Brief: feat/cache-full-aoi-coverage

- **Goal:** Every analysis layer for an AOI shares one geographic frame, so the curtain slider never opens onto a blank wedge.
- **Issue:** none yet. Orchestrator handoff, 2026-11-15. Executor: Grok.
- **Owner lane:** Data + gate for cache tiles. Frontend only for the slider math that consumes those tiles.
- **Files you may touch:** `scripts/prestage_tiles.py`, tile manifests under `local_cache/<aoi>/tiles/` (generated, not committed), `static/story-map.js`, `app.py` tile routes if the manifest contract changes, `tests/` for the tile contract, `README.md` status row if a layer moves between live, cached, and not cached, `status/data.md`.
- **Out of scope:** Inventing pixels. Zero-fill. Stretching a footprint to pretend it covers the config AOI. Editing `config/preregistered.yaml`. The decision-layer products. The VM deploy.

## The problem

The navigator already frames the camera to `footprint_bbox` when the data footprint is smaller than the config AOI (`static/aoi-nav.js`). The curtain (`#handle-1`, `#handle-2` in `static/index.html`, clip-path in `static/story-map.js`) still reveals whatever each panel has loaded. If optical, C-band, and L-band tiles do not share bounds, a slider position shows empty canvas between products. Empty canvas reads as a hole in the disaster, which is worse than a labeled gap.

## The rule

1. Pick one frame per AOI: the intersection of the layers that actually have tiles. Frame the camera to that polygon.
2. Every layer is warped to that frame. A layer with no observation inside the frame is a labeled no-data hatch, with provenance, not a transparent hole and not a zero.
3. The curtain is a clip of three co-registered panels. Moving the handle changes the clip only. It does not change bounds, zoom, or pixel size.
4. Missing stays missing. If a granule does not cover the config AOI, say so on the panel (`coverage_pct` already exists). Do not mosaic invented data out to the config bbox.
5. Do this for every AOI that has a tile manifest. Today that is the cached set (Aburrá, Eje Cafetero, La Mojana). La Picacha, Chocó epicenter, and Valle del Cauca stay "not cached" until real tiles exist. A not-cached panel is an explicit state, not a blank map.

## Acceptance

- For mojana, aburra, and eje_cafetero, a script walks the curtain from 5% to 95% and asserts each panel's geographic bounds are identical at every stop.
- A pixel that is no-data is marked no-data in the tile and reads as no-data in the UI. It is never 0.
- The story chapter change still uses the two-feet transition and lands on the same frame.
- `uv run pytest -q` for the new tile-contract test, offline. Do not claim `make ci` is green. The trunk already fails `tests/test_cut_fixtures.py` and `tests/test_parquet_roundtrip.py`.

## Paste-in prompt

```
You are the executor on Surface Tango. Read AGENTS.md, then briefs/feat/cache-full-aoi-coverage.md, and do only that.

Work in a new worktree from latest origin/main:
  cd /Users/andresbecerra/Documents/surface_tango && make worktree BRANCH=feat/cache-full-aoi-coverage
  cd /Users/andresbecerra/Documents/surface_tango-worktrees/feat-cache-full-aoi-coverage

Make the optical, Sentinel-1 C-band, and NISAR L-band layers for each cached AOI share one frame so the curtain slider never reveals an empty wedge. Co-register real tiles. Where a layer has no observation, draw a labeled no-data hatch. Never zero-fill and never invent coverage out to the config AOI. La Picacha, Chocó, and Valle del Cauca stay not cached.

Run make sync before you commit. Commit locally with a Conventional Commit. Do not push, merge, or edit config/preregistered.yaml.
```
