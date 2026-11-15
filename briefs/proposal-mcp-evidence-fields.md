# Proposal: evidence-bearing MCP flood and landslide responses

Owner: `alicealanapineda-byte` (MCP/agents lane). This is a proposed output
contract for owner review, not an implemented adapter or an approved science
change. The only deliverable of this branch is this proposal.

## Verification basis and scope

Reviewed the worktree created from `origin/main` at
`134905df267749a9b208d654bd04052a491f4fc3`, after #103, against `AGENTS.md`.
The branch ref and locally recorded `origin/main` ref identify the same commit.
The local `main` checkout is older; it is not the basis of this review.
Git is unavailable on PATH, so no fresh fetch, `make sync`, or Git-based diff
was run. These findings describe the supplied main snapshot, not an independently
refreshed remote. No Earth Engine calls or hazard computations were run.

Code inspected:

- `mcp_servers/gee_fusion_mcp.py`: both tool bodies and the shared reduction helper.
- `mcp_servers/cache_guard.py`: `cached_output`, `request_key`, and
  `with_offline_zarr_fallback` for the actual outward envelope.
- `gee_math/flood_polarimetric_math.py`: #98's dataclasses, `class_masks`,
  `class_raster_from_db`, `classify_stack`, sensitivity helpers, ancillary fetches,
  and `_write_provenance`.
- `gee_math/landslide_insar_math.py`: `correct_pair`, `noise_floor`,
  `_independent`, `null_motion_sentence`, `_prefer_provisional`, and the separate
  retained GEE entrypoint `compute_landslide_insar_kinematics`.
- `config/bailasar.yaml`, `config/preregistered.yaml`, README Status table,
  `status/aburra-flood.md`, existing hazard tests, and hook configuration.

The earlier adapter and review records were used only to identify issues to
recheck. Their claims of fixes and test results are not evidence of main's
behavior. The checklist below preserves the findings so this document remains
usable after the reference directory is removed.

Current main imports hazard functions inside each tool call. The flood tool
still requests `compute_flood_scattering_decomposition`, which #98 no longer
defines: the guard returns an error instead of crashing server import. Landslide
still calls the legacy single-pair GEE image graph, not the numpy noise-floor
pipeline. Neither body currently supplies the proposed evidence contract.

## Shared outward response contract

Keep the cache guard's canonical field `state`; do not introduce a competing
`status` panel field. Return an envelope with the following required fields on
every outcome, including errors and cache misses. Domain evidence belongs in
`data`, while `provenance` describes the execution and sources.

| Field | Required meaning |
| --- | --- |
| `state` | Exactly `live`, `cached`, `not cached`, `gate result`, or `error`. |
| `tool`, `domain` | Requested tool name and `flood` or `landslide`. |
| `reason` | Human-readable explanation; required for withheld products, gates, misses, and errors; null on uncomplicated success. |
| `calibrated` | Always `False` in Python, serialized as JSON `false`, for this proposed integration. A separate CLI calibration artifact does not calibrate this MCP adapter. |
| `uncalibrated` | Explicit list of parameter identifiers used, as specified per tool below; never an unsupported claim of calibration. |
| `data` | The per-tool fields below, with nulls and reasons for missing evidence. Never replace missing values with zero. |
| `provenance` | Source records, execution identity, request identity, configuration identities, and cache origin where applicable. |
| `unavailable` | Map from field name to an object containing `availability: "unavailable"` and `reason`; also set the corresponding data field to null. |
| `error` | Null normally; sanitized code/message and `missing_keys` where relevant on error. Never include credential-bearing URLs or secrets. |

State selection is independent of the presence of optional renderers:

- `live`: a completed, evidence-valid live result. Optional unavailable rendering
  does not erase valid measurements.
- `cached`: an exact-request, real pre-staged response that passes the same
  domain evidence validation as live output.
- `gate result`: a completed scientific/evidence gate withholding some or all
  products, including measured absence of supported motion, too few independent
  pairs, or an unacceptable flood baseline. Keep valid partial evidence visible.
  Record `provenance.execution_mode` as live or cached for a cached gate result.
- `not cached`: offline/timeout fallback has no matching evidence-valid record.
  An invalid legacy cache is a miss with an explicit reason, not usable science.
- `error`: invalid inputs/configuration, unsupported adapter integration, or a
  failed operation. An exception must not become a measured negative result.

