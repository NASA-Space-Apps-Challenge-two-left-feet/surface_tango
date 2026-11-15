# Armenia boundary validation and neighborhood crosswalk

Issue #24 audit, prepared on `feat/quake-ground-truth` and published as a research handoff. Source snapshot completed at
2026-11-14T22:38:30.242793+00:00 (UTC); accessed 2026-11-14 in Bogotá.

**Outcome: diagnostic validation completed; boundaries are not accepted for the
scientific scorecard.** Geometry, attribution, coverage, and stable-ID concerns
remain. The crosswalk preserves source records and does not assign damage labels.

## Source and reproducibility

- [IGAC-hosted neighborhood layer](https://pruebassig.igac.gov.co/server/rest/services/SIG_QUINDIO/Ordenamiento_territorial/MapServer/1); municipality filter `IDMUNICIPIO='63001'`.
- [Same-service urban perimeter](https://pruebassig.igac.gov.co/server/rest/services/SIG_QUINDIO/Ordenamiento_territorial/MapServer/3).
- [Local audit script](ground_truth_armenia_audit.py).
- Snapshot manifest (local-only path: `local_cache/ground_truth/armenia_igac/20261114T223825410289Z/manifest.json`): exact request URLs and response SHA-256 checksums.
- Machine-readable summary (local-only path: `local_cache/ground_truth/armenia_igac/20261114T223825410289Z/audit/summary.json`): counts, versions, source and script checksum.

All quantities in the results below are **measured** from that snapshot, not
estimates of damage, official barrio totals, or eligible units. Denominators are
explicit below. These are full-snapshot diagnostics, so sampling confidence
intervals do not apply. No source radar granules or scenes were used.

```bash
uv run --no-project --python 3.11 \
  --with shapely==2.2.0 --with pyproj==3.7.2 --with matplotlib==3.11.2 \
  python reports/ground_truth_armenia_audit.py \
  --snapshot local_cache/ground_truth/armenia_igac/20261114T223825410289Z
```

Run without `--snapshot` to retrieve a new dated snapshot instead. The audit checks
checksums, source IDs before and after collection, and downloaded membership.
Membership was stable; the server does not guarantee an atomic geometry snapshot.
Raw data and CSV/image diagnostics stay in ignored `local_cache/`, outside git.

## Results

| Check | Measured result | Meaning |
|---|---|---|
| Download completeness | 364 features; all source IDs reconciled before/after download | Complete membership for this filtered snapshot, not proof of municipal coverage. |
| Meaningful names and communes | 7 whitespace-only names and 7 whitespace-only commune values among 364 records | Earlier raw-string checks missed these placeholders. They are missing attributes, not named neighborhoods. |
| Raw/normalized names | 348 distinct raw values; 348 distinct normalized values, each including a blank/whitespace group | Normalization removes accents, case, punctuation and repeated spaces only; no prefix removal or fuzzy merging. |
| Repeated nonblank names | 8 groups; 25 records across all repeated groups including the blank group | Multiple parts or naming collisions remain unresolved; all rows are retained. |
| Geometry validity | 362 valid and 2 invalid among 364 records | Two ring self-intersections; no repair applied. |
| Positive-area intersections | 291 unordered pairs among 362 valid records; invalid records excluded | Median pair intersection 0.000362591 m²; largest 2084.52 m². Tiny slivers may reflect rounding/reprojection; no tolerance or automatic acceptance was applied. |
| Equal geometries | 0 topologically equal pairs among intersecting valid records | Does not establish that repeated names are unique barrios. |
| Reference perimeter | 1 valid same-service perimeter feature | No municipal legal/event-date validation is implied. |
| Geometric coverage | Valid polygon union 17318821.07 m²; reference perimeter 31758427.83 m² | Areas calculated after projecting the GeoJSON download from EPSG:4326 to EPSG:9377. |
| Perimeter difference | 14453348.97 m² of perimeter outside the valid union; 13742.21 m² of valid union outside perimeter | Excludes invalid barrio geometry. This is a set difference, not a count of missing barrios or proof that every uncovered area should be a barrio. |

Invalid source records: `OBJECTID=71`, LA FACHADA, and `OBJECTID=223`, QUINDIO.
The largest intersections involve record `392`, AVENIDA CENTENARIO, and nearby
polygons. Road, park, stadium, settlement, and neighborhood names occur in the
source; feature type and evaluation-unit eligibility need explicit owner review.

The [Shapely diagnostics documentation](https://shapely.readthedocs.io/en/stable/manual.html#diagnostics)
explains the validity predicates used. A valid individual polygon does not imply
a nonoverlapping or complete partition. No dissolve, snap, buffer repair,
coordinate simplification, or duplicate deletion was performed. Union is used
only for the diagnostic area comparison; source polygons are preserved.

## Duplicate-name review queue

| Normalized name | Source record IDs | Commune values | Action |
|---|---|---|---|
| (missing name) | 302, 346, 352, 359, 374, 398, 401 | (missing commune) | Retain all records; manual identity review |
| ALCAZAR | 86, 333 | 10 | Retain all records; manual identity review |
| ASENTAMIENTO ACACIAS BAJO | 222, 280 | 2 | Retain all records; manual identity review |
| BLOQUES EL RETIRO | 393, 394 | 10 | Retain all records; manual identity review |
| CIUDADELA NUEVO ARMENIA | 127, 238, 267 | 3 | Retain all records; manual identity review |
| ESTADIO CENTENARIO | 377, 383 | 1 | Retain all records; manual identity review |
| LOS QUINDOS I Y II ETAPA | 200, 281 | 2 | Retain all records; manual identity review |
| NUEVA CECILIA | 378, 379 | 10 | Retain all records; manual identity review |
| PARQUE SUCRE | 385, 386, 388 | 10 | Retain all records; manual identity review |

Same name plus commune is not sufficient evidence to merge records. Source
`OBJECTID` identifies a record in this snapshot; it is not a certified, stable
municipal barrio ID.

## Damage-report crosswalk

The [municipal structural-inspection report](https://www.armenia.gov.co/comenzaron-visitas-y-ensayos-estructurales-en-edificios-afectados-por-el-sismo-en-armenia),
published 2026-11-11, supplies the reported names below. Names match the source
inventory after conservative normalization. They are candidate record associations,
not confirmed geolocations of the damaged buildings.

| Reported neighborhood | Snapshot record ID | Source name | Commune | Geometry valid? | Interpretation |
|---|---|---|---|---|---|
| Serranías | 152 | SERRANIAS | 2 | True | Unique name match for the report’s named damaged dwelling; building location and source vintage still require confirmation. |
| Corbones | 253 | CORBONES | 8 | True | Unique name match, but the reported building is between Corbones and Granada; assignment remains ambiguous. |
| Granada | 130 | GRANADA | 9 | True | Unique name match, but the reported building is between Corbones and Granada; assignment remains ambiguous. |

Each candidate polygon participates in positive-area intersection flags; counts
are in the CSV. All `damage_label` values remain `not_assigned`; the inventory’s
`damage_status` remains `unknown`. No row is encoded as an undamaged negative.
GRANADA is not matched to CONJUNTO TORRES DEL GRANADA.

The paths below identify artifacts retained in the original local research
worktree. They are intentionally absent from GitHub. To create a new snapshot,
run the audit command above; its timestamp and checksums identify that new
version rather than silently replacing the cited snapshot.

## Local artifacts

- All source records with normalized names and audit flags (local-only path: `local_cache/ground_truth/armenia_igac/20261114T223825410289Z/audit/neighborhood_crosswalk.csv`).
- Damage-report candidate crosswalk (local-only path: `local_cache/ground_truth/armenia_igac/20261114T223825410289Z/audit/damage_source_crosswalk.csv`).
- Duplicate-name queue (local-only path: `local_cache/ground_truth/armenia_igac/20261114T223825410289Z/audit/duplicate_names.csv`).
- Intersection review queue (local-only path: `local_cache/ground_truth/armenia_igac/20261114T223825410289Z/audit/overlaps.csv`).
- Boundary audit map (local-only path: `local_cache/ground_truth/armenia_igac/20261114T223825410289Z/audit/boundary_audit.png`), visually inspected locally. Highlighted candidate locations are representative polygon points, **not damaged-building coordinates**.

## Remaining acceptance requirements

Municipal adoption, event-date vintage, reuse terms, stable official IDs, missing
attribute records, repeated-name identities, invalid rings, substantive overlaps,
and reference-perimeter differences require resolution. Any corrected release must
be a separate versioned input; the raw snapshot must not be silently repaired.
Complete public damage-assessment coverage and the frozen scientific configuration
are still required for a scorecard. These diagnostics do not authorize co-event
radar viewing or change the preregistration gate.

The owner-provided `.secrets.baseline` is inherited from `main`. This handoff
publishes the report and helper only; raw data and derived artifacts stay local.
No authority was contacted and scientific acceptance remains pending.
