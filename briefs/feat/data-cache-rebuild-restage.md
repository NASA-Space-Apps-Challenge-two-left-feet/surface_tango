# Brief: feat/data-cache-rebuild-restage — rebuild cache, emit evidence, re-stage the release (agent: opencode Kimi-K3 via Nebius Token Factory)

- **Goal:** produce the definitive team cache for the submission: every AOI has the `hand_m` band, all three MCP evidence artifacts are written, and a fresh release is staged so teammates (and the demo) get the measured evidence. Data lane, LEONOB2014 account (you run with the user's `.env`, so you hold Earthdata/GEE/GCS).
- **Issue:** #30 / #42 (cache + release). **Reference:** `scripts/build_cache.py`, `scripts/write_hazard_evidence.py` (flood/quake/landslide serializers, #127/#136), `scripts/cache_release.py` (stage/verify), `docs/kb/mcp-evidence-artifact-schema.md`.
- **Prerequisite:** the pre-registration is **frozen** (`config/preregistered.yaml` `status: frozen`, hash `36a90fa…`). Never edit it. Because it is frozen, the quake C/K statistics are unsealed, so `quake_evidence_track<N>.json` may now carry `coherence_statistics` (the serializer keys this off `prereg_frozen`).

## Steps
1. **HAND band for all AOIs.** `scripts/build_cache.py` added `hand_m` for La Mojana (#137). Generalize it to Aburrá and Eje Cafetero (MERIT Hydro `MERIT/Hydro/v1_0_1` band `hnd`, each AOI's own grid, missing → NaN + `missing`, provenance recorded). `--only-band hand_m` appends without rebuilding other bands. If an AOI's cube already has `hand_m`, skip it.
2. **Emit the three evidence artifacts** (foreground):
   ```
   uv run python scripts/write_hazard_evidence.py --hazard landslide
   uv run python scripts/write_hazard_evidence.py --hazard flood
   uv run python scripts/write_hazard_evidence.py --hazard quake --track 11
   uv run python scripts/write_hazard_evidence.py --hazard quake --track 47
   ```
   Then confirm each MCP tool serves its artifact (a short `Client(mcp)` call, as in #127): `analyze_flood_inundation` → `water_extent_ha.pixel_count`/`valid_pixel_count` match `reports/mojana.md`; `analyze_landslide_kinematics` → the #109 null gate result; `analyze_earthquake_dpm` → counts, and with the file frozen, `coherence_statistics` now **present** (no longer sealed).
3. **Re-stage the release** `cache-2026-11-15-v2` from the three AOI folders (not `quake/`): include the `*_evidence.json` artifacts and the `hand_m` bands.
   ```
   uv run python scripts/cache_release.py stage --cache-dir <staged AOIs> --output-dir dist/cache-release --source-commit $(git rev-parse HEAD)
   uv run python scripts/cache_release.py verify --manifest dist/cache-release/cache_manifest.json --parts-dir dist/cache-release
   ```
   Do **not** publish the GitHub release (owner action). Leave the staged parts + manifest under `dist/cache-release/` and report their sizes + sha256.
   - **Seal check:** the previous release withheld co-event coherence. Now the prereg is frozen, so C-pair coherence is no longer sealed — but still exclude `local_cache/quake/` (the raw 291 MB DPM zarr) from the release; ship only the three AOI folders + their evidence artifacts.

## Acceptance
- `make ci` green. The three AOIs have `hand_m` (finite ratios in each manifest, *(measured)*). The three evidence artifacts exist and the tools serve them (quake `coherence_statistics` present post-freeze).
- `dist/cache-release/` has the staged parts + manifest, verified; report part sizes and sha256.
- A `reports/cache_release_v2.md` noting: per-AOI band counts + hand_m finite ratios, the evidence artifacts, the staged release size, and the exact numbers the flood/quake tools now serve.

## Rules
- No synthetic data; missing stays NaN + `missing`. Every number *(measured)* with denominator.
- Files you may touch: `scripts/build_cache.py`, `scripts/write_hazard_evidence.py`, `scripts/cache_release.py` (only if a bug blocks staging), `tests/test_cache_builder.py`, `reports/cache_release_v2.md`, this brief. Writing `local_cache/*` and `dist/cache-release/*` is expected.
- Earth Engine via `gee_math/ee_session.init_ee()`; run long jobs in the **foreground**; a stalled granule → `missing` (`docs/kb/nisar-gcov-read-timeouts.md`). Don't `.resample("nearest")` (`docs/kb/gee-image-resample-modes.md`).
- `make sync` before each commit. Do **not** push, merge, switch branches, reset, stash, open PRs, run `gh`, publish a GitHub release, or write to GCS. The orchestrator reviews and does those.

## If blocked
Write `BLOCKED: <reason>` and stop.

## Report (append when done)
Band counts + hand_m finite ratios per AOI, the evidence-artifact tool checks, the staged release sizes/sha256, and the measured numbers the tools now serve.

---

**Report — 2026-11-15 UTC (opencode Kimi-K3).** Full measured detail in `reports/cache_release_v2.md`; commit `9508d1e` on this branch.

- **`hand_m` per AOI** *(measured, `uv run python scripts/build_cache.py --aoi <aoi> --only-band hand_m`; MERIT/Hydro/v1_0_1 `hnd`, each AOI's own 512×512 grid)*: aburra 17 bands, 262144/262144 finite (ratio 1.0, range 0.0–1214.2 m); eje_cafetero 16 bands, 262144/262144 (1.0, 0.0–1204.3 m); mojana 17 bands, 262144/262144 (1.0, 0.0–716.0 m, already present from #137 → skipped unchanged). The builder change generalizes `append_merit_hand_band` to every AOI cube and skips a cube that already carries `hand_m` instead of raising.
- **Evidence artifacts** *(measured, the four `write_hazard_evidence.py` commands)*: landslide `no_motion`; flood display 2026-06-17 water 5539/197758 px, baseline accepted; quake t11 316399/10353357 px units 32/28/4 and t47 316398/10353357 px units 32/28/4, both carry `coherence_statistics` (pre-registration frozen).
- **Tool checks** *(measured, in-memory `fastmcp.Client(mcp)` calls, zero drift; script was a scratch file, not committed)*: `analyze_flood_inundation` live — 5539/197758 valid px, 4486.59 ha, matches `reports/mojana.md`; `analyze_landslide_kinematics` gate result — `no_motion`, 9.105440970850369 mm, 17 pairs (#109); `analyze_earthquake_dpm` t11/t47 live — counts as above, `coherence_statistics` **present** post-freeze.
- **Staged release** `dist/cache-release/` *(measured; NOT published, no GCS writes)*: single part `cache.tar.gz.part-000000`, 137264762 bytes, sha256 `ba24939ce6faec8019a0e0ec0ba3c62cf1131ebf9676e4a1ac5716f028614667`; `cache_manifest.json` 392705 bytes, sha256 `9f5266474b4b33316a6f2f5b8bb6ea71b5bb81bbdc3ff04d573b5a493943a9f8`; `source_commit` `9508d1ef5a75538ed8efc4bf3844e70fac190367`, built 2026-11-15T08:52:58Z. `cache stage: verified`; `cache verify: verified`. 1740 files (aburra 312, eje_cafetero 710, mojana 718): all four `*_evidence.json`, the three cubes with `hand_m`, the unsealed `coherence_C`/`coherence_coseismic` bands, COGs, tiles, manifests; zero `quake/` files. All entries `missing: true` provenance (no sidecars/zarr provenance in this layout — explicitly unknown, never fabricated; band provenance ships in the AOI manifests). The pre-staged copy `dist/staged-aois/` was left beside it (both git-ignored).
- **`make sync` / `make ci`**: sync clean before the commit; `make ci` green at baseline and after the builder change (422 passed, 7 deselected; `tests/test_cache_builder.py` 15 passed).
- Nothing pushed, no branches switched, no resets/stashes, no `gh`, no release publishing, no GCS writes.
