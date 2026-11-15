# Status: agents-mcp

_Last update: 2026-11-15 (UTC−5)_

- Doing: 02-06 tool latency budgets (#28), branch `feat/agents-mcp-tool-latency`
- Done:
  - `search_nisar_granules` measured on current main (post #79): n=10, warm p95 0.693 s, cold start 4.205 s. Budget `search_nisar_granules: 1.2` written to `config/bailasar.yaml` `breaker_budgets_s`.
  - `reports/tool_latency.md`: the search measurement (with the cold-start caveat) and why the staging/analyze_* tools are still not timeable on real data.
- Blocked (partial): the `stage_nisar_*` tools need approval for a paid download/upload run; the `analyze_*` tools need real staged-COG URIs from the cache (#30/#78). Both stay on `breaker_budgets_s.default` until then — no number fabricated.