Each numerical evidence object carries `measurement: "measured"` or `"estimate"`,
unit, producing command/tool invocation, source references, and its denominator.
Missing numerical values are null with `measurement: "missing"` and a reason.
Serialize non-finite values as null; retain raster masks/NaN internally. Agents
render placeholders from these fields and never calculate replacement numbers.

`provenance` must include a reproducible command or tool invocation with public
arguments, git SHA, measurement time, bbox, grid/CRS/transform, configuration
paths and content identities, and per-source records. Source records distinguish
requested, executed, failed, and skipped reads. Only completed reads appear in
`ancillary_reads`; do not claim a planned read occurred before an early gate.
For cache output retain original measurement provenance plus `source`,
`granule_ids`, `cache_build_time`, tool name and request key. A cache path alone
is not a source granule identity.

For every GEE read record the collection/asset ID, selected image IDs where
applicable, bands, acquisition/coverage dates, query start and exclusive end,
and actual read time. Static terrain products need their version and documented
coverage date, or explicit null plus reason if no acquisition date is exposed;
do not invent a date or confuse access time with acquisition time.

## `analyze_flood_inundation`

### Inputs and science boundary

Replace the obsolete decomposition call with an owner-integrated path to #98's
dated-stack API. A pre/post URL pair or caller baseline boolean cannot establish
the measured dry baseline. Validate actual usable dates, common stack identity,
aligned analysis grid, source quality masks, linear-power units, and the #98
usable-date gate before exposing change classes. Use `choose_baseline` through
`classify_stack`; preserve its reason and selected reference date.

Class 1 is the implemented HH-change/HAND rule. Class 2 uses HH change and
change in the HV/HH ratio in dB with HAND eligibility. Do not describe the result
as a Pauli/Freeman decomposition or a measured double-bounce power fraction.
Sentinel-1 is a separate comparison, not an extra classifier requirement.
Retain #98's event-scope limitation: seasonal water and breach water are not
separated; this is not a reconstruction of the earlier breach event.

`uncalibrated` must include the configured `labels.uncalibrated` list, which
currently names `open_water_abs_hh_db`, `class1_delta_hh_db_max`,
`class2_delta_hh_db_min`, `class2_delta_hv_hh_db_abs_max`, and `hand_max_m`.
Also disclose the applied baseline rule (`flood.no_baseline_relative_gap`),
sensitivity settings (`flood.sensitivity.db_step`, `flood.sensitivity.hand_m`),
and any comparison threshold borrowed for Sentinel-1 as uncalibrated method
parameters; do not silently omit them because the current labels list is shorter.
Read frozen science settings from `config/preregistered.yaml`; do not change it.

### Required data fields

| Field | Contents and withholding rule |
| --- | --- |
| `baseline` | `accepted`, `reason`, `reference_date`, wet/dry dates, wet/dry fractions with their original counts/denominators, relative gap, and applied rule/config identity. |
| `dates` | Dated result objects with contributing granule IDs and GCS/source paths, including the baseline source dates. Identify the selected display date explicitly. |
| `area_evidence.water_extent_ha` | Dated absolute extent: `value_ha`, `pixel_count = n_water`, `valid_pixel_count = n_valid`, pixel area/grid evidence and source IDs. |
| `area_evidence.open_water_flood_ha` | Class 1: `value_ha`, `pixel_count = n_class1`, `valid_pixel_count = n_valid_class1`, reference/target dates and sources. |
| `area_evidence.subcanopy_double_bounce_flood_ha` | Class 2: `value_ha`, `pixel_count = n_class2`, `valid_pixel_count = n_valid_class2`, reference/target dates and sources; label it as the uncalibrated class proxy. |
| `area_evidence.total_inundated_ha` | Only a supported union of change classes. Include component counts and denominators next to the value, union support/mask definition, grid and source evidence. Otherwise null plus reason. |
| `alert_level`, `alert_reason`, `alert_policy` | Policy-based alert on the explicitly identified total-change-area metric, or null plus reason when that metric is unavailable. Record required configuration key names and applied config identity. Missing evidence never implies GREEN. |
| `gee_xyz_tile_url`, `diagnostic_rgb_tile_url`, `hotspot_coordinates` | Explicit null and corresponding unavailable entries until separately implemented and evidence-validated. Never use the AOI centroid as an observed hotspot. |
| `key_quantitative_metrics` | Optional compatibility view referencing the evidence objects, never bare hectares without their denominators. Unsupported legacy percentiles/fraction bands are null with reasons. |
| `sentinel1_comparison`, `rainfall` | Actual separately computed comparison/context with counts and source/date evidence, or null plus reason. Do not assert either was read merely because helper functions exist. |
| `physical_radar_driver` | Qualitative description of the implemented rules, their uncalibrated status, and baseline limitations; no unsourced numerical narrative. |

