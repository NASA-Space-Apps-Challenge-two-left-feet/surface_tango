# Allow-list: the only places resampling or hand-written arrays may appear

| Path | What | Why it is not synthetic data |
|---|---|---|
| `validation/scoring.py` (bootstrap functions) | seeded barrio-block resampling | statistical CI on measured data, seed in `config/preregistered.yaml` |
| `tests/test_*.py` | small hand-written arrays with hand-computed expected values | known-answer logic tests (D15); never reach the app, cache or video |
| `tests/test_cache_release.py` | tiny hand-written byte strings and known-answer manifest verifier cases | isolated temporary-directory tests only; never reach the app or distributed cache |
| `tests/test_fetch_cache.py` | tiny literal bytes, in-memory HTTP responses and temporary staged releases | offline transport, packaging and rollback logic only; never reach the app or distributed cache |
| `tests/test_cut_fixtures.py` | tiny literal arrays in temporary Zarr stores; sentinel-to-NaN and unchanged-value expectations, test-only source and Git labels | known-answer serialization and evidence checks confined to `tmp_path`; never use the real cache or produce observations |
| `tests/test_pipeline_flood.py` | real La Mojana fixture arrays and validity masks only; no generated input arrays or expected measured counts | invariant checks on recorded observations; thresholds come from the frozen configuration and missing inputs skip |
| `tests/test_decision.py` | hand-written envelopes: `value_ha` 10.0, `pixel_count` 1000, `valid_pixel_count` 1000, `pixel_area_m2` 100.0, quake windows 100 and 250 and 1000 valid pixels, a retained rate 80, a population value 10 | known-answer posture tests; the numbers are not observations and never enter the cache, a report, or the video |
| `tests/test_picacha_window.py` | one hand-written 4 by 4 grid, values 0 through 15. The box [1, 1, 3, 3] must return [[5, 6], [9, 10]] | known-answer native-grid window. The cells are not observations and never enter the cache |
| `tests/test_flood_display.py` | one hand-written 5 by 5 mask and HAND grid. Scale 10. Low HAND 1 maps to RGB (26, 64, 133) alpha 140. High HAND 9 maps to (168, 203, 235) alpha 140. Border RGB (4, 30, 90) alpha 235. Missing HAND RGB (37, 99, 168) alpha 170. A false cell stays alpha 0 | known-answer display arithmetic for the open-water overlay. Not a depth survey and never a cache write |
| `tests/test_context_basemap.py` | one 2 by 2 DN stack. Display clip 2500. DN 0 maps to RGB 0 alpha 255. DN 1000 maps to 102 because `1000/2500*255 = 102`. DN 2500 maps to 255. A NaN maps to alpha 0. A coarse pixel RGB (1, 1, 1) stays where the fine layer is transparent. A fine pixel RGB (9, 9, 9) replaces only its own cell. Padding 0.1 on `[0, 0, 1, 1]` is `[-0.1, -0.1, 1.1, 1.1]`. Posting 111320 m on that box is one pixel | known-answer display arithmetic for the context photograph. Not a reflectance measurement and never a cache write |
| `tests/test_quake_coverage.py` | one 2 by 2 coherence grid. A measured 0 stays 0 and stays RGB (35, 30, 75) alpha 255. A NaN stays NaN and becomes the no-data hatch inside the frame. Coherence 0.5 maps to RGB (145, 122, 147) because `35+0.5*220=145`, `30+0.5*185` truncates to 122, and `75+0.5*145` truncates to 147. Open water value 1 stays RGB (53, 196, 181) alpha 200. A finite dry 0 stays alpha 0. Counts 4 of 8 are only a gate fixture | known-answer display arithmetic and an AOI-ownership gate. The cells are not observations and never enter the cache |

## Issue #18: known-answer scoring fixtures

All inputs below are hand-written logic fixtures in `tests/test_scoring.py`.
They are not observations, measured results, or cache contents; none may enter
application output, reports of real damage, or video. No source granules apply.
The numerical values below are exact test arithmetic unless explicitly rounded.

| Fixture | Inputs and expected arithmetic |
|---|---|
| Percentiles | `[30, 10, 20, 20]` maps to `[1, 0, 0.5, 0.5]`; tied average ranks use `(rank - 1)/(n - 1)`. A singleton and constant vectors use `0.5`. |
| Ranking | IDs `a,b,c`, DPM `3,1,2`, population `10,30,20`, distance `0,20,10`, weight `0.25`: baseline scores `0,1.25,0.5625`; radar scores `0,0,0.28125`. Score ties use ascending ID. Negative median Z remains valid. |
| k | Test fraction `0.1`, minimum `5`: sizes `1,30,50,51,100` give `1,5,5,6,10`. Round up fractional counts, then enforce minimum and cap at available units. These conventions are explicit because the design does not specify ties or rounding. |
| Precision | Labels `true,false,true,true`: top two yield `1/2`; all four yield `3/4`. Unknown labels are rejected. |
| Wilson | Four trials, successes `0,2,4`. With `z = 1.959963984540054`, denominator `1 + z²/4`, center `(p + z²/8)/denominator`, radius `z*sqrt(p*(1-p)/4 + z²/64)/denominator`: rounded intervals `[0,0.4898908365]`, `[0.1500389892,0.8499610108]`, `[0.5101091635,1]`. |
| Informative | Boolean label lists exercise unit, positive-count, and inclusive prevalence boundaries. Empty or absent ground truth cannot pass. |
| Pooled excess | Built-up blocks `[2,4,6]`, `[10]`; reference blocks `[0]`, `[2]`: pooled medians `5` and `1`, so excess is `4`. |
| Paired bootstrap | Barrio a: negative, C built `[2]`, reference `[0]`, K built `[1]`, reference `[0]`; barrio b: positive, C built `[4]`, reference `[0]`, K built `[1]`, reference `[0]`. Equal population and distance. Stable original IDs `a,b` precede occurrence suffixes in tie-breaking. Two seed-zero draws are `(b,b)`, `(a,b)`. Recomputed precision differences are `0,1`, C excesses `4,3`, K excesses `1,1`, adjusted excesses `3,2`. Linear percentile interpolation gives the asserted endpoints. Two draws test arithmetic only, not scientific adequacy. |
| Draw-order regression | All permutations of samples `a,b`, `a,a,b`, and `a,b,b` retain the same statistics; the precision difference is `1` in each sample because the tied baseline selects original ID `a` and radar selects `b`. Repeated barrio occurrences are retained. |
| Claim rule | Explicit intervals cover positive gain, loss, intervals touching zero, missing/post-event control, and an uninformative card. A negative precision difference cannot establish a win. |
| Invalid inputs | Empty/nonfinite vectors, mismatched units, duplicate IDs, unknown labels, impossible counts and undefined bootstrap statistics fail explicitly. |

