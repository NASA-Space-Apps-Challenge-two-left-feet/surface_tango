# Agents/MCP integration handoff

The graph composes ingestion, three hazard requests and checked bilingual
synthesis over the merged SSE servers. A real-input plan is required; the graph
does not select scenes, invent observations or call a prose model in offline
mode. The default plan path is the ignored `local_cache/agent_run_plan.json`.

Prepare that plan only from owner-staged real inputs. The required fields and
reference syntax are documented in [RUN_PLAN.md](RUN_PLAN.md). Every tool
request is validated before any tool effect. Numeric prose must resolve through
the merged bulletin contract, and cached templates are checked again when
served. GeoJSON remains deterministic tool output; the prose model cannot
generate geometry or measurements.

The agent contract suite passed **48/48** cases with
`python -m pytest -q tests/test_agents` using the project's locked Python 3.12
environment. These tests cover plan validation, state transitions, caching,
placeholder checks and offline behavior. They do not establish live tool
connectivity or scientific results.

## Acceptance still needs owner inputs

- The config owner must commit frozen R/C/K pair IDs and the preregistration
  hash before earthquake evidence is available.
- Data and scoring owners must stage real measurements, provenance, source-linked
  ground truth and geometry. Missing measurements must stay explicit nulls.
- A cloud owner must complete measured-result parity and live tool integration.
- With those inputs, run the graph through actual SSE servers, verify ES and EN
  output and badge insertion, and inspect any rendered map before claiming
  end-to-end scientific acceptance.

The local offline contract is ready for review. Issue #36 remains open until the
data-dependent acceptance above is satisfied. The software gates do not imply
that a real hazard result or submission-ready bulletin exists.
