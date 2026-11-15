# Status: frontend-video

_Last update: 2026-11-14 (UTC−5)_

- Doing: #22. Mission control reads the Aburrá cache from the merged builder, exposes the manifest source granule, and removes the remaining biomass inspector and map styling.
- Doing: #37. Two curtain layouts and four story chapters are wired to approved outputs.
- Story handoff: Supply `local_cache/story-results.json` in the shared cache, keyed by `landslide`, `earthquake`, `flood`, and `synthesis`. Each available chapter needs `state` (`live`, `cached`, or `gate`), `summary`, and `source` (report and provenance). Optional `bounds` uses [west, south, east, north]. Optional `panels` lists the three panel entries in order, each with `tile_url` and `state` (`live` or `cached`). Cached URLs must be same-origin. Quake `ranked_barrios` entries use `position` ([longitude, latitude]) and `rank`. Synthesis `links` entries use `from`, `to`, and `source` for the measured link. Missing chapters remain in **Not cached** until the approved outputs arrive.
- Done:
- Verification: Changed-file pre-commit checks passed on the updated trunk, including the secret scan. Offline HTTP checks cover missing cache and gate inputs and stream failure.
- Cache handoff: Keep the builder output `local_cache/aburra/aburra_sar_cube.zarr/` together with `local_cache/aburra/manifest.json`. The older `local_cache/antioquia_aburra/` layout still works. Set `BAILASAR_CACHE_DIR` to the shared cache root if the worktree has no cache link. The cube route serves LOS displacement with recorded provenance. Quake and flood comparisons need approved story tiles.
- Gate handoff: Optional `gate-panel-results.json` in the same directory maps `landslide`, `flood`, or `earthquake` to the approved coverage or null statement. This is a UI adapter. Populate it from the approved plan 02-01 output once available.
- BLOCKED: Real PNG rendering needs the Aburrá Zarr cube and its provenance manifest from the data team. The Agents/MCP lane owns the remaining biomass node in the backend graph.

## Stage frontend assets once, before going offline

Run from the frontend worktree with its `local_cache` linked to the shared cache:

```sh
npm install --prefix local_cache/frontend-assets --ignore-scripts --no-audit --no-fund --save-exact maplibre-gl@4.7.1 deck.gl@9.0.34 tailwindcss@3.4.17
node local_cache/frontend-assets/node_modules/tailwindcss/lib/cli.js -i static/mission-control.tailwind.css -o local_cache/frontend-assets/mission-control.css --content "static/index.html,static/story-map.js" --minify
```

Keep `local_cache/frontend-assets/` with the offline cache bundle. The client uses local assets and a neutral background while chapter tiles are unavailable.
