# Real pipeline fixtures

Fixtures are unchanged spatial cuts from a real local Zarr cube. Each archive must
have a matching `.provenance.json` sidecar. Never create replacement data or edit
values, NaNs, source identifiers, or a recorded `missing` status. Fixtures are
committed only after a human reviews the arrays and their provenance.

From the repository root, after a human builds or downloads the real cache, run:

```sh
uv run python scripts/cut_fixtures.py --aoi antioquia_aburra --name flood --row 0 --col 0 --size 32 --vars gcov_hhhh_pre gcov_hvhv_pre gcov_hhhh_post gcov_hvhv_post
uv run python scripts/cut_fixtures.py --aoi antioquia_aburra --name landslide --row 0 --col 0 --size 32 --vars los_disp_mm gunw_phase_corr gunw_coherence gunw_conncomp
uv run python scripts/cut_fixtures.py --aoi antioquia_aburra --name quake --row 0 --col 0 --size 32 --vars gunw_coherence coherence_coseismic
```

The AOI selects `local_cache/<aoi>/antioquia_sar_cube.zarr`. These commands write
`tests/fixtures/antioquia_aburra/{flood,landslide,quake}.npz` and the corresponding
sidecars. The window arguments are example selections, not measured coverage or
an assurance of valid pixels. Inspect the real coverage and choose another window
if the cutter reports an entirely NaN cut. Bounds are exclusive at row + size and
col + size; the requested square must fit in every selected variable. Existing
fixtures are never overwritten: use another name for a candidate cut.

Keep each `.npz` under 1 MB. The cutter enforces this limit, and the repository
pre-commit hook blocks files over 1000 KB. Reduce the window or selected variables
if necessary. Neither the cutter nor the tests fetch data or alter the cache.

The sidecar records the source cube path, selected variables, window, UTC cut time,
Git commit, and SHA-256 of the archive. `nisar_provenance` contains the full cube
mapping; `nisar_provenance_attribute` preserves the attribute as stored.
`variable_provenance` associates selected variables with their original records,
including the cache builder's differently named provenance keys. Source strings
(including granule IDs and any annotations) are copied verbatim. A `missing`
record remains `missing`. The loader checks the archive digest before loading
arrays with pickle disabled. A missing archive, sidecar, or local cache skips;
a digest mismatch or inconsistent evidence fails.

The current cube permits provenance and SHA checks. It does not yet contain all
inputs needed for the numerical invariants:

- Flood rules require real `hh_db`, `delta_hh_db`, `delta_hv_hh_db`, and `hand_m`
  layers on the same grid, with recorded provenance for each. Raw GCOV power is
  not dB, and slope is not HAND. Rule tests skip until these layers are available.
  If the cache owner adds these real derived layers, cut a candidate with:

  ```sh
  uv run python scripts/cut_fixtures.py --aoi antioquia_aburra --name flood-rules --row 0 --col 0 --size 32 --vars hh_db delta_hh_db delta_hv_hh_db hand_m
  ```

  After human review, use the candidate archive and sidecar as the `flood` fixture
  together. The no-baseline test uses the recorded HH source identifier as its
  observation label; the cut timestamp is not an acquisition date.
- Landslide rules first require the complete nested `landslide` section declared
  by `LANDSLIDE_PARAM_KEYS` in `config/preregistered.yaml`. Missing keys skip with
  `landslide keys not in config/preregistered.yaml yet`. Real independent rates
  must be named `rate_mm_yr_pair_<id>` and matching stable-residual grids
  `stable_residual_mm_yr_pair_<id>`, in mm/year, with per-variable provenance.
  Only stable residual pixels may be finite in those residual grids. Select all
  available independent pairs explicitly with `--vars`; do not repeat a pair or
  use `los_disp_mm` as a rate. Residual grids are flattened only for the rule call.
- Earthquake NumPy rules are pending (03-02). Only provenance and digest checks
  run; the rule placeholder skips without importing Earth Engine.

No thresholds or input layers are supplied by this harness. Flood parameters come
from `load_params("flood")`; landslide parameters use the same frozen YAML loader.

Reviewer commands (no fixtures needed for the first command):

```sh
uv run pytest -q -m "not network and not cache"
uv run pytest -q -m cache
uv run pre-commit run --all-files
```

Every new test has the `cache` marker. With no cache or fixtures, cache tests skip
cleanly, and the offline selection deselects them. The invariant checks use only
loaded observations and their missing-data masks, never expected numeric results.
