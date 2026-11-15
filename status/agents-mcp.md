# Status: agents-mcp

_Last update: 2026-11-15 (UTC−5)_

- Doing: 02-06 tool latency budgets (#28), branch `feat/agents-mcp-tool-latency`
- Done:
  - `search_nisar_granules` measured on current main (post #79): n=10, warm p95 0.693 s, cold start 4.205 s. Budget `search_nisar_granules: 1.2` written to `config/bailasar.yaml` `breaker_budgets_s`.
  - `reports/tool_latency.md`: the search measurement (with the cold-start caveat) and why the staging/analyze_* tools are still not timeable on real data.
- Blocked (partial): the `stage_nisar_*` tools need approval for a paid download/upload run; the `analyze_*` tools need real staged-COG URIs from the cache (#30/#78). Both stay on `breaker_budgets_s.default` until then — no number fabricated.

## MCP transport foundation (issue #20)

Both servers use configured SSE endpoints without startup authentication. Cache fallback matches the exact request and requires provenance; uncached requests remain explicit. Per-tool budgets come from operational config; live budget measurements remain issue #28. Pair/ranking/score wrappers and graph integration remain separate work.

## Bulletin contract (issue #21)

Implemented placeholder schema, numeric evidence requirements, sensor-name allow-list and tool-output integrity checks. Only verified non-null event fields reach prose. Unsupported event depth remains missing. Locale rendering and graph end-to-end acceptance remain issue #36.

## MCP scoring tools (#35, Jack4Codes)

_Last update: 2026-11-15 (UTC−5)_ · branch `feat/mcp-scoring-tools`

- Done: `mcp_servers/scoring_tools.py` — three thin wrappers over `validation.scoring` (#18): `get_earthquake_pair_set` (R/C/K triplets from the frozen pre-registration), `rank_first_aid_barrios` (radar ranking + evaluation k), `score_against_baseline` (precision@k radar vs baseline, Wilson CIs, informative gate). Registered on `mcp-nisar-asf` (imports without Earth Engine creds).
- No numbers of their own: every weight/threshold/k comes from `config/preregistered.yaml`; a null or missing value raises, never a default. `get_earthquake_pair_set` raises until the pairs are filled and frozen (#26).
- Tests: `tests/test_mcp_scoring_tools.py` (11 offline), expected values taken from calling `validation.scoring` directly (no hand-computed constants, nothing to allowlist).
- Handoff (hazard-modeling lane, LEONOB2014): `mcp_servers/gee_fusion_mcp.py` `analyze_earthquake_dpm` imports `compute_earthquake_dpm_and_rupture`, which no longer exists in `gee_math/earthquake_dpm_math.py` (now lazy on `main`, so import survives but the call would fail). Not in my lane; flagged for the owner.

## Live tool latency handoff (#28, alicealanapineda-byte)

Offline owner-runner and preregistered call plan in `mcp_servers/tool_latency.py` + `reports/tool_latency_plan.json`; a cloud owner runs it to fill live measurements (the readiness report has none yet).