Every area evidence object must additionally contain `pixel_area_m2` (or a
reference to verified per-cell area weights), `measurement`, `command`,
`source_ids`, `sensitivity_range`, `sensitivity_reason`, and
`sensitivity_scenarios`. A sensitivity endpoint is itself an area evidence
object with scenario name, pixel count, valid-pixel denominator and sources.
A range is a parameter sensitivity envelope, not a confidence interval.

When all required scenarios are available, use #98's configured sweep and return
its minimum/maximum and supporting scenario rows. If any required evidence is
unavailable, return `sensitivity_range: null` with the precise reason, including
whether the sweep is incomplete or not serialized. Do not substitute a nominal
area for an uncertainty range. Do not label a partial sweep complete.

Use positive valid-pixel support to distinguish measured zero from no data.
Missing HV must not erase a known Class 1 detection; it leaves Class 2
unresolved. Conversely, Class 2 missingness must not become a non-flood label.
The current #98 raster writer initializes valid Class 1 support to the neutral
class even where Class 2 cannot be evaluated; preserve a separate Class 2
validity mask before any downstream interpretation of that raster.

If baseline rejection or no wet-water support prevents change classification,
return a gate result with the module's reason: expose only valid dated absolute
water extent, with change areas and alerts null. The reference date itself has
no change classification. Do not sum areas across incompatible supports or
overlapping class rules. If reporting a combined total over differing valid
domains, disclose the component denominators and the verified union support;
withhold a full-coverage total when missing Class 2 evidence prevents it.

### Capabilities actually exposed by #98

| Capability | Verified API boundary and required unavailable representation |
| --- | --- |
| GEE class tile renderer | Absent. `write_rasters`/`write_class_geotiff` write local rasters; they do not return a GEE tile. `gee_xyz_tile_url = null`; unavailable reason identifies the missing renderer. |
| GEE RGB tile renderer | Absent. `diagnostic_rgb_tile_url = null`; unavailable reason identifies the missing renderer and obsolete decomposition bands. |
| Hotspot reduction | Absent from #98. `hotspot_coordinates = null`; unavailable reason identifies the missing reduction. The MCP legacy helper is not a #98 API. |
| Sensitivity rows in serialized provenance | `_write_provenance` omits them. Set `serialized_evidence.sensitivity_rows = null` with an unavailable reason when consuming that file alone. `SensitivityCount`, `DateResult.sensitivity`, `_sensitivity_rows`, `iter_sensitivity`, and report rendering do expose them in memory/report form; an integrated adapter can serialize real rows explicitly. |
| Pixel area in serialized provenance | `_write_provenance` omits it. Set `serialized_evidence.pixel_area_m2 = null` with an unavailable reason for that file alone. `Analysis.pixel_area_m2` and `AnalysisGrid.pixel_area_m2` expose it in memory. Without a verified grid/area artifact, withhold hectares; do not guess pixel area from counts or prose. |

`serialized_evidence` is a proposed data object describing the supplied cache
artifact, not a claim that in-memory #98 analysis lacks those quantities.
An adapter may populate it only from an actual evidence-bearing artifact.

Flood provenance must connect each dated GCOV granule ID to its original source
and any staged HH/HV GCS paths. Record `MERIT/Hydro/v1_0_1`, band `hnd`, version,
coverage-date availability, AOI and sampling grid for HAND reads. If rainfall is
computed, record `UCSB-CHG/CHIRPS/DAILY`, selected dates/images, actual aggregation
window and completeness. For Sentinel-1 comparison record `COPERNICUS/S1_GRD`,
actual scene IDs and date bounds. FABDEM is not used by #98 flood classification;
do not claim a FABDEM read for this tool.

## `analyze_landslide_kinematics`

### Verdict precedes every motion product

