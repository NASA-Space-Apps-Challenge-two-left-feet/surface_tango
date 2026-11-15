# Brief: feat/data-flood-quake-evidence — flood & quake MCP evidence serializers (agent: opencode GLM-5.3)

- **Goal:** finish the MCP evidence loop started in #126/#127. Extend `scripts/write_hazard_evidence.py` with **flood** and **quake** serializers so `analyze_flood_inundation` (the video headline) and `analyze_earthquake_dpm` serve the real measured numbers instead of `not cached`. The landslide serializer (#127) is the pattern to follow.
- **Issue:** #20 / #122 (MCP evidence). **Reference contract:** `briefs/proposal-mcp-evidence-fields.md` and `docs/kb/mcp-evidence-artifact-schema.md`.
- **Inputs (all structured, already in `local_cache/` — read them, do NOT recompute science, do NOT call Earth Engine or ASF):**
  - Flood: `local_cache/mojana/provenance.json` — has `baseline` (`accepted`, `reference_date`, `f_wet`, `f_dry`, `gap`) and `dates` (a list; each: `date`, `granule_ids`, `n_water`, `n_valid`, `n_class1`, `n_valid_class1`, `n_class2`, `n_valid_class2`). Grid/pixel area: `local_cache/mojana/manifest.json` (90 m grid → `pixel_area_m2 = 8100`; confirm from the manifest, do not hardcode if the manifest states it). Thresholds/uncalibrated list and the sensitivity range come from `reports/mojana.md` **only if** also present structurally — otherwise set `sensitivity_range: null` with reason "sweep not serialized".
  - Quake: `local_cache/quake/dpm_track{11,47}.zarr/zarr.json` → `attributes.provenance` (a JSON string). It has `pairs` (R/C/K, IDs, baseline_days), `units` (`n_units`, `unit_source`, counts), `grid`, `baseline_mismatch`, `prereg_frozen`, and **`summary_C` / `summary_K_control`** (the SEALED co-event/control statistics). Valid/built-up/non-built pixel counts are in the provenance (`units` and/or top-level count fields — inspect and map them).
- **Outputs:**
  - `scripts/write_hazard_evidence.py`: add `flood_artifact(aoi="mojana")` and `quake_artifact(aoi="eje_cafetero", track=...)`, register them in `BUILDERS`/`OUT_NAME`, and support `--hazard {flood,quake}` (`--track` for quake).
  - Writing `local_cache/mojana/flood_evidence.json` and `local_cache/eje_cafetero/quake_evidence_track{11,47}.json` (git-ignored; verify the tools serve them).
  - `tests/test_hazard_evidence_writer.py`: add known-answer tests for both (synthetic structured inputs via `monkeypatch.setattr(whe, "CACHE", tmp_path)`, like the landslide tests).
- **Files you may touch:** `scripts/write_hazard_evidence.py`, `tests/test_hazard_evidence_writer.py`, this brief. **Nothing else.**

## The #122 schema the artifacts must match (so `mcp_servers/evidence.py` accepts them)
Read `mcp_servers/evidence.py` for the exact fields the builders require; match them. In short:
- **flood_evidence.json**: `schema: "flood/1"`, `provenance` (`source`, `granule_ids`, `cache_build_time`), `baseline` (with `accepted`), `water_extent` (an **area object**: `value_ha`, `pixel_count`=n_water, `valid_pixel_count`=n_valid, `pixel_area_m2`, `source_ids`, `reference_date`), `dates`, and `open_water_flood` / `subcanopy_double_bounce_flood` as area objects **with `reference_date` and `target_date`** (from the per-date Class 1/2 counts for the display date). `value_ha = pixel_count * pixel_area_m2 / 1e4`. Pick the display date = the headline date in `reports/mojana.md` (2026-06-17). `uncalibrated`: the list from `config/preregistered.yaml` `labels.uncalibrated`.
- **quake_evidence_track<N>.json**: `schema: "quake/1"`, `provenance`, `counts` (`valid_pixels`, `window_pixels`, `units_total`, `evaluated`, `excluded`), `pairs`, `units`, `scorecard: {state: "uninformative", reason: "no barrio labels (reports/ground_truth.md, #24)"}`.
  - **SEALING (critical):** while `prereg_frozen` is false, **omit `summary_C` and `summary_K_control` entirely from the artifact** — do not write the C/K statistics to disk at all (the artifact ships in the team cache release; a sealed value on disk is a leak, deviation 1). Only when `prereg_frozen: true` may the artifact include `coherence_statistics`. The MCP builder also seals at serve time, but the artifact itself must not carry sealed numbers while draft.

## Verify (end to end, offline)
For each hazard, after writing the artifact, start the server and confirm the tool serves it (the landslide check in the #127 PR is the template):
```
uv run python scripts/write_hazard_evidence.py --hazard flood
uv run python scripts/write_hazard_evidence.py --hazard quake --track 11
uv run python scripts/write_hazard_evidence.py --hazard quake --track 47
```
then a short `Client(mcp)` call per tool asserting `state` and that `analyze_flood_inundation` returns `water_extent_ha.pixel_count == 5539`, `valid_pixel_count == 197758` for 2026-06-17, and `analyze_earthquake_dpm` returns `counts.valid_pixels == 316399` (track 11) with `coherence_statistics: null` and `coherence_statistics` under `unavailable`.

## Acceptance
- `make ci` green (offline tests + hooks); new known-answer tests for both serializers pass.
- The three artifacts are written and the tools serve them with the real numbers above; quake C/K are **absent from the artifact and sealed in the envelope**.
- `rg -n 'summary_C|summary_K_control|excess' local_cache/eje_cafetero/quake_evidence_track*.json` is **empty** while draft.
- One commit per logical change, Conventional Commits, `Refs: #20`, `Co-Authored-By: opencode GLM-5.3`. `make sync` before each commit.

## Out of scope / forbidden
- No Earth Engine / ASF / GCS calls, no cache rebuild, no recomputation of science (read the structured files only).
- Don't touch `mcp_servers/`, `config/`, the reports, or any other lane's files.
- Do **not** push, merge, switch branches, reset, stash, open PRs, or run `gh`. The orchestrator reviews the diff and does those.

## If blocked
Write `BLOCKED: <reason>` at the end of this file and stop (e.g. a count field you can't locate in the provenance).

## Report (append when done)
What you built, the three write commands and their output tails (counts only — never a C/K statistic), the tool-serves-it check results, and anything you could not map.
