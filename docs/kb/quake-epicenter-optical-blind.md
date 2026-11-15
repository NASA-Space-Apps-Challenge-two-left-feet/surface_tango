---
title: The 2026-08-10 epicenter (San José del Palmar, Chocó) is optically blind and NISAR L-band covers it — the strongest "why L-band" evidence for the earthquake lane
status: verified
source: https://earthquake.usgs.gov/fdsnws/event/1/query?eventid=us6000tjl2&format=geojson
accessed: 2026-11-15
quote: "4 km SSW of San José del Palmar, Colombia"
used_in: [config/bailasar.yaml, reports/quake_extended_aois.md, video/storyboard.md, "#31"]
verified_by: LEONOB2014
supersedes: null
---

The USGS preferred epicenter of the M7.4 event (us6000tjl2) is **San José del
Palmar, Chocó** (−76.26 / 4.86), in the San Juan basin of the Pacific/western
Andes. This region is among the cloudiest and wettest on Earth (public
geography), so optical satellites (Sentinel-2, Landsat) and short-wavelength
C-band are least useful exactly where the shaking was strongest and the terrain
most remote.

**Measured 2026-11-15 (ASF NISAR search):** NISAR L-band **covers the epicenter**
— `4_choco_epicenter_quake` [-76.70, 4.40, -75.95, 5.25]: 96 granules (50 GCOV,
39 GUNW, 7 GOFF), with **co-event interferograms on tracks 11, 47 and 148**.
`5_valle_del_cauca_quake`: 192 granules, co-event on tracks 11, 47, 112, 148
(`reports/quake_extended_aois.md`).

**Why it matters for BailaSAR:** the project's thesis — L-band sees through
clouds and canopy where optical/C-band fail — is literally demonstrated at the
epicenter. These AOIs are operational coverage, **not** part of the frozen
scorecard (that stays Eje Cafetero); the damage proxy over them carries the same
"proxy contrast, PROVISIONAL" caveats. No outside report or its statistics
informs this note — only the USGS event page, ASF search results and public
geography.