The retained GEE entrypoint returns a single-pair image and has no noise-floor
verdict. Its existence is not evidence that the gated numpy pipeline is wired
into MCP. Owner integration must supply validated per-pair inputs and execute
the verdict before velocity summaries, alerts, motion tiles, diagnostic motion
RGB, hazard-index products, or motion hotspots are generated or returned.

Use real acquisition identities, not arbitrary `pair_id` labels, to establish
independence. Reject duplicate source rasters and duplicate acquisition pairs,
including renamed paths or urgent-response/provisional copies of the same
pair. Validate source identity using source granule/acquisition metadata and
artifact identities; string-unique paths alone are insufficient. Distinct pairs
sharing an acquisition do not provide independent support. Unknown identities
cannot establish independence. Return a sanitized error for falsely duplicated
input evidence; return a gate result for a valid but insufficient pair set.

Validate common grids, signed displacement/rate units, real temporal baselines,
stable-pixel residuals and final eligibility masks before the verdict. Apply
coherence, connected-component, terrain/projection, layover/shadow and missing
data restrictions to the pixels being tested. Summary support must equal the
exported retained support; later display masks must not turn a reported motion
finding into an empty product without an explicit explanation.

Main's numpy `noise_floor` compares LOS displacement with per-pair residual RMS
in millimetres, then retains signed downslope rates with independent sign
support. This is distinct from the rate-RMS implementation described in the
earlier adapter and from the wording in `preregistered.yaml`. The owner must
resolve that scientific contract with the hazard/config owners; this proposal
does not silently switch tests or edit frozen settings. Never compare mm/yr
directly with mm. If a rate-based test is approved, transform residuals using
the real per-pair baseline and label that test and its units explicitly.

`uncalibrated` must explicitly list the applied, unvalidated parameter
identifiers: `landslide.noise_floor.min_pairs`,
`landslide.noise_floor.require_sign_agreement`, stable-mask slope criterion,
coherence cutoff, minimum projection cosine, any assumed incidence/heading,
and any hazard-index normalization/weights used. Identify legacy constants by
their actual symbol/expression when no config key exists; do not invent a claim
that main already loads them from config. Separate those assumptions from
measured geometry, residuals and acquisition baselines. The owner must obtain
an approved configuration source for scientific parameters before enabling the
products; alert/display policy belongs in operational config.

For explicit serialization, use the config identifiers above and these source
identifiers when their corresponding legacy assumptions are used:
`VALLEY_FLOOR_MAX_SLOPE_DEG`, `MIN_ABS_COS_XI`, `WAVELENGTH_M`,
`compute_landslide_insar_kinematics.inc_angle_deg`,
`compute_landslide_insar_kinematics.sat_heading_deg`,
`compute_landslide_insar_kinematics.valid_insar_mask`,
`compute_landslide_insar_kinematics.stable_mask`,
`compute_landslide_insar_kinematics.projection_img.slope_mask`,
`compute_landslide_insar_kinematics.projection_img.reg_cos_xi`, and
`compute_landslide_insar_kinematics.hklsi.normalization_and_weights`.
The dotted function/expression identifiers locate assumptions in the source;
they are not existing configuration keys. Return only the assumptions actually
used by the approved path, with their source/config mapping, and include the
operational alert-policy keys when an alert is emitted.

### Required data fields and branches

| Field | Required contents |
| --- | --- |
| `noise_floor_verdict` | Structured `outcome`, `evidence_status`, `text`, `reason`, test name/units, per-pair residual RMS with stable-pixel counts, pair baselines, finite-RMS pair count, independent supporting pair identities, eligible-pixel count, retained-pixel count, sign-support counts, and source references. Aggregate floor alone is insufficient. |
| `pairs` | For every considered pair: granule/source IDs, reference/secondary acquisition IDs and dates, staged phase/ionosphere/coherence/component paths, any rate/residual paths, artifact identities, grid and units, eligibility/exclusion reason. |
| `key_quantitative_metrics` | Supported displacement/rate/terrain/rainfall summaries with per-band valid-pixel counts, units, sources and producing invocation. Motion summaries use only verdict-retained pixels; unavailable statistics are null, never default zero. |
| `area_evidence` | Null with reason if no area is computed. Any future retained/eligible area must carry its own pixel count, valid-pixel denominator, grid/pixel area, source IDs and sensitivity evidence object, following the flood area contract. |
| `sensitivity_range`, `sensitivity_reason`, `sensitivity_scenarios` | Null, explicit reason, and null until a justified landslide sensitivity sweep exists. Main's GEE and numpy motion APIs do not return that sweep; do not call residual RMS a sensitivity interval. |
| `alert_level`, `alert_reason`, `alert_policy` | Only after a supported motion verdict and a valid configured metric. Identify whether policy uses signed or absolute retained rate and its units. Otherwise null with reason. |
| `gee_xyz_tile_url`, `diagnostic_rgb_tile_url`, `hotspot_coordinates` | Only verified retained-support products after the verdict, or null with unavailable reasons. No AOI-center hotspot substitution. |
| `rainfall` | Actual start, exclusive end, duration, completeness, valid-pixel count and aggregation unit; validate the required duration before using `rain_15d_mm`, or expose a duration-neutral field and its actual window. |
| `physical_radar_driver` | Qualitative account matching the approved test and projection; disclose uncalibrated assumptions without asserting unsupported motion. |

