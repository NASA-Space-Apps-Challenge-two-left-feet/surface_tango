# Tool latency and breaker budgets (plan 02-06, #28)

Goal: 10 timed calls per live tool, write `p95 + 0.5 s` into
`config/bailasar.yaml` → `breaker_budgets_s`.

Status (2026-11-15, after #136 made the `analyze_*` tools cache readers):
**`search_nisar_granules` and `analyze_flood_inundation` measured and
budgeted.** `analyze_landslide_kinematics`, `analyze_earthquake_dpm` and the
two staging tools are still not timeable on real data — they stay on
`default: 1.8`, not an invented number.

## Credential state (read-only check)

`uv run python scripts/check_credentials.py`:

| Service | Result |
|---|---|
| earthdata | PASS — `EARTHDATA_USERNAME` + `EARTHDATA_TOKEN` (environment strategy) |
| gee | PASS — ADC identity, read-only `getInfo` ok |
| gcs | PASS — bucket list ok |
| llm | FAIL — no provider keys (not needed here) |

## `search_nisar_granules` — measured

Since #79, `mcp-nisar-asf` imports with no login at import, so the tool
runs. Timed as the real registered tool (not a proxy):

- Command: `uv run python <scratch>/time_tool.py` (loads `.env`, imports
  `mcp_servers.nisar_asf_mcp`, calls `search_nisar_granules`).
- 10 calls, Eje Cafetero AOI `[-75.85, 4.40, -75.40, 5.15]`, GCOV,
  window 2026-06-17 → 2026-11-14, each returned n=5 (the tool caps at 5).

| n | min | median | warm p95 | max |
|---|---|---|---|---|
| 10 | 0.391 s | 0.426 s | 0.693 s | **4.205 s (cold start, call 1)** |

- Budget `warm p95 + 0.5 = 1.19 s` → `config/bailasar.yaml`
  `breaker_budgets_s.search_nisar_granules: 1.2`.
- **Cold-start caveat:** the first call on a cold connection paid 4.205 s
  (TLS/connection warmup). A 1.2 s breaker trips once on that first call and
  then serves cached tiles; subsequent calls stay well under budget. If the
  first live search must not trip, warm the ASF connection at server start or
  raise this one tool's budget. Recorded, not silently absorbed.

## `analyze_flood_inundation` — measured

Since #136 the `analyze_*` tools on `mcp-gee-fusion` no longer take GCS URIs
or call Earth Engine: each reads `local_cache/<aoi>/<hazard>_evidence*.json`
and returns the #122 evidence envelope. So they are timed on the real cache.

- Cache: draft release `cache-2026-11-15` (staged from main `8ca49ef`),
  `gh release download cache-2026-11-15 -D dist/cache` then
  `uv run python scripts/cache_release.py assemble --manifest dist/cache/cache_manifest.json --parts-dir dist/cache`
  → `cache assemble: verified`.
- Artifact: `uv run python scripts/write_hazard_evidence.py --hazard flood`
  → `local_cache/mojana/flood_evidence.json` (display 2026-06-17, water
  5539/197758 px, baseline accepted — same counts as #136). Display-date
  granule `NISAR_L2_PR_GCOV_023_047_A_005_4005_DHDH_A_20260617T103906_20260617T103941_P05023_F_F_J_001`;
  11 dates in the artifact.
- Command: `uv run python <scratch>/time_analyze.py` from the worktree root.
  It imports `mcp_servers.gee_fusion_mcp` and calls the registered tool
  (through `cache_guard.with_offline_zarr_fallback`, so the thread hand-off
  and the config read are inside the timing) 10× with `aoi="mojana"`;
  `time.perf_counter` per call; p95 is nearest-rank over the 9 warm calls
  (= their max at n=9).
- Host: Windows 11, Python 3.12, fastmcp 4.2.0, local SSD. In-process call,
  no SSE round-trip.

| n | state | call 1 | warm min | warm median | warm p95 | max |
|---|---|---|---|---|---|---|
| 10 | `live` ×10 | 0.017 s | 0.014 s | 0.016 s | 0.019 s | 0.019 s |

*(measured, 2026-11-15; denominator 10 calls)*

- Budget `warm p95 + 0.5 = 0.519 s` → `config/bailasar.yaml`
  `breaker_budgets_s.analyze_flood_inundation: 0.52`.
- The tool is a local JSON read, so the 0.5 s margin dominates the budget.
  On a cold disk or a slower host it still has ~25× headroom over the
  measured p95.

## Still not timeable on real data

### `analyze_landslide_kinematics`, `analyze_earthquake_dpm`
Their artifacts cannot be written from the release cache:
`write_hazard_evidence.py --hazard landslide` → `skip landslide aburra:
summary.json or calibration.json absent` (the release has `summary.json` but
not `calibration.json`); `--hazard quake --track 11|47` → `dpm_track<N>.zarr
absent` (`local_cache/quake/` was withheld from the release while the
pre-registration was a draft). Timed anyway, both returned `not cached` on all
10 calls (p95 0.009 s / 0.010 s for tracks 11 and 47). That is the absent-file
path, not the live read, so it sets no budget. Budget stays `default: 1.8`.
(`analyze_biomass_disturbance` is out of scope — biomass dropped; it always
returns a gate result.)

### `stage_nisar_gcov_to_gcs`, `stage_nisar_gunw_ionosphere_corrected_to_gcs`
These **download NISAR granules and upload COGs to GCS** — a paid,
outward-facing run. Timing them 10× each needs Earthdata auth (token Bearer,
available) plus explicit approval for the cloud download/upload spend. Not run
here. Budget stays `default: 1.8`.

## To finish #28

1. A cache release that carries `local_cache/aburra/calibration.json` and
   `local_cache/quake/dpm_track{11,47}.zarr` (now that the pre-registration is
   frozen; the quake DPM is to be rerun with the #134 control pairs first),
   then time the landslide and quake tools the same way.
2. Approval for the paid `stage_nisar_*` runs, then time them and set their
   budgets.
