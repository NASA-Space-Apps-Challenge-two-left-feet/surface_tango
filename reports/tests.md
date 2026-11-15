# Offline test results

- Command: `uv run pytest -q -m "not network and not cache"`
- Run at: `2026-11-15T04:41Z` (UTC), by the orchestrator while merging #93.
- Branch: `docs/readme-fixes-0503`, rebased on `origin/main` at `97068c7`.
- Result: **180 passed** *(measured)*.
- Scope / denominator: tests selected by `not network and not cache` in this run.
- Source granule or scene IDs: not applicable to this offline test-suite result.
- History: 156 passed at `91dc569` (2026-11-15T04:12:35Z), before #98 added the La Mojana tests.