Required verdict branches:

- Missing/invalid residual evidence: `evidence_status: "missing"`, gate result
  with text explaining missing stable residuals; floor and motion products null.
  Do not say no motion was measured.
- Insufficient independent evidence: gate result with the exact phrase
  **"too few independent pairs"**, actual supported pair count and the configured
  requirement; motion summaries, alerts and motion products null. This includes
  otherwise valid pairs with shared/unknown acquisition identities.
- Adequate evidence with no retained support: measured gate result with
  `no motion detected above {noise_floor_mm} mm ({n_pairs} pairs)` only when
  that displacement-based test and its denominators are actually available.
  Include eligible support and independent-pair evidence; never call this a cache
  miss. Use corresponding rate units if the approved test is rate-based.
- Supported motion: `live` or validated `cached`; retain signed rates and export
  only the verdict's support. Missing optional rain/rendering remains explicit.

Landslide source evidence must include all GUNW granule IDs and staged GCS paths,
plus actual ancillary reads of `projects/sat-io/open-datasets/FABDEM` with selected
terrain asset identities/version/date availability and `UCSB-CHG/CHIRPS/DAILY`
with actual start/end dates and selected rainfall images. MERIT is not used by
the present landslide entrypoint; do not list it as read. An early gate includes
only ancillary reads that actually executed.

## Required operational policy, without proposed values

Propose these required keys in `config/bailasar.yaml`:

- `hazard_tools.flood.alert.red_above`
- `hazard_tools.flood.alert.orange_above`
- `hazard_tools.flood.alert.yellow_above`
- `hazard_tools.landslide.alert.red_above`
- `hazard_tools.landslide.alert.orange_above`
- `hazard_tools.landslide.alert.yellow_above`

Flood alert keys apply to supported total change area in hectares; landslide
keys apply to the documented retained-rate statistic in mm/yr. Validate type,
finiteness, ordering and units, and identify strict comparison semantics in
`alert_policy`. Missing required keys return `state: "error"` with their dotted
names and no default thresholds. The shipped config has no `hazard_tools` block.
No values are proposed here and no config files are changed.

Require visualization/hotspot keys only for capabilities actually enabled:
`hazard_tools.landslide.velocity_viz.min`, `.max`,
`hazard_tools.landslide.diagnostic_viz.min`, `.max`, and
`hazard_tools.landslide.hotspot_min` if those operations remain. Flood's absent
renderers/reducer must not require unused flood display/hotspot keys. Display
policy must not silently redefine scientific eligibility or verdict support.

## Offline and timeout parity

Preserve #103's exact-request cache lookup, sanitized errors, bounded worker
behavior and configured breaker budgets. Add domain validation after every
cache lookup and before every output, including offline mode, timeout and busy
worker fallback. Validate the nested `data` envelope rather than expecting the
legacy flat `status` fields used by the earlier adapter.

Flood cached products need baseline decisions, dated class-specific counts,
pixel area/grid evidence, calibration labels, sources and explicit sensitivity
availability. Landslide cached products need the same independent-pair verdict,
final support and source identities as live products. Retain original provenance
and execution mode for cached gate results. Reject stale schema/config/method
identities where they change the interpretation of evidence. Missing optional
sensitivity rows may be declared unavailable; missing area conversion evidence
cannot support hectares. Never reconstruct measurements from labels, legacy
hardcoded classifications, or the cache directory name.

## Review findings checked against main

