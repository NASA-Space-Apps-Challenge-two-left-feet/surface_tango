# Agents/MCP integration handoff

The guarded graph implementation and its live bilingual bulletin follow-up are
merged to `main` in [PR #151](https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango/pull/151)
and [PR #162](https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango/pull/162).
The latter records an ES/EN run from real tool evidence in
[`reports/bulletin_demo.md`](../reports/bulletin_demo.md), including measured
values, denominators, source IDs, unavailable fields and a cached-serve replay.
The run report names GLM-5.3 via Hyperbolic as the model that served; it records
the configured provider's HTTP 402 and fallback. The graph does not select
scenes or invent observations. The default plan path is the ignored
`local_cache/agent_run_plan.json`.

Prepare that plan only from owner-staged real inputs. The required fields and
reference syntax are documented in [RUN_PLAN.md](RUN_PLAN.md). Every tool
request is validated before any tool effect. Numeric prose must resolve through
the merged bulletin contract, and cached templates are checked again when
served. GeoJSON remains deterministic tool output; the prose model cannot
generate geometry or measurements.

The onboarding verification on `main` commit `e140c01` passed the offline
repository suite:
**438 passed, 2 skipped, 8 deselected of 448 collected** (measured; command:
`uv run pytest -q -m "not network and not cache"`; no source granules apply).
The focused Agents suite passed **53/53 tests** on a later `main`-based branch
(measured; command: `uv run --frozen pytest -q tests/test_agents`;
denominator: 53 tests; no source granules apply).
The PR #162 report also records the graph run and cached-serve replay. These
results establish software and report-contract behavior, not the accuracy of
every hazard result or completeness of the underlying observations.

## Acceptance still needs owner inputs

- The frozen R/C/K pair IDs and pre-registration hash are committed on `main`;
  the captured bulletin still reports an uninformative earthquake scorecard
  because barrio labels are missing and the layover/shadow mask is unavailable.
- The report describes the graph run and traces values to evidence, but it does
  not preserve the exact shell command used for that run. Record a reproducible
  command before treating the reported measurements as independently rerun.
- The graph's scoring requests use `dataset_id`; the MCP scoring wrappers on
  `main` accept arrays/labels. Align the interface with the scoring/MCP owner.
- Validate GDAL redirect destinations in the MCP staging layer before using
  owner credentials and bucket writes. This is outside the `agents/` issue scope.
- Before broader scientific acceptance, verify measured transport/backend
  parity, provenance completeness and any rendered map; keep unavailable fields
  explicit. The cached report does not prove all operational paths are live.

The Agents code and real-evidence bilingual bulletin are on `main`. The
orchestrator closed issue #36 after the graph and bulletin merges; the remaining
scoring and redirect items above are cross-lane follow-ups, not unmerged graph
code. The captured nulls are honest outcomes, not a claim that every hazard has a
complete result or that the submission is ready.
