# Brief: feat/data-mojana-hand-band — add the MERIT Hydro HAND band to the cache (agent: grok2)

- **Goal:** add a `hand_m` (Height Above Nearest Drainage) band to the La Mojana cache so Esteban's flood pipeline fixture (#121) can be cut and his flood pipeline tests can run. Today `scripts/cut_fixtures.py --aoi mojana ... hand_m` fails with **"variable absent from cube: hand_m"** because the cache builder never stored HAND; the flood pipeline fetches it from Earth Engine at run time.
- **Issue:** #38 / #121 (flood fixture enablement). **Reference:** `scripts/build_cache.py` (the cache builder), `gee_math/flood_polarimetric_math.py` (how the flood code reads HAND today), `tests/fixtures/README.md` (the fixture-cut command that must work after this).
- **Source:** MERIT Hydro, Earth Engine asset `MERIT/Hydro/v1_0_1`, band `hnd` (HAND, metres). Same AOI and sampling grid as the other `mojana` bands.

## What to build
1. In `scripts/build_cache.py`, add a `hand_m` band to the La Mojana cube: sample `MERIT/Hydro/v1_0_1` band `hnd` onto the existing mojana grid (EPSG:32618, 90 m, the grid the cube already uses — read it from the cube/manifest, don't hardcode). Missing pixels stay NaN and `missing` in the manifest (never zero-filled). Record provenance per the existing pattern: asset ID `MERIT/Hydro/v1_0_1`, band `hnd`, version, the grid, source = the asset.
2. Regenerate **only** the `hand_m` band into `local_cache/mojana/mojana_sar_cube.zarr` and update `local_cache/mojana/manifest.json` to list the new band with its provenance and finite-pixel ratio. Do **not** rebuild the other mojana bands, and do **not** touch `local_cache/mojana/provenance.json`, the COGs or the tiles (another agent reads those).
3. Verify the fixture now cuts:
   ```
   uv run python scripts/cut_fixtures.py --aoi mojana --name flood --row 0 --col 0 --size 32 \
     --vars gcov_hhhh_pre gcov_hvhv_pre gcov_hhhh_post gcov_hvhv_post hand_m
   uv run pytest -q tests/test_pipeline_flood.py -m cache -rs
   ```
   The flood pipeline tests should now pass (not skip) with the fixture present.

## Acceptance
- `make ci` green; if you add a unit test, it is a hand-written-array check of the HAND sampling/missing-handling (no network).
- The mojana cube has a `hand_m` band; `manifest.json` lists it with its MERIT provenance and finite ratio *(measured)*.
- `scripts/cut_fixtures.py --aoi mojana ... hand_m` succeeds and `tests/test_pipeline_flood.py -m cache` passes.
- Your report has the build command, the finite-pixel ratio of `hand_m`, and the fixture-cut + test result.

## Rules (AGENTS.md)
- No synthetic or fabricated data; missing HAND stays NaN + `missing`. Never zero-fill.
- Every number *(measured)* with its denominator.
- Files you may touch: `scripts/build_cache.py`, `tests/test_cache_builder.py`, this brief. Writing `local_cache/mojana/` (cube + manifest) is expected; do not touch `provenance.json`, COGs, tiles, or any other AOI.
- Earth Engine via `gee_math/ee_session.init_ee()`; run the live job in the **foreground**.
- `ee.Terrain`/categorical reads: do not call `.resample("nearest")` — nearest is the default (see `docs/kb/gee-image-resample-modes.md`).
- `make sync` before each commit; `make ci` before you finish. Commit locally (`Refs: #38`, `Co-Authored-By: grok`). Do **not** push, merge, switch branches, reset, stash, open PRs or run `gh`.

## If blocked
Write `BLOCKED: <reason>` at the end of this file and stop.

## Report (append when done)
What you built, the build command and output tail, the `hand_m` finite ratio, and the fixture-cut + `test_pipeline_flood` result.
