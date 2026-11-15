# Epicenter AOIs — hour-2 gate (R/C/K triplets, measured)

Gate record for the two operational AOIs added in #190 (`4_choco_epicenter_quake`,
`5_valle_del_cauca_quake`). **Not the frozen scorecard** (Eje Cafetero). Grounded
in the USGS epicenter us6000tjl2 + public geography. Structured record:
`nisar_epicenter_aois_gate.json` (separate from the committed catalog, which is
unchanged). *(measured 2026-11-15, `asf.geo_search`, NISAR L2, stream PR.)*

## Complete reference+co-event+control triplets

**`4_choco_epicenter_quake`** — 96 granules (50 GCOV · 39 GUNW · 7 GOFF):

| track | geom | C (co-event) | R | K | K timing |
|---|---|---|---|---|---|
| 11 | desc | 24 d | 12 d | 12 d | **pre-event** |
| 47 | asc | 24 d | 12 d | 12 d | **pre-event** |
| 148 | asc | 24 d | 12 d | 12 d | **pre-event** |

**`5_valle_del_cauca_quake`** — 192 granules (99 · 79 · 14):

| track | geom | C | R | K | K timing |
|---|---|---|---|---|---|
| 11 | desc | 24 d | 12 d | 12 d | pre-event |
| 47 | asc | 24 d | 12 d | 12 d | pre-event |
| 112 | desc | 36 d | 12 d | 12 d | pre-event |
| 148 | asc | 24 d | 12 d | 12 d | pre-event |

## Why this matters
- The epicenter has **cleaner control geometry than the frozen scorecard AOI**:
  all three Chocó tracks have a true **pre-event** K (12 d), whereas Eje Cafetero
  track 11 required a post-event control fallback (deviation 2). So a damage proxy
  here can meet the control condition on every track.
- The C-baseline mismatch (24 d vs 12 d R/K) is the same recorded gate caveat; it
  carries to every number. These remain additional-coverage AOIs, PROVISIONAL —
  not a second frozen scorecard.

## Status
- **Done (this PR):** gate complete — granule counts and full R/C/K triplets per
  track, measured, for both AOIs.
- **Next (GEE, no LLM):** build the cache and run the coherence-loss damage proxy
  over these triplets (brief `briefs/feat/quake-epicenter-build.md`). Full granule
  IDs are in `nisar_epicenter_aois_gate.json`.
