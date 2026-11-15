---
title: Armenia government-hosted polygons require identity and topology review before scoring
status: verified
source: https://pruebassig.igac.gov.co/server/rest/services/SIG_QUINDIO/Ordenamiento_territorial/MapServer/1
accessed: 2026-11-14
quote: "esriGeometryPolygon"
used_in: [reports/ground_truth.md, reports/ground_truth_armenia_boundaries.md]
verified_by: "Codex, snapshot audit and visual inspection; no human approval implied"
supersedes: docs/kb/data-ground-truth-armenia-igac.md
---

The complete filtered snapshot reconciles with public source IDs. It contains
whitespace-only name/commune values, repeated names, invalid rings, and positive-area
intersections. Diagnostic coverage differs from the same-service urban perimeter.
Measured counts, methods and snapshot checksums are in the audit report.

Conservative normalization produces unique record-name candidates for the municipal
damage report’s Serranías, Corbones and Granada references. A name match is not a
building location. Between-neighborhood assignment remains ambiguous. Source records
are preserved without repair, merging or negative damage labels. Government hosting
does not establish municipal adoption, event-date validity, stable barrio IDs or
complete damage-assessment coverage; scientific acceptance remains pending.
