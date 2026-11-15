# Brief: feat/agents-bulletin-live-run — live bilingual bulletin from the hazard graph (agent: opencode GLM-5.3 via Hyperbolic)

- **Goal:** run the merged LangGraph hazard graph (#36/#151) end to end against the MCP evidence tools and produce the **ES/EN bilingual cross-hazard bulletin** for the three AOIs, proving the placeholder contract fills from real tool outputs (never invented numbers). This is the agent-stack demonstration the video narrates.
- **Issue:** #36 (follow-up to #151). **Reference:** `agents/orchestrator.py` (`build_and_run_multi_hazard_graph`, `create_compiled_multi_hazard_graph`), `agents/bulletin_runtime.py`, `agents/run_plan.py`, `agents/bulletin.py`, `agents/RUN_PLAN.md`, `agents/INTEGRATION_HANDOFF.md`.
- **LLM:** the orchestrator LLM is the fallback chain in `config/bailasar.yaml` `llm:`. You are **GLM-5.3 via Hyperbolic** — make sure your Hyperbolic endpoint + token are set so the chain resolves to a served model (`uv run python scripts/check_credentials.py --only llm`). Agents write prose with `{placeholders}`; they never produce numbers.
- **Prerequisite:** the hazard evidence artifacts (`local_cache/<aoi>/<hazard>_evidence*.json`) must exist for the tools to serve `live`/`cached`. If they are absent (the cache-rebuild handoff has not run), the tools return `not cached`; in that case run the bulletin in `OFFLINE_DEMO_MODE=0` and show the `not cached`/placeholder path honestly, and note it.

## Steps
1. **Run the graph** for each AOI (foreground), e.g. via `make test-dag` or a small driver calling `build_and_run_multi_hazard_graph(initial_state)`:
   - ingestion → landslide/flood/earthquake agents (each calls its `analyze_*` tool) → `cross_hazard_synthesis`.
   - Confirm every numeric slot in the bulletin is a declared placeholder resolved from a tool output (`BulletinContractError` if not), and the bilingual (ES/EN) rendering works.
2. **Capture the bulletin** for the headline (La Mojana flood) and the two others into `reports/bulletin_demo.md`: the ES and EN text, and beside each number the tool + evidence field it came from (state, denominator, source IDs). The **SI-Assisted Analytics** badge marks the AI-written text (AGENTS.md).
3. **Verify the contract**: add/confirm an offline test that a number with no backing tool output raises `BulletinContractError`, and that a withheld/sealed field renders as "not available", never a fabricated value.
4. If a provider in the chain is unreachable, record which model actually served (the chain falls through); never hand-write a number to fill a gap.

## Acceptance
- `make ci` green (offline tests, incl. the contract test); `make test-dag` (or your driver) runs the graph to a bilingual bulletin.
- `reports/bulletin_demo.md` has the ES/EN bulletin with every number traced to a tool evidence field and its source; the SI-Assisted Analytics badge present; no NASA logos.
- Your report names the model/endpoint that served and confirms no number was produced by the LLM.

## Rules
- Agents never produce numbers — placeholders only, validated against tool outputs. No synthetic data.
- Files you may touch: `agents/*.py` (bulletin/graph wiring only — do not change the evidence tools or hazard math), `tests/test_agents/*`, `reports/bulletin_demo.md`, this brief. Do not touch `mcp_servers/`, `gee_math/`, `config/`, `local_cache/` science outputs.
- No NASA logos/flags. The SI-Assisted Analytics badge on AI text. Material from outside the project is never named/cited/committed.
- `make sync` before each commit. Do **not** push, merge, switch branches, reset, stash, open PRs or run `gh`. Keep the orchestrator LLM key out of logs and the report.

## If blocked
Write `BLOCKED: <reason>` (e.g. no LLM key resolves, or no evidence artifacts) and stop.

## Report (append when done)
The model/endpoint that served, the bilingual bulletin location, the number→tool-evidence tracing, and the contract-test result.
