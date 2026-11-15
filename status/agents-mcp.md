# Agents/MCP status

The Agents graph and guarded preflight were merged to `main` in PR #151; the
live bilingual graph run and evidence-linked report were merged in PR #162.
The graph validates complete plans before tool effects, checks bilingual
placeholders and cached prose, and emits explicit unavailable states. The
captured report at `reports/bulletin_demo.md` contains real tool evidence in
English and Spanish, source IDs, denominators and explicit unavailable results.

At `main` commit `e140c01`, the onboarding verification's offline repository suite passed **438 tests**
(measured; `uv run pytest -q -m "not network and not cache"`; 448 collected,
2 skipped and 8 deselected; no source granules apply). The focused Agents suite
passed **53/53 tests** (measured; `uv run --frozen pytest -q tests/test_agents`;
denominator: 53 tests; no source granules apply). See
[the integration handoff](../agents/INTEGRATION_HANDOFF.md) for remaining
cross-lane acceptance gaps: the captured run lacks its exact invocation command,
scoring request schemas do not match the MCP wrappers, and GDAL redirect
validation remains MCP work. The orchestrator closed issue #36 after the graph
and bulletin merges; these gaps do not mean its Agents implementation remains
unmerged.
