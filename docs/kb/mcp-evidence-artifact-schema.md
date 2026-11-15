---
title: MCP hazard tools read a serialized evidence artifact per AOI; they never compute or invent numbers
status: verified
source: briefs/proposal-mcp-evidence-fields.md
accessed: 2026-11-15
quote: "An adapter may populate it only from an actual evidence-bearing artifact."
used_in: [mcp_servers/evidence.py, mcp_servers/gee_fusion_mcp.py, "#20", "#122"]
verified_by: LEONOB2014
supersedes: null
---

The `analyze_*` tools on `mcp-gee-fusion` are adapters over
`local_cache/<aoi>/<hazard>_evidence*.json`, written by the data lane during the
cache build from the same measured run as `reports/<hazard>.md`. The tool reads
the artifact and returns the #122 envelope (`mcp_servers/evidence.py`); an absent
artifact is `not cached`. Verified 2026-11-15: the server starts and all four
tools return the contract envelope (`uv run python -c "...Client(mcp)..."`),
with 11 builder tests.

Artifact required keys (`EvidenceError` if absent):
- all: `schema`, `provenance` (`source`, `granule_ids`, `cache_build_time`).
- flood (`flood_evidence.json`): `baseline.accepted`, `water_extent` (an area
  object: `value_ha`, `pixel_count`, `valid_pixel_count`, `pixel_area_m2`,
  `source_ids`, optional `sensitivity_range`); optional `open_water_flood`,
  `subcanopy_double_bounce_flood`, `total_inundated`, `sentinel1_comparison`,
  `rainfall`, `dates`, `uncalibrated`.
- landslide (`landslide_evidence.json`): `noise_floor_verdict.outcome` in
  {`missing`, `too_few_pairs`, `no_motion`, `motion`}; `motion` also needs
  `retained_rate_stat_mm_yr`; optional `pairs`, `key_quantitative_metrics`.
- quake (`quake_evidence_track<N>.json`): `counts.valid_pixels`;
  `coherence_statistics` served only when `config/preregistered.yaml`
  `status: frozen`, else sealed and listed under `unavailable`.

Renderer/hotspot fields are always null + `unavailable` (the modules write local
rasters, not GEE tiles, and have no hotspot reduction — never an AOI centroid).
Alert thresholds come only from `config/bailasar.yaml` `hazard_tools.<domain>.alert`;
missing keys are an `error`, never a default GREEN. Alerts fire only when the
graded metric exists (flood total change area; landslide retained-rate on a
motion verdict), so the current measured results (degenerate flood classes, the
Aburrá null) report `alert_level: null` with a reason and need no config.
