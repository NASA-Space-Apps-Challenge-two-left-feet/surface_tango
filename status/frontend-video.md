# Status: frontend-video

_Last update: 2026-11-14 (UTC−5)_

- Doing: #22. Mission control reads the Aburrá cache from the merged builder, exposes the manifest source granule, and removes the remaining biomass inspector and map styling.
- Doing: #37. Both curtain layouts use the staged Sentinel scenes. Aburrá has LOS context, Eje Cafetero has the released pre-event coherence and the documented scorecard null, and La Mojana shows the measured open-water mask and sensitivity. Co-event coherence stays unavailable.
- Story cache setup: Run `uv run python static/prepare_story_cache.py --cache-dir <shared-cache-root>` after assembling the cache release. The script checks the La Mojana mask against its report and adds display assets to the ignored story-results file. Point `BAILASAR_CACHE_DIR` at the same directory.
- BLOCKED: The Aburrá noise-floor verdict and measured synthesis links need publication from their owners. Their chapters show the missing result explicitly.
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