Each item is a recheck, not a claim that the earlier branch's fixes were merged.
Repeated findings in the review records are consolidated with their origins.

- [ ] **Still applies — operational settings may change.** The operational
  comment in `config/bailasar.yaml` confirms the rule. Neither tool reads alert
  policy from it; required keys and provenance must replace hardcoded policy.
- [ ] **Still applies — secret findings cannot be self-silenced.** `AGENTS.md`
  and `.pre-commit-config.yaml` retain the secret-scan/baseline rule. No baseline
  change or secret exception is proposed.
- [ ] **Still applies — different pair labels can duplicate raster evidence.**
  The GEE tool accepts a single set of rasters and performs no source-identity
  rejection. Numpy `_independent` checks date disjointness and CLI
  `_prefer_provisional` removes some duplicate products, but neither provides
  the proposed general MCP duplicate-source validation.
- [ ] **Still applies — arbitrary rainfall windows labeled `rain_15d_mm`.**
  The GEE entrypoint accepts caller dates and renames their sum without checking
  duration; the MCP signature forwards those dates unchanged.
- [ ] **Not applicable — rate RMS reported as mm in the earlier implementation.**
  Main's `noise_floor` consumes displacement residual RMS in mm and its verdict
  uses mm correctly. The reviewed rate-RMS implementation is absent. Preserve
  unit correctness when integrating rather than changing current text to mm/yr
  without changing the actual test.
- [ ] **Fixed by #103 — shared tool wrapping and budget handling foundation.**
  Both MCP tools use `with_offline_zarr_fallback()`; the guard reads configured
  per-tool/default budgets and handles timeout, offline and busy fallback. Hazard
  budgets remain on the documented default until measured; this is not evidence
  that every hazard budget has been measured or that domain checks exist.
- [ ] **Not applicable — early gates falsely list executed FABDEM/CHIRPS reads.**
  The reviewed `ancillary_reads` construction and early-gate adapter are absent
  on main. Current MCP provenance is missing instead; executed-read tracking
  remains a requirement of this proposal.
- [ ] **Fixed by #103 — successful landslide response lacks a panel state.**
  The body is still flat, but the outward guard wraps it in
  `{"state": "live", "data": ...}`. Use `state`, not the review's suggested
  `status: "live"`; that old suggestion does not match the current envelope.
- [ ] **Still applies — flood fallback bypasses domain evidence checks.**
  `cached_output` validates request identity and basic provenance only; it does
  not validate baseline, masks, denominators or sensitivity. Main no longer
  generates legacy classifications in fallback, but can return an inadequately
  evidenced staged `data` payload. Reject such records rather than trusting them.
- [ ] **Not applicable — unused visualization/hotspot settings are mandatory.**
  Main has no `_operational_settings` reader and no such mandatory key list.
  It hardcodes display/alert settings instead. Require only settings actually
  used by the future integration; do not copy the old unused requirements.
- [ ] **Still applies — frozen parameters and hash ownership.** `AGENTS.md`
  and `config/preregistered.yaml` state the pre-registration rule. This proposal
  must not alter frozen science settings; operational alerts belong elsewhere.
- [ ] **Still applies — README/KB must follow method/capability changes.**
  README's MCP row already acknowledges #103 and the broken flood wiring, so
  that disclosure exists. `status/aburra-flood.md` remains a blank template,
  and the proposed noise-floor KB note is absent. The earlier claimed adapter
  removals are not on main. Any future integration still needs matching MCP
  Status rows, method documentation/KB and migration notes in its own scope.
- [ ] **Still applies — hardcoded alert/visualization thresholds.** Both tool
  bodies contain literal alert cutoffs and rendering ranges; neither uses
  required `hazard_tools` policy. The earlier review summary's claimed fix is
  not present on main.
- [ ] **Still applies — Class 1 and missing HV handling, in part.** #98's
  `class_masks` already keeps Class 1 independent of HV, so that narrow loss
  finding does not apply to its count API. However, `class_raster_from_db` marks
  all `valid1` pixels neutral before class assignment, including unresolved
  Class 2 support. MCP also still targets the absent legacy flood API. Preserve
  Class 1 and expose Class 2 validity separately in the integrated contract.
- [ ] **Still applies — landslide bypasses the noise-floor verdict.** MCP calls
  the retained GEE image function and renders/alerts directly. Numpy `noise_floor`
  exists but is not called by that route; no independent-pair verdict is returned.
