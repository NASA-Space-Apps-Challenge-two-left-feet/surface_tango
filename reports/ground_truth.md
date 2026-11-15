# Issue #24 — Neighborhood damage sources and official boundaries

**Research handoff:** organized for team review; scientific acceptance remains pending.
**Publication branch:** `codex/issue-24-ground-truth`. **Sources last inspected:** 2026-11-14, Bogotá time.
**Target event:** 2026-08-10 earthquake; Pereira, Armenia, and Manizales.

## Finding and decision

**The scorecard is uninformative with the evidence verified so far.** We located
public damage reports and queryable boundary candidates, but did not verify a
complete neighborhood damage-assessment dataset for any target city. Official
boundary adoption, event-date validity, and unit identity also remain unresolved.
This describes the sources inspected; it does not establish that other data do not exist.

The research report and source register can be reviewed now. A usable scientific
scorecard cannot yet be produced. Unreported, unvisited, and uncertain neighborhoods
remain **unknown**, not undamaged. No damage labels, prevalence, evaluated-unit
count, precision, or ranking results were generated.

This records the fallback allowed by plan 02-02. It does not close the GitHub issue
or make the official gate decision. Plan 02-03 owns the power check and headline
entry in `validation/README.md`; plan 02-04 owns the configuration freeze. Neither
shared file was changed. The existing hour-four timebox is not restarted here;
its start was not supplied, so this report does not claim that deadline was met.

## What we found by city

| City | Damage evidence | Boundary evidence | Still missing before scoring |
|---|---|---|---|
| Pereira | Municipal council recovery report describes earthquake damage and affected sectors. | Queryable SIGPER neighborhood polygons. Metadata, count and a geometry sample inspected. | Public assessment annex with neighborhood coverage; validated unit IDs, full geometry checks, adoption/vintage and reuse terms. |
| Armenia | Municipal reports summarize assessments and explicitly name Serranías. A building described as between Corbones and Granada remains ambiguous. | Complete filtered snapshot of the IGAC-hosted neighborhood layer audited; municipal SIG catalog located but access is restricted/unavailable. | Assessment coverage, municipal adoption/vintage and reuse confirmation, and resolution of identity/geometry flags. |
| Manizales | Municipal reports name damaged urban neighborhoods and rural sectors. | Queryable municipal-domain neighborhood layer. Metadata, count and a geometry sample inspected. | Complete assessment annex, urban/rural unit mapping, stable IDs, full geometry checks, adoption/vintage and reuse terms. |

## Damage-source register

The entries below are sources and leads, **not an accepted label dataset**.
Publication dates are publisher-reported; an inspection cutoff must be established
separately before using a source for evaluation.

