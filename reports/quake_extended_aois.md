# Extended earthquake AOIs — NISAR coverage and co-event pairs (measured)

Additional quake coverage beyond the frozen scorecard AOI (`2_eje_cafetero_quake`,
Pereira/Armenia/Manizales). These AOIs are **operational, not part of the frozen
pre-registration**: they add damage-proxy *coverage* for the demo, not a second
scorecard. Grounded in public geography and the USGS-verified epicenter
us6000tjl2 (San José del Palmar, Chocó, −76.26 / 4.86;
`docs/kb/event-2026-08-10-earthquake.md`).

Why these: the Chocó epicentral zone is persistently cloud- and canopy-covered —
optically blind, where NISAR L-band is the only sensor that sees the surface.
That is the core BailaSAR thesis applied to the actual epicenter.

## Coverage *(measured 2026-11-15, `asf.geo_search`, NISAR L2, 2026-06-17 → 11-14)*

| AOI | bbox [W,S,E,N] | granules | GCOV · GUNW · GOFF | GUNW tracks |
|---|---|---:|---|---|
| `4_choco_epicenter_quake` (San José del Palmar / San Juan basin) | [-76.70, 4.40, -75.95, 5.25] | **96** | 50 · 39 · 7 | 11, 47, 148 |
| `5_valle_del_cauca_quake` (Cali / Buenaventura / Cartago) | [-77.10, 3.30, -75.95, 4.95] | **192** | 99 · 79 · 14 | 11, 47, 112, 148 |

## Co-event (C) interferogram pairs — spans the 2026-08-10 event *(measured; PROVISIONAL, stream PR)*

**Chocó epicenter** — co-event GUNW on three tracks (all 24-day, the gate's recorded mismatch):
- track 11 (desc): `NISAR_L2_PR_GUNW_026_011_D_086_028_4000_SH_20260720…20260813…P05023…`
- track 47 (asc): `NISAR_L2_PR_GUNW_026_047_A_004_028_4000_SH_20260723…20260816…P05023…`
- track 148 (asc): `NISAR_L2_PR_GUNW_025_148_A_004_027_2000_SH_20260718……`

**Valle del Cauca** — co-event GUNW on four tracks (24–36 day):
- track 11, track 47 (shared with Eje Cafetero), track 112 (36-day), track 148.

## Status and next steps
- **Done:** AOIs added to `config/bailasar.yaml` (operational); coverage and co-event pairs confirmed by the hour-2 gate method. Full granule IDs in the gate run output.
- **Pending (bigger lift, GEE):** build the cache and run the coherence-loss damage proxy over these AOIs, same frozen method as Eje Cafetero. The baseline mismatch (C 24 d) and the "proxy contrast, PROVISIONAL, not a validated scorecard" caveats carry over. The pre-registration is **not** changed.
- **Not used:** no outside narrative, report or its statistics informs any number here — only ASF search results, public geography and the USGS event page.

## Narrative hook for the demo video (recover this for storytelling)

> **"NISAR saw the epicenter that no optical satellite could."** The M7.4 struck
> San José del Palmar, Chocó — one of the cloudiest, most remote corners of the
> Americas, where optical and C-band go blind. BailaSAR's L-band observatory
> covers that epicenter (measured: 96 NISAR granules, co-event interferograms on
> three tracks) and the isolated western-Andes zones around it. This is the
> project's thesis, demonstrated where it matters most — not a major city, but
> the optically-blind epicentral zone that early response struggled to reach.

Use this as the earthquake chapter's framing. Numbers shown on screen come only
from measured reports (coverage here; damage proxy from `reports/quake_dpm.md`
and `reports/quake_dpm_interpretation.md`). The La Mojana flood remains the
ratified headline (#102); the epicenter is the earthquake chapter's hook.
