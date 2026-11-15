# Real pipeline fixtures

Fixtures are spatial cuts from a real local Zarr cube, with recorded nodata
sentinels converted to NaN in floating arrays and all other values preserved. Each archive must
have a matching `.provenance.json` sidecar. Never create replacement data or edit
values, NaNs, source identifiers, or a recorded `missing` status. Fixtures are
committed only after a human reviews the arrays and their provenance.

From the repository root, after a human builds or downloads the real cache, run:

```sh
uv run python scripts/cut_fixtures.py --aoi mojana --name flood --row 0 --col 0 --size 32 --vars gcov_hhhh_pre gcov_hvhv_pre gcov_hhhh_post gcov_hvhv_post hand_m
uv run python scripts/cut_fixtures.py --aoi antioquia_aburra --name landslide --row 0 --col 0 --size 32 --vars los_disp_mm gunw_phase_corr gunw_coherence gunw_conncomp
```

The unified cache builder (#78) uses short AOI names (`aburra`, `eje_cafetero`,
`mojana`) and writes `local_cache/<aoi>/<aoi>_sar_cube.zarr`. Use `--aoi aburra`
instead of `--aoi antioquia_aburra` in the landslide example for that
builder. The flood tests load `tests/fixtures/mojana/flood.npz`, cut from
`local_cache/mojana/mojana_sar_cube.zarr`. The cutter also accepts the legacy
`local_cache/<aoi>/antioquia_sar_cube.zarr` layout if the current path is absent.
Commands write `tests/fixtures/<aoi>/<name>.npz` and matching sidecars.
The window arguments are example selections, not measured coverage or
an assurance of valid pixels. Inspect the real coverage and choose another window
if the cutter reports an entirely NaN cut. Bounds are exclusive at row + size and
col + size; the requested square must fit in every selected variable. Existing
fixtures are never overwritten: use another name for a candidate cut.

**Sealed earthquake data:** do not cut, load, or inspect an `eje_cafetero`
fixture containing C-pair coherence before the pre-registration freeze (#26)
and the committed `validation/README.md`. The flood workflow uses only La Mojana.

Keep each `.npz` under 1 MB. The cutter enforces this limit, and the repository
pre-commit hook blocks files over 1000 KB. Reduce the window or selected variables
if necessary. Neither the cutter nor the tests fetch data or alter the cache.

The sidecar records the source cube path, selected variables, window, UTC cut time,
Git commit, and SHA-256 of the archive. `nisar_provenance` contains the full cube
mapping; `nisar_provenance_attribute` preserves the attribute as stored.
When the cube has no such attribute, the cutter reads the sibling `manifest.json`
mapping `nisar_granule_provenance` written by the unified builder.
`provenance_source` identifies that file or the cube attribute.
`variable_provenance` associates selected variables with their original records,
preferring exact variable names before legacy provenance aliases. Source strings
(including granule IDs and any annotations) are copied verbatim. A `missing`
record remains `missing`. The loader checks the archive digest before loading
arrays with pickle disabled. A missing archive, sidecar, or local cache skips;
a digest mismatch or inconsistent evidence fails.

`variable_metadata.<variable>.fill_value` records the sentinel used, a list when
multiple sentinels are recorded, or JSON `null` when none is recorded. The cutter
reads `_FillValue`, `missing_value`, and `nodata` on each variable; it never assumes
a sentinel or applies scale/offset transforms. Non-finite sentinel values are
recorded as strings (`nan`, `inf`, `-inf`) for valid JSON. Existing NaNs remain NaN.
Older fixtures without this metadata must be cut again under a new candidate name
and reviewed with their sidecars; do not edit the evidence by hand.

The current cube permits provenance and SHA checks. It does not yet contain all
inputs needed for the numerical invariants:

- Flood checks use the public La Mojana API in
  `gee_math/flood_polarimetric_math.py` (#98). The command above selects real
  pre/post HH/HV linear GCOV power and HAND on the same grid, with provenance
  for every layer. Tests convert power with `power_to_db`; non-positive or
  non-finite power stays NaN. Absolute water counts exclude missing HH or HAND
  and pixels outside the configured HAND domain. Change checks use separate
  Class 1 and Class 2 validity masks; Class 2 additionally needs both HV inputs.
  Rasters permit only the documented class codes and `CLASS_NODATA`.
  A single real observation exercises the no-baseline path, where Class 2 counts,
  denominators, and change rasters remain null, including sensitivity outputs.
  Its recorded HH source identifier is an observation label, not an acquisition
  date. Missing variables skip via `require_variables`; slope never replaces HAND.
- Landslide rules first require the complete nested `landslide` section declared
  by `LANDSLIDE_PARAM_KEYS` in `config/preregistered.yaml`. Missing keys skip with
  `landslide keys not in config/preregistered.yaml yet`. Real independent rates
  must be named `rate_mm_yr_pair_<id>` and matching stable-residual grids
  `stable_residual_mm_yr_pair_<id>`, in mm/year, with per-variable provenance.
  Only stable residual pixels may be finite in those residual grids. Select all
  available independent pairs explicitly with `--vars`; do not repeat a pair or
  use `los_disp_mm` as a rate. Residual grids are flattened only for the rule call.
- Earthquake checks call the offline NumPy functions in
  `gee_math/earthquake_dpm_math.py`. The coherence-loss test needs real
  `coherence_R` and `coherence_C` layers. It checks missing-data propagation and
  the definitional coherence and difference domains. Standardization and DPM
  additionally need real `footprint_coverage`, `landcover`, and `gunw_mask` layers
  with per-variable provenance on the same grid. Cut those explicitly with
  `--vars` when available; otherwise that test skips. Coverage thresholds come
  from `load_quake_prereg()`. Reference pixels exclude vegetation, water, invalid
  GUNW samples, and missing ancillary observations. No layer is substituted.
  Undefined standardization stays NaN, and finite DPM values must be nonnegative.
  These checks use no expected measured results and never initialize Earth Engine.

No thresholds or input layers are supplied by this harness. Flood parameters come
from `load_flood_thresholds("config/preregistered.yaml")`; landslide parameters
use their frozen YAML loader.

Reviewer commands (no fixtures needed for the first command):

```sh
uv run pytest -q -m "not network and not cache"
uv run pytest -q tests/test_pipeline_flood.py -m cache -rs
uv run pre-commit run --all-files
```

Every flood pipeline test has the `cache` marker. With no cache or fixtures, cache tests skip
cleanly, and the offline selection deselects them. The invariant checks use only
loaded observations and their missing-data masks, never expected numeric results.
`tests/test_cut_fixtures.py` runs offline without the `cache` marker. Its
allowlisted literal arrays exist only in temporary Zarr stores and check evidence
serialization, not hazard results.