| Source | Publication date | What it supports | Limitation / next evidence needed |
|---|---|---|---|
| [Pereira council recovery report](https://concejopereira.gov.co/es/ieventos/ver/3052/concejo-de-pereira-analiza-avances-de-infraestructura-y-exige-resultados-concretos-en-la-atencion-de-la-emergencia-por-el-terremoto/) | 2026-11-11 | Primary municipal recovery and damage context; lead to the infrastructure/DIGER assessment. | No complete neighborhood label table or assessment coverage verified. Locate a public nonpersonal annex. |
| [Armenia assessment update](https://www.armenia.gov.co/armenia-amplia-la-evaluacion-de-danos-y-avanza-en-el-registro-de-familias-damnificadas-tras-el-sismo) | 2026-08-21 | Refers to Official Report No. 20 and describes assessment activity. | Aggregate information cannot supply neighborhood labels. Locate its public coverage annex. |
| [Armenia structural-inspection update](https://www.armenia.gov.co/comenzaron-visitas-y-ensayos-estructurales-en-edificios-afectados-por-el-sismo-en-armenia) | 2026-11-11 | Explicit earthquake-damage lead for Serranías; another building is between Corbones and Granada. | Name matching is possible; exact neighborhood assignment and complete assessment coverage are not established. |
| [Manizales rural assessment](https://centrodeinformacion.manizales.gov.co/autoridades-mantienen-seguimiento-a-las-afectaciones-en-la-zona-rural-tras-el-sismo/) | 2026-08-11 | Named rural-sector damage reports. | Rural sectors must be mapped to their own official units; absence of a report is not an assessed negative. |
| [Manizales one-month update](https://centrodeinformacion.manizales.gov.co/un-mes-despues-del-sismo-se-mantienen-las-acciones-de-atencion-demolicion-y-reconstruccion/) | 2026-09-10 | Names urban damage sectors, including Chipre, Milán, El Carmen and Campo Amor. | Roads, the historic center, sectors and communes are mixed with barrio names. Resolve unit identity before joining. |
| [Manizales recovery update](https://centrodeinformacion.manizales.gov.co/tres-meses-despues-del-sismo-del-10-de-agosto-asi-va-la-recuperacion-de-manizales/) | 2026-11-09 | Names locations associated with demolition cases. | Aid eligibility and demolition proceedings do not replace the frozen event-caused building-damage definition or coverage evidence. |
| [Escuela Colombiana de Ingeniería field-assessment report](https://www.escuelaing.edu.co/es/minisitios/impacto-en-territorio/) | Not established | Primary technical account of assigned inspections in the target cities; potential route to public inspection annexes. | The report explicitly limits its coverage and describes ongoing consolidation. Habitability/vulnerability alone is not an event-damage label. |

City totals, household/aid registers, deaths, shelter locations, and road closures
were not converted into damaged-building labels. No personal addresses, occupant
names, or beneficiary records are retained in the report or crosswalk.

## Boundary-source register

All record counts below are **measured service checks**, not official totals of
unique barrios or counts of eligible evaluation units. No radar granules apply.

| Source | Checks completed and denominator | Acceptance status |
|---|---|---|
| [Pereira SIGPER layer](https://services3.arcgis.com/Zdpg0E6lri7EggIc/arcgis/rest/services/Barrios_del_municipio_de_Pereira/FeatureServer/0), [item](https://www.arcgis.com/home/item.html?id=900f6ace1d54413d8056494b749e25bf) | 486 feature records from `where=1=1`; polygon metadata and a one-record GeoJSON sample. Candidate IDs `ID_BAR`/`CODBAR`, name `NOMBRE`. | Municipal portal attribution supported by the [city announcement](https://www.pereira.gov.co/publicaciones/1442/propuesta-del-gobierno-de-la-ciudad-fue-elegida-en-convocatoria-mundial-del-programa-de-las-naciones-para-los-asentamientos-humanos-un-habitat-y-geo/). Full adoption/vintage, unit uniqueness, geometry and terms remain pending. |
| [Manizales municipal layer](https://sig.manizales.gov.co/wadmzl/rest/services/20_WEB/2021_consulta_catas_urbano_web/FeatureServer/1) | 116 feature records from `where=1=1`; polygon metadata and a one-record GeoJSON sample. Schema includes `OBJECTID`, `BARRIOS`, `Id_Comuna`; advertised `ID_BARRIO` is absent from the reported fields. | Government-domain hosting verified. Stable unit keys, local CRS, extent, full geometry, vintage and terms need review. |
| [Armenia IGAC-hosted layer](https://pruebassig.igac.gov.co/server/rest/services/SIG_QUINDIO/Ordenamiento_territorial/MapServer/1) | 364 records filtered by `IDMUNICIPIO='63001'`; full downloaded membership reconciled to source IDs. Geometry and names audited. Native CRS EPSG:9377. | Government test-host candidate; not certified municipal/event-date boundaries. Defects and release provenance remain unresolved. See the detailed audit below. |

The earlier Armenia [academic upload](https://www.arcgis.com/home/item.html?id=6679b075b29f48a2806b3f4fd8a48750)
remains unaccepted as official: publisher attribution and license fields were empty.
It has not replaced the government-hosted candidate.

### Armenia validation and neighborhood crosswalk

The [boundary audit report](ground_truth_armenia_boundaries.md) contains the full
methods, measured results, snapshot manifest, review queues and local artifact links.
Among the **364 downloaded source records (measured)**:

- **362** have valid individual geometry; **2** have ring self-intersections.
- **7** have whitespace-only name and commune values.
- **8** nonblank normalized names occur on multiple records. No records were merged.

These checks do not establish a complete, nonoverlapping municipal partition.
Positive-area intersections and differences from the same-service urban perimeter
are documented for review. Small intersections can reflect numerical slivers;
uncovered perimeter area is not automatically a missing barrio.

| Name in the municipal damage report | Candidate source record | Commune | Crosswalk decision |
|---|---|---|---|
| Serranías | `OBJECTID=152`, `SERRANIAS` | `2` | Unique normalized-name candidate with valid individual geometry; building location, source vintage and topology review remain pending. |
| Corbones | `OBJECTID=253`, `CORBONES` | `8` | Unique name candidate; the building is described as between Corbones and Granada. Do not assign it to either or both without location evidence. |
| Granada | `OBJECTID=130`, `GRANADA` | `9` | Same location ambiguity. Do not confuse `GRANADA` with `CONJUNTO TORRES DEL GRANADA`. |

Source IDs are snapshot record keys, not certified stable official barrio IDs.
All inventory damage states remain `unknown`, and all candidate damage labels
remain `not_assigned`. The CSV crosswalks and audit map are linked from the
boundary audit report and stored in ignored `local_cache/`.

## Sources that cannot establish confirmed ground truth

| Source or access path | Observed limitation | Treatment |
|---|---|---|
| [3iS Pereira map](https://3is.org/emergenciaslatam/terremoto_choco/img/Mapa_Pereira_Barrios_Afectados.png), printed 2026-08-19 | Credits Copernicus EMS EMSR916; disclaimer calls the information indicative and requires field verification. | Satellite-derived lead only; not independent confirmed field ground truth. |
| [3iS Manizales map](https://3is.org/emergenciaslatam/terremoto_choco/img/Mapa_Manizales_Barrios_Afectados.png), printed 2026-08-20, updated 2026-09-02 | Credits municipal risk management and UNOSAT/UNITAR; marked preliminary and not field-validated. | Possible damage is not a confirmed positive; uncolored areas are not negatives. |
| [SIG Armenia hub item](https://www.arcgis.com/home/item.html?id=8a397338268244cbb30535a91818e154) and [neighborhood web map](https://www.arcgis.com/home/item.html?id=410793ef775d46d293299424ddddf1f3) | Hub page returned HTTP 404; map data returned JSON 403, subscription disabled. Neighborhood service item `c0d862bcfbe54a85ae2c65a89fc425c4` was cataloged under `SIGARMENIA_EDITOR` but its service returned JSON 499, token required. | Municipal recovery path; no restricted data obtained and no access controls bypassed. |
| [Earlier Armenia catalog candidate](https://www.arcgis.com/home/item.html?id=b598297780f14371b55c6e84ef773ec6) | Its service returned JSON 400, invalid URL. | Not an accepted download. |
| [Pereira document archive](https://www.pereira.gov.co/documentos/1827/noviembre-2026/) | Search indexing identified demolition resolutions; page reader returned HTTP 403. | Unread resolution/annex lead only; no labels derived. |
| [Pereira neighborhood-by-commune table](https://www.datos.gov.co/widgets/ebsr-7cb7) | Possible name crosswalk; polygon content not verified. | Not a boundary replacement. |

Both 3iS maps were visually inspected. Access errors do not establish that data
are absent. The municipal Pereira open-data page also returned HTTP 403; its
portal had no readable text, and the Armenia planning page returned HTTP 502.
These are access observations from the review, not current availability guarantees.

## What is still missing and who can act

| Missing item | Required evidence / next action | Responsible role |
|---|---|---|
| Neighborhood damage coverage | Public, nonpersonal assessment annex with event attribution, cutoff, unit identifiers, definition, assessment scope and reuse terms. Distinguish assessed negatives from unknown/unvisited records. | Issue #24 research / source-owning municipal risk or infrastructure authority |
| Boundary adoption and event-date validity | Municipal publication or confirmation of the boundary release, adoption, date and reuse terms; recover the unavailable SIG Armenia export if possible. | Municipal planning / boundary publisher; issue #24 records the evidence |
| Validated unit identities | Resolve unnamed records, repeated names, source feature types and stable official IDs; keep an explicit municipality-plus-unit crosswalk. | Boundary publisher / data owner, with issue #24 review |
| Geometry issues and ambiguous locations | Review invalid rings, substantive overlaps and perimeter differences; obtain location evidence for the Corbones/Granada building. Any corrected release stays separate from the raw snapshot. | Boundary and assessment data owners |
| Official gate and headline decision | Use this report to record an uninformative outcome if gaps persist at the existing timebox. Compute power only from accepted polygons and labels. | Plan 02-03 owner |
| Frozen configuration | Fill accepted sources/pair IDs, freeze and record the required hash before co-event radar viewing. | Plan 02-04 owner |

No authority was contacted in this task. No request was sent on the user's behalf.
The first unresolved research action is obtaining the public assessment annexes
and municipal boundary release evidence; the local findings can be reviewed now.

## Local deliverables, checks and limits

- Main issue deliverable: this report plus `docs/kb/data-ground-truth-*.md` source notes.
- Supporting work: [Armenia boundary audit and crosswalk](ground_truth_armenia_boundaries.md).
  The existing `.py` helper is an optional diagnostic tool, not a requirement of issue #24.
- Source notes preserve supersession: earlier Armenia candidates are superseded by the
  [current validation note](../docs/kb/data-ground-truth-armenia-validation.md).
- Search coverage: municipality/event-specific public searches, primary municipal
  reports, technical field-report review, ArcGIS metadata, public GIS queries and
  visual map inspection. This was not an exhaustive archival search.
- Count reproduction for Pereira/Manizales: issue a read-only GET to the exact
  layer `/query` URL with `f=json`, `where=1=1`, `returnCountOnly=true`. These counts
  have no scientific eligibility interpretation. Armenia snapshot commands and
  checksums are in the supporting audit report.
- Historical local validation at `cc4de1b`: the earlier issue worktree passed its
  offline tests and hooks. Publication checks are recorded in `status/quake.md`;
  historical test counts are not a claim about this branch.
- The baseline and locked dependencies came from `main`; neither is modified here.
- Publication includes the research report, source notes and optional diagnostic
  helper. Raw snapshots and generated GIS artifacts remain ignored local files.
  No authority was contacted and no GitHub issue is closed by this handoff.
