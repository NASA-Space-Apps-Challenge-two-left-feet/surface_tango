---
title: Manizales exposes municipal polygons but damage coverage is not scoring-ready
status: verified
source: https://sig.manizales.gov.co/wadmzl/rest/services/20_WEB/2021_consulta_catas_urbano_web/FeatureServer/1
accessed: 2026-11-14
quote: "esriGeometryPolygon"
used_in: [reports/ground_truth.md]
verified_by: "Codex, public metadata inspection; no human approval implied"
supersedes: null
---

The municipal-domain service returned neighborhood polygon metadata and a polygon
in a one-record GeoJSON query. The schema includes `OBJECTID`, `BARRIOS`, and
`Id_Comuna`; the advertised display field is absent from that schema. Stable unit
identity, local CRS, full geometry validity, event-date coverage, and terms need review.

The [rural assessment](https://centrodeinformacion.manizales.gov.co/autoridades-mantienen-seguimiento-a-las-afectaciones-en-la-zona-rural-tras-el-sismo/)
dated 2026-08-11 and [recovery update](https://centrodeinformacion.manizales.gov.co/tres-meses-despues-del-sismo-del-10-de-agosto-asi-va-la-recuperacion-de-manizales/)
dated 2026-11-09 offer named-sector damage leads. They do not establish a complete
neighborhood assessment universe. Rural sectors require their own official unit
mapping; aid eligibility cannot substitute for the preregistered building-damage label.
