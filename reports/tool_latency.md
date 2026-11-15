# Tool latency and breaker budgets (plan 02-06, #28)

Goal: 10 timed calls per live tool, write `p95 + 0.5 s` into
`config/bailasar.yaml` → `breaker_budgets_s`.

Status (2026-11-15, after #79 dropped the module-level netrc login):
**`search_nisar_granules` measured and budgeted.** The staging and
`analyze_*` tools are still not timeable on real data — they stay on
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

## Still not timeable on real data

### `stage_nisar_gcov_to_gcs`, `stage_nisar_gunw_ionosphere_corrected_to_gcs`
These **download NISAR granules and upload COGs to GCS** — a paid,
outward-facing run. Timing them 10× each needs Earthdata auth (token Bearer,
available) plus explicit approval for the cloud download/upload spend. Not run
here. Budget stays `default: 1.8`.

### `analyze_landslide_kinematics`, `analyze_flood_inundation`, `analyze_earthquake_dpm` (`mcp-gee-fusion`)
Each takes **GCS URIs of staged NISAR COGs** as inputs
(`coh_pre_gcs`, `gcov_hhhh_pre_gcs`, `gunw_unw_gcs`, …). Timing them needs real
staged-COG URIs; a fake URI only exercises the offline zarr fallback (a fixed
1.8 s), which is not a measurement. Pending real inputs from the cache build
(#30/#78). Budget stays `default: 1.8`. (`analyze_biomass_disturbance` is out
of scope — biomass dropped.)

## To finish #28

1. Approval for the paid `stage_nisar_*` runs, then time them and set their
   budgets.
2. Real staged-COG URIs (from the cache) to feed the `analyze_*` tools, then
   time them and set their budgets.
