# Status: frontend-video

_Last update: 2026-11-15 (UTC−5)_

## feat/web-offline-pitch (#37, #39/#43 prep)

- Done: The page opens on **La Mojana** (the ratified headline). `?chapter=live` keeps mission control. Chapter numbers come from `/api/pitch-facts`. That endpoint uses `video/report_facts.py` to parse `reports/mojana.md`, `reports/aburra.md` and `validation/README.md`. `static/story-evidence.json` now holds `{placeholders}` only, and each summary carries its report sources (`data-fact-sources`). If a report line changes shape, the chapter shows **Error** instead of an old number.
- Done: Panel states come from `/api/cache-bands/<aoi>` (manifest band `status`). The quake co-event panel always shows **Not cached · C/K sealed**, whatever the cache holds. Sentinel panels show the share of the AOI imaged, from the tiles manifest (La Mojana S2 86.22%, S1 45.44% *(measured by `scripts/prestage_tiles.py --aoi mojana`)*). This explains the mostly dark S1 curtain.
- Done: Removed the unsourced coherence/dB numbers from the physics-inspector diagrams.
- Done: `video/assemble.py` renders the silent 30 s draft (1920×1080, 30 fps) from the storyboard timings. Report-sourced cards and VO placeholders are in `video/README.md`. Output: `video/draft_cut.mp4` (git-ignored; ffprobe duration 30.000000).
- Offline check (2026-11-15): Docker is not installed on this laptop, so `make pitch` was not run. Instead, the app ran with `OFFLINE_DEMO_MODE=1 uv run uvicorn app:app --port 8765` against the cache release. Every browser request in the La Mojana, Aburrá and quake chapters went to `127.0.0.1` (network log). There were no external URLs, and no panel was blank.
- Needs another lane (not done here): (1) The `Dockerfile` copies neither `reports/`, `validation/` nor `video/`. Under `make pitch`, `/api/pitch-facts` would return 500 and the chapters would show **Error**. Data + gate lane: add those copies. (2) Brief step 5 (move `static/prepare_story_cache.py` to `scripts/`) is outside this lane's paths. It stays in `static/` for now, and it now reads its expected counts from the report parser.
- Done: `tests/test_web_pitch.py` pins the report parser, the placeholder summaries and the 30 s storyboard timings. The README Status rows and an offline run section are updated.

- Doing: #22. Mission control reads the Aburrá cache from the merged builder, exposes the manifest source granule, and removes the remaining biomass inspector and map styling.
- Doing: #37. Both curtain layouts use the staged Sentinel scenes. Aburrá has LOS context and its calibrated null verdict, Eje Cafetero has the released pre-event coherence and the documented scorecard null, and La Mojana shows the measured open-water mask and sensitivity. Co-event coherence stays unavailable.
- Story cache setup: Run `uv run python static/prepare_story_cache.py --cache-dir <shared-cache-root> --release-manifest <downloaded-cache-manifest>` after assembling the cache release. The script checks the La Mojana mask against its report and adds display assets to the ignored story-results file. Point `BAILASAR_CACHE_DIR` at the same directory.
- Synthesis: The chapter summarizes the published hazard outcomes. No cross-hazard arcs appear until the science lane supplies a measured link.
- Story handoff: Supply `local_cache/story-results.json` in the shared cache, keyed by `landslide`, `earthquake`, `flood`, and `synthesis`. Each available chapter needs `state` (`live`, `cached`, or `gate`), `summary`, and `source` (report and provenance). Optional `bounds` uses [west, south, east, north]. Optional `panels` lists the three panel entries in order, each with `tile_url` and `state` (`live` or `cached`). Cached URLs must be same-origin. Quake `ranked_barrios` entries use `position` ([longitude, latitude]) and `rank`. Synthesis `links` entries use `from`, `to`, and `source` for the measured link. Missing chapters remain in **Not cached** until the approved outputs arrive.
- Done:
- Verification: Changed-file pre-commit checks passed on the updated trunk, including the secret scan. Offline HTTP checks cover missing cache and gate inputs and stream failure.
- Cache handoff: Keep the builder output `local_cache/aburra/aburra_sar_cube.zarr/` together with `local_cache/aburra/manifest.json`. The older `local_cache/antioquia_aburra/` layout still works. Set `BAILASAR_CACHE_DIR` to the shared cache root if the worktree has no cache link. The cube route serves LOS displacement with recorded provenance. Quake and flood comparisons need approved story tiles.
- Sentinel tile handoff: Keep each AOI's `tiles/manifest.json` with its `tiles/s1/` and `tiles/s2/` PNGs. Mission control uses the Aburrá cache for the reference panels when a live source is unavailable. The tile API also accepts Eje Cafetero and La Mojana.
- Gate handoff: Optional `gate-panel-results.json` in the same directory maps `landslide`, `flood`, or `earthquake` to the approved coverage or null statement. This is a UI adapter. Populate it from the approved plan 02-01 output once available.
- Cache verification for #22: Assembled the private cache release with `scripts/cache_release.py assemble`. Mission control rendered Aburrá Sentinel and NISAR LOS PNGs with recorded provenance. Withheld co-event bands stay unavailable. The Agents/MCP lane owns the remaining biomass node in the backend graph.

## Stage frontend assets once, before going offline

Run from the frontend worktree with its `local_cache` linked to the shared cache:

```sh
npm install --prefix local_cache/frontend-assets --ignore-scripts --no-audit --no-fund --save-exact maplibre-gl@4.7.1 deck.gl@9.0.34 tailwindcss@3.4.17
node local_cache/frontend-assets/node_modules/tailwindcss/lib/cli.js -i static/mission-control.tailwind.css -o local_cache/frontend-assets/mission-control.css --content "static/index.html,static/story-map.js" --minify
```

Keep `local_cache/frontend-assets/` with the offline cache bundle. The client uses local assets and a neutral background while chapter tiles are unavailable.
