# Brief: feat/decision-layer

- **Goal:** An evidence-state response posture for every AOI, from the hazard envelopes the platform already serves.
- **Issue:** none (orchestrator request, 2026-11-15)
- **Plan reference:** docs/designs/bailasar.md evidence rules; docs/kb/decision-nrf-priorities.md
- **Inputs:** `local_cache/<aoi>/*evidence*.json` via `mcp_servers.evidence`. No new GEE or ASF calls.
- **Outputs:** `GET /api/decision` and `GET /api/decision/{aoi}`, the mission-control card.
- **Files you may touch:** `mcp_servers/decision.py`, `mcp_servers/flood_display.py`, `config/bailasar.yaml` (`decision:` only), `app.py`, `static/decision.js`, `static/index.html`, `static/aoi-nav.js`, `static/story-map.js`, `tests/test_decision.py`, `tests/test_flood_display.py`, `validation/ALLOWLIST.md`, `README.md`, `docs/kb/decision-*.md`, `docs/kb/flood-hand-display.md`, this brief.
- **Out of scope:** `config/preregistered.yaml`, `validation/scoring.py`, hectare or dollar cutoffs, PAGER colors, WorldPop or OSM counts that are not already on an envelope, the VM deploy, GraphRAG.
- **Steps:**
  1. Map each AOI to its own hazard.
  2. Copy extent, or mark it unavailable. Quake pixels stay an analyzed window.
  3. Rank lights: deploy assessment, provisional, not assessed, monitor.
  4. A monitor light does not clear an unassessed sibling. Out-of-scope hazards are not a clearance.
  5. Actions are no dispatch, preposition assessment, or dispatch life-safety assessment. Quantities stay unavailable.
  6. The flood overlay draws the measured open-water edge. Interior blue is MERIT HAND, labeled as not a surveyed depth. Building typology and land-use weights stay unavailable. No agricultural multiplier is applied.
- **Acceptance (commands that must pass):** `uv run pytest -q tests/test_decision.py -m "not cache"` and `uv run pytest -q tests/test_decision.py -m cache` when the cache is linked. `make ci` still has the pre-existing cut-fixture and parquet failures on this trunk.
- **Outward or paid actions needing approval:** push, PR, merge, VM redeploy.
- **Report:** README status row. No new measured number is claimed.
- **If blocked:** write `BLOCKED: <reason>` in `status/frontend-video.md` and stop.