- [ ] **Still applies — calibration labels and obsolete physical explanation.**
  Neither current body returns `calibrated`/`uncalibrated`. Flood text still
  claims decomposition/double-bounce power behavior that #98's API does not expose.
- [ ] **Still applies — hectares lack evidence.** The legacy flood body reduces
  area without class-specific valid-pixel denominators/source IDs, defaults
  absent totals to zero, and cannot run against #98. #98 in-memory counts exist,
  but their presence does not repair the MCP output.
- [ ] **Still applies — missing residual wording.** `null_motion_sentence`
  renders a missing floor as `no motion detected above missing mm`; empty or
  insufficient evidence can therefore read as measured absence. Explicit
  missing-evidence and insufficient-independent-pair branches are required.
- [ ] **Not applicable — earlier breaking schema declaration claimed prepared.**
  No such adapter/schema change or migration note is on main; the status file
  is a blank template. A future tool input/output change needs the repository's
  breaking-change declaration and consumer migration review. This document
  changes no runtime schema and creates no PR metadata.
- [ ] **Not applicable — copied edge-case tests/allow-list additions claimed done.**
  The named `test_mcp_hazard_rules.py`, `test_flood_edge_cases.py` and copied
  landslide edge-case suite are absent on main. Existing hazard logic tests
  do not establish the proposed MCP envelope/cache evidence behavior. No earlier
  test count or claimed Ruff result is adopted as validation of this proposal.
- [ ] **Still applies — offline/timeout landslide bypasses independent-pair gating.**
  The shared cache guard never inspects a verdict inside cached `data`; returning
  a real request-matched payload alone does not establish scientific validity.
- [ ] **Still applies — verdict must use final eligible pixels.** The earlier
  specific post-verdict mask sequence is absent, and numpy `correct_pair` masks
  eligibility before `noise_floor`. However, the MCP GEE route has no verdict
  at all. Its future gate must use the final exported support, including
  coherence and slope restrictions; do not assume the offline fix covers it.
- [ ] **Not applicable — measured no-motion result mapped to `status: "not cached"`.**
  That specific mapping was in the earlier adapter, which is absent. Main does
  not return a landslide no-motion verdict through MCP. The proposed integration
  must map valid no-motion findings to `state: "gate result"`.
- [ ] **Still applies — FABDEM/CHIRPS IDs and dates missing in MCP provenance.**
  They appear as source literals in the GEE math, but the live MCP response
  includes neither read records nor rainfall dates. The guard's generic cache
  provenance checks do not require those ancillary details.
- [ ] **Still applies — flood sensitivity range absent from MCP hectares.**
  The current tool body has no sweep/range. #98 has in-memory sensitivity rows
  and report ranges, but `_write_provenance` omits rows and pixel area. Integrate
  real rows or declare null plus reason; never infer a range from one area.

Additional compatibility observations from the earlier adapter: #103 already
moved EE initialization to call time, deferred hazard imports, and removed the
obsolete `timeout_sec` decorator argument. Those startup/API fixes do not merge
the reference adapter's scientific changes. Its flat `status` evidence wrappers
must not be transplanted onto the nested `state`/`data` contract.

## Owner acceptance criteria for a later implementation

- Verify all outcome branches use the canonical envelope and explicit missing
  fields; test the real decorated tool boundary, including nested cached data.
- Use approved hand-written known-answer arrays in allow-listed tests to cover
  missing HV, empty valid support, rejected baseline, incomplete sensitivity,
  duplicate source/acquisition pairs, shared dates, missing residuals, final
  masking, and measured no-motion versus insufficient evidence.
- Reject cached products lacking the same evidence required live; verify source
  IDs, executed-read records, dates, denominators and area conversion artifacts.
- Verify absent required operational keys fail explicitly and unused renderer
  settings do not block otherwise supported flood measurements.
- Coordinate the landslide test/units discrepancy with the hazard/config owners,
  and have consumers review the breaking schema before enabling motion products.
- Update the affected README Status rows and method KB documentation in the
  integration change. Run its relevant offline tests and repository checks;
  acquire real-data validation only through authorized cloud operators.

This proposal itself was checked by static source inspection. It includes no
new measurements, threshold values, code changes, installations, commits or
outward actions. Runtime tests and full hooks were not run for this documentation
draft; the earlier reference test results are not reused.