## Scoring API boundaries

`validation/scoring.py` uses only the Python standard library. Callers must pass
frozen values from `config/preregistered.yaml`; the module neither reads nor edits
that file. Upstream code must select eligible barrios, count exclusions, mask
invalid pixels, and provide named source provenance before invoking these functions.

`block_bootstrap` draws whole barrio objects with replacement using a local seeded
RNG. Its callback receives all C/K observations for the same draw, preserves repeated
occurrences with stable original-ID tie-breaking, recomputes the rankings, and returns named paired statistics. Undefined
replicates fail rather than being discarded. The test callback demonstrates this
contract; the production scorecard assembly is part of issue #32. Confidence intervals
use linear empirical percentile interpolation. Wilson intervals are computed separately
from successes and the top-k denominator. An interval containing zero does not prove
absence of an effect; the claim rule uses positive C and C-minus-pre-event-K bounds.

## Issue #33: known-answer landslide analyst fixtures

All inputs below are hand-written logic fixtures in `tests/test_landslide_geology.py`,
`tests/test_landslide_geomorphology.py`, `tests/test_landslide_hydrogeology.py`, and
`tests/test_landslide_analysts.py`. They are not observations, measured results, or
cache contents. None may enter application output, reports of real AOIs, or video.
No source granules apply. The numerical values are exact test arithmetic.

| Fixture | Inputs and expected arithmetic |
|---|---|
| Engineering class | Stems match in order colluvium, rock, soil, so `arenisca` is rock and `arcilla aluvial` is soil. A blank or unrecognized label stays unclassified. |
| Dominant unit | Counts `5, 5, missing, 9` select the count-9 unit. A tie of count 5 selects the smaller name. Every missing count returns no dominant unit. |
| Structures | One true fault, one false contact, one missing flag: faults 1, contacts 0, missing 1. A false flag is not an intersection. |
| Slope summary | Finite samples `0, 10, 20, 30` (one NaN excluded from the percentiles, kept in `n_pixels`). Linear index `(n-1)*p`: median 15, p05 1.5, p95 28.5. |
| Horn derivatives | 3×3 elevation `[[10,10,10],[10,20,30],[10,20,30]]`, cell 10 m. `p=0.75`, `q=-0.5`, `r=0`, `t=-0.1`, `s=0.05`. Slope `degrees(atan(hypot(p,q)))` = 42.03111377419729. Aspect `degrees(atan2(-p,-q)) mod 360` = 303.69006752597977. Profile curvature 0.031523877038014105 per metre. Plan curvature 0.025601547518087502 per metre. Edges and any window with a non-finite neighbor stay NaN. A flat cell has slope 0 and NaN aspect. Relative relief is max−min = 20 m. |
| Photogrammetry | `(0,0)` to `(3,4)` is 5 m. Two such steps sum to 10 m. A missing point leaves the path missing. Control `(0,0),(10,0)` onto `(1,2),(12,2)` shifts by `(1.5, 2)` with RMSE 0.5 m. Gully 10 m over 365.25 days is 10 m/yr. A non-positive interval is missing. Sign agreement is undefined at zero or when either side is missing. |
| Green-Ampt | `Δθ=0.2`, `ψ=0.5` m, `F=0.1` m, `K=1e-5` m/s gives `t=3068.528194400546` s and `z_f=0.5` m. Rainfall cap 0.02 m gives `F=0.02` m and `z_f=0.1` m. Rainfall 0 m is a real zero. A missing soil term leaves both depths null. |
| Effective stress | `Δσ' = -9.81 * Δh`. A 2 m rise is -19.62 kPa. A 0 m rise is 0. A missing rise is null. |
| SPT-N | Wolff / Peck: `φ = 27.1 + 0.3 N − 0.00054 N²`. `N=10` is 30.046°. `N=0` is 27.1°. A negative or missing N is null. Stroud: `cu = f1 * N` with `f1` required. `N=8`, `f1=4.5` is 36 kPa. |
| Built-up load | Fraction 0.25 times 20 kPa is 5 kPa. A fraction outside `[0, 1]` is null. |
| Culmann | `β=60°`, `φ=30°`, `c=10` kPa, `γ=20` kN/m³. `sin β cos φ = 0.75`. `H_c = 11.196152422706637` m. `H=5` m gives FS 2.2392304845413276. Surcharge 10 kPa gives FS 2.035664076855752. `β≤φ` withholds the height. |
