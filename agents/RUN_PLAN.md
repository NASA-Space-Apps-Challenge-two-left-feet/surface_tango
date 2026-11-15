# Real-input graph handoff

The graph reads `local_cache/agent_run_plan.json` by default. This ignored file
must be prepared from actual staged inputs by their owner. This branch supplies
software contracts, not observed hazard results or a fabricated runnable plan.

| Plan field | Required content |
|---|---|
| `context` | Actual `bbox`, `start_date`, `end_date`; they must match the invocation |
| `ingestion_requests` | Ordered objects with unique `id`, approved `tool`, and explicit `arguments` |
| `tool_requests` | Domain arguments for landslide, earthquake and flood |
| `placeholders` | Dotted tool-output keys mapped to the declarations accepted by `Placeholder` in `agents/bulletin.py` |
| `recipe` | Explicit model/prompt revision string for cache identity |
| `llm` | Optional literal `configured`, selecting the operational provider chain |
| `model` | Optional exact model ID from the configured provider chain; mutually exclusive with `llm` |

An ingestion argument may reference an already staged field with
`{"from_staged": "request-id", "path": ["field"]}`. A context reference uses
`{"from_context": "bbox"}` or a date field. References never supply defaults for
missing observations. Repeated calls to the same tool need different request IDs.
The complete ingestion/domain request collection is validated before its first
tool call, including state-supplied overrides of the plan.

Earthquake domain requests may be ordinary DPM arguments or an object with
`tool` and `arguments`. Approved selections are `analyze_earthquake_dpm`,
`rank_first_aid_barrios` and `score_against_baseline`. Scoring receives a real
staged `dataset_id` in the graph request contract. On `main`, however,
`mcp_servers/scoring_tools.py` exposes ranking arrays and ordered labels; it does
not resolve `dataset_id`. The graph's scoring routes are therefore not executable
against those MCP schemas yet. Resolve this with the scoring/MCP owner before
selecting either scoring operation in a live plan. Do not substitute invented
arrays or labels.
The other domains retain their approved hazard tools.

For configured prose, set `llm` to `configured` and use the operational settings
in `config/bailasar.yaml`. Keep secrets in the ignored environment. Model clients
may also be restricted to one exact configured model ID using `model`; unknown
model IDs are rejected before tool calls. Both selection modes bind the chosen
configuration to the prose cache identity. Model clients are constructed only
for uncached generation after valid tool evidence arrives.
Offline mode never constructs a prose provider. Cached prose is bound to the
evidence, schema, prompt recipe and configured provider/model settings; changing
these requires fresh validation and, when authorized, fresh generation.

Run the graph from its worktree with:

```powershell
$env:OFFLINE_DEMO_MODE = '1'
uv run --frozen python -m agents.orchestrator --plan local_cache/agent_run_plan.json
```

The command emits an explicit unavailable/gate/error state when prerequisites are
missing. An absent plan does not select scenes or invoke a paid model. Successful
bulletins must contain checked ES/EN prose and the SI-Assisted Analytics badge.
GeoJSON passes through deterministic tool output; the LLM supplies no geometry
or numerical observations.

The guarded graph and live bilingual bulletin were merged to `main` in PRs #151
and #162. Their current evidence and remaining acceptance gates are summarized
in [INTEGRATION_HANDOFF.md](INTEGRATION_HANDOFF.md). The server-side redirect
guard and scoring schema alignment are cross-lane MCP work; offline agent
contract tests do not establish those server behaviors or scientific accuracy.
