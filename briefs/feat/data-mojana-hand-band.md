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

### Done

`scripts/build_cache.py` now samples MERIT Hydro `MERIT/Hydro/v1_0_1` band `hnd` as `hand_m` for a La Mojana build, and `--only-band hand_m` appends that band onto the cube that is already on disk. The sample grid is read from the cube coordinates and `crs` attribute. Masked pixels are unmasked to the -9999 sentinel and stored as NaN. A value of 0 m is kept. `resample()` is not called.

The grid read from `local_cache/mojana/mojana_sar_cube.zarr` is EPSG:4326, 512 by 512, coordinates on bbox `[-75.4, 7.9, -74.2, 9.2]`.

Build command (foreground):

```
PYTHONUNBUFFERED=1 uv run python scripts/build_cache.py --aoi mojana --only-band hand_m
```

Output tail:

```
HAND grid read from cube: crs=EPSG:4326 512x512 scale_x=0.0023437500000000056 scale_y=-0.002539062499999998 translate=(-75.4, 9.2)
hand_m finite pixels: 262144 of 262144 (ratio 1.0) *(measured)*
manifest finite_pixel_ratio: 1.0
appended hand_m to local_cache/mojana/mojana_sar_cube.zarr
```

Finite ratio *(measured)*: 262144 / 262144 = 1.0. A follow-up read of that array: min 0.0 m, max 716.0 m, same denominator 262144. `manifest.json` lists `hand_m` as `cached`, source `MERIT/Hydro/v1_0_1`, band `hnd`, version `v1_0_1`, grid EPSG:4326 512×512. No `hand_m` COG was written.

`local_cache/mojana/provenance.json` was not modified (sha256 unchanged: `996c1e64b96b1a480b2b1e2a36dbefda3bd860cf6612f89cfdee77b3f52dea6a`). COGs and tiles were not modified. `to_zarr` mode `a` rewrote the `y` and `x` coordinate chunks; their values still match `linspace` of the bbox edges (max absolute difference 0). The same call cleared root attributes; they were restored to `aoi=mojana`, `aoi_key=3_la_mojana_caregato`, `bbox=[-75.4, 7.9, -74.2, 9.2]`, `crs=EPSG:4326`. `write_hand_variable` now writes those attributes back.

Fixture cut:

```
uv run python scripts/cut_fixtures.py --aoi mojana --name flood --row 0 --col 0 --size 32 \
  --vars gcov_hhhh_pre gcov_hvhv_pre gcov_hhhh_post gcov_hvhv_post hand_m
```

Wrote `tests/fixtures/mojana/flood.npz` and `tests/fixtures/mojana/flood.provenance.json`. Left untracked: `tests/fixtures/README.md` says a human reviews the arrays before commit.

```
uv run pytest -q tests/test_pipeline_flood.py -m cache -rs
4 passed in 0.10s
```

`uv run pytest -q tests/test_cache_builder.py`: 15 passed.

### Completion note (opencode, acting orchestrator, 2026-11-15 ~08:45 UTC)

Finishing this lane after the session stopped. Findings and corrections:

- Branch synced onto current main; `make ci` at head: **341 passed, 7 deselected** *(measured)* (main 334 + this lane's builder tests).
- Cache state verified: `local_cache/mojana/manifest.json` lists `hand_m` (source `MERIT/Hydro/v1_0_1`, status `cached`, finite_pixel_ratio 1.0); `local_cache/mojana/provenance.json` sha256 verified unchanged (`996c1e64…`, as the report above claims).
- **The fixture cut above was vacuous and has been replaced.** Its row 0/col 0 window was NaN in all four GCOV bands (0/1024 finite each; the granule footprint does not cover the grid corner), so the "4 passed" ran on an all-NaN observation. The joint coverage analysis found 19,878 jointly-finite pixels in the cube; the best window is **row 432, col 240** (1024/1024 jointly finite). Re-cut `flood` there (the old untracked cut was never committed and was removed first):
  - `gcov_hhhh_pre` 0.028–1.446 · `gcov_hvhv_pre` 0.0085–0.244 · `gcov_hhhh_post` 0.026–2.734 · `gcov_hvhv_post` 0.0092–0.276 (linear power) · `hand_m` 0–56.78 m — all *(measured)*, 32×32, digest matches sidecar.
  - `tests/test_pipeline_flood.py -m cache`: **4 passed** on real coverage; `tests/test_cut_fixtures.py`: 10 passed.
- The fixture commit still awaits the human review the fixtures README requires (arrays, sidecar, provenance) — flagged to the owner.
