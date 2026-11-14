# Hour-2 data gate (#23, plan 02-01)

Run: `uv run python scripts/discover_nisar_colombia.py` (2026-11-14, ASF search, read-only).
Window 2026-06-17 → 2026-11-14 (public NISAR record). Evidence: `nisar_colombia_granules_2026.json`.
AOI bboxes: `config/bailasar.yaml` → `aois`.

## Coverage (measured)

| AOI | GUNW | GCOV | GOFF | Streams |
|---|---|---|---|---|
| 1 Aburrá (Medellín, Bello, Copacabana) | 20 | 24 | 3 | PR 38, UR 9 |
| 2 Eje Cafetero (Pereira, Armenia, Manizales) | 19 | 24 | 3 | PR 38, UR 8 |
| 3 La Mojana / Caregato | 68 | 82 | 8 | PR 134, UR 24 |

Polarization (from file names): GUNW and GOFF single-pol `SH`; GCOV mostly dual-pol `DHDH` (HH/HV), a few single-pol `SHSH` (Aburrá 2, Eje Cafetero 1, La Mojana 4). All products are **provisional** (`PR`, CRID P05023) or **urgent response** (`UR`). No validated products in the window.

## Quake R / C / K (automatic selection, provisional stream)

| Track | R (pre-event) | C (spans 2026-08-10) | K (control) | Baselines (days) |
|---|---|---|---|---|
| 11 descending, frame 86 | 2026-07-08 → 07-20 | 2026-07-20 → 08-13 | 2026-06-26 → 07-08 | R 12, **C 24**, K 12 |
| 47 ascending, frame 4 | 2026-07-11 → 07-23 | 2026-07-23 → 08-16 | 2026-06-29 → 07-11 | R 12, **C 24**, K 12 |

Full granule IDs: `quake_triplets` in the catalog.

## Decision table (applied)

| Row | Result | Decision |
|---|---|---|
| Quake R, C and K exist (pre-event K) | **Yes**, both tracks | Full scorecard path open; quake can headline, pending the hour-4 power check (#25) |
| Temporal baseline match | **No**: C is 24 days, R/K 12 days (Aug 1 / Aug 4 acquisitions missing) | "Closest available, mismatch recorded": report next to every quake number; the built-up vs non-built excess is relative, which partly absorbs the extra decorrelation |
| Only provisional products | **Yes** | Proceed; every view and the video carry PROVISIONAL |
| GUNW ionosphere layer (Aburrá) | Not yet probed per granule | Aburrá lane checks `ionosphericPhaseScreen` presence before claiming any velocity |
| HH+HV GCOV over La Mojana | **Yes** (78 DHDH) | Flood dual-pol path open |
| Coherence posting | 20 m and 80 m per ASF docs (not yet probed per granule) | Quake units stay at barrio level |

## Not done at this gate (owners)
- CHIRPS per acquisition date (needed for the wetness check): cache builder (#30). CHIRPS daily is published weeks late, so recent dates may be missing.
- Per-tool latency budgets (D6): #28 (Jack4Codes).
- Ground truth + polygons by hour 4: #24 (Maru816). Power check + headline: #25 (Jack4Codes).
