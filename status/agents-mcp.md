# Agents/MCP status

Issue #20 transport/cache foundation and issue #21 bulletin contract are merged
to `develop`. Issue #36 graph implementation now routes explicit ingestion and
hazard plans through scoped SSE calls, revalidates bilingual placeholders and
cached prose, and refuses to invent inputs. Whole-plan validation checks tool
names, required and optional keys, literal argument types, context references,
and staged output paths before any tool effects. LangSmith run metadata remains
attached to graph invocations. The offline agent suite passed 51/51 tests
(measured; `uv run --frozen pytest -q tests/test_agents`; denominator: 51
tests; no source granules apply).

Issue #36 is still awaiting the committed frozen pair set/hash and owner-staged
real measurements, ground truth and geometry. Live result parity and a real
ES/EN end-to-end bulletin have not been demonstrated. See
[the integration handoff](../agents/INTEGRATION_HANDOFF.md).
