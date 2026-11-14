# Baseline import notes (issue #1)

Source: the team's earlier Gemini architecture session (shared chat). 67 code blocks were extracted as text and nothing was executed. For each file, the most complete version from before the export was taken. The turn-17 "verbatim export" copies were shorter, so they were not used.

## Changed on import (no-synthetic-data rule, AGENTS.md)
- `scripts/prewarm_antioquia_cache.py`:
  - **Synthesizer removed.** Every band that could not be fetched (FABDEM slope, CHIRPS, ESA AGB, GCOV HH/HV pre/post, GUNW phase, ionosphere, coherence, connected components) is now an all-NaN array marked `"missing"` in the provenance. Before, it was generated from formulas plus `np.random`, including a planted Gaussian "landslide" and "seismic patch".
  - `nan_to_num(nan=0.0)` removed: missing pixels stay NaN, and the coverage check counts finite pixels.
  - The ionosphere screen is saved as real data. Before, an all-zeros COG was written as "iono". Phase correction only runs when both the phase and the ionosphere layers exist; otherwise no displacement is computed (see the gate table).
  - `downslope_disp_mm` renamed to `los_disp_mm`. The troposphere fit and the downslope projection are left as a TODO for the Aburrá lane.
- `static/index.html`: preloaded demo hazard results and the bulletin ("612.8 tC", "22.4 mm", "145 mm") removed. Panels start empty ("Awaiting measured results").
- `README.md`: the `logo=nasa` badge logo is removed (branding rule), and the S-band claim is removed.
- `pyproject.toml` is not included: the generated block was a directory tree, not TOML. The Data lane creates a pinned one (issue #2).

## Left for the lanes (in `docs/baseline/unapplied_patches/`)
| Patch | Lane / issue | Note |
|---|---|---|
| `app_py_tile_server_addition.py` | Frontend #12 | adds the local Zarr XYZ tile endpoint to `app.py` |
| `mcp_servers_transport_main_block.py` | Agents/MCP #10 | the generated default is `stdio`; D4 requires **SSE** on 8001/8002 |
| `orchestrator_snippet.py` | Agents/MCP #11 | config/env wiring for the orchestrator |
| `makefile_*.mk` | Data #4 | prewarm, discover and tmux targets |
| `story_map_*.html/js` | Frontend #12 | **contains fabricated narrative numbers (612 tC, 22.4 mm, 145 mm); replace with placeholders from measured outputs before use** |

## Also flagged
- `prewarm_antioquia_cache.py` manifest: the `optical_s2` template points at Google satellite basemap tiles (`mt1.google.com`), which are not Sentinel-2. Replace with real S2 tiles from GEE (Data #4).
- `gee_math/biomass_polarimetric_math.py` and the biomass agent are out of scope (TODO 1). They are kept, but not wired into the 3-agent graph target.
- `mcp_servers/*.py` call `mcp.run()` (stdio by default). Set SSE per D4.
- No `.env` is committed. The generated `.env` block had placeholder keys only; credentials go in `.env.example` names (issue #2).
