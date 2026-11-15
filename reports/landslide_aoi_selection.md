# Valle de Aburrá landslide AOIs — selected from Medellín's POT prioritizations

**What this is.** The most relevant vulnerable AOIs for the landslide lane, selected
from the *prioritizations already made by the Medellín authorities*: the city
commissioned **detailed** landslide-risk studies (POT resolutions) only for polygons
flagged high-risk, so the study set *is* the prioritization. Grounded in the SGC
framework (*amenaza · vulnerabilidad · riesgo*; `knowledge/graphrag/`). Public
official sources, cited by resolution.

**Evidence note.** Risk categories, comunas and sectors below are **measured** — read
from the official study text (`knowledge/graphrag/ingest.py` extraction, provenance
in `local_cache/graphrag/input/_provenance.json`). Study coordinates are in
**MAGNA-SIRGAS Medellín-local** (e.g. La Picacha 828420 E / 1181464 N); the WGS84
bounding boxes are marked **(estimate)** — comuna/sector-scale extents for demo
framing — pending exact reprojection of each study's polygon (the local CRS is not
yet confirmed, and the detailed studies ship as PDFs with no vector layer; see
"Coordinate precision" below). No coordinate is fabricated.

## Tier 1 — prioritized vulnerable AOIs (detailed-risk studies)

| # | AOI | Comuna / sector | Risk category *(measured)* | Why it ranks | Source *(public)* |
|---|---|---|---|---|---|
| 1 | **La Picacha** | 16 · Belén (SW) | **Riesgo alto no mitigable** + amenaza alta (25×); also amenaza por avenidas torrenciales | Largest detailed study (484 pp.); combined mass-movement + torrential hazard along quebrada La Picacha; explicit *no mitigable* zones | Res. 202350105375 de 2023 |
| 2 | **Parque Popular** | 1 · Popular (NE) | Amenaza alta (10×); riesgo alto mitigable | Dense hillside informal settlement on the NE ladera; classic high-exposure slope | Estudio de detalle Parque Popular |
| 3 | **Carabineros** | 5 · Castilla / Robledo (NW) | Amenaza de detalle por movimiento en masa | NW ladera | Res. 202350105991 |
| 4 | **Parque Complex 2** | Santa Elena (E) | Detalle por movimiento en masa | Most recent study (2024), E corregimiento edge | Res. 202450021403 |
| 5 | **Colegiatura** | Santa Elena / Buenos Aires (E) | Amenaza de detalle | E hillside | Informe de amenaza Colegiatura |

## Tier 2 — historic / high-impact demo AOIs

| # | AOI | Comuna / sector | Why it's a strong demo AOI | Source |
|---|---|---|---|---|
| 6 | **Villatina** | 8 · Villa Hermosa (E) | Site of the **1987 Villatina landslide**, one of Colombia's deadliest mass-movement disasters — iconic, high narrative impact | EstudioSantaElena barrio report *Villatina-Torcoroma* |
| 7 | **Santa Elena barrios** | E ladera | Loreto, San Antonio, Villa Liliam, Villa Mercedes — clustered hillside reports | EstudioSantaElena-2016 |

**City-wide prioritization layer.** *Estudios de riesgo de detalle*, **Res. 202250081537
de 2022** (916 pp.), zonas con condición de riesgo across the comunas — the master
layer the detailed studies draw from.

## Recommended demo AOIs (3)

1. **La Picacha** (Comuna 16) — the clearest *riesgo alto no mitigable* case, with both
   landslide and torrential hazard; strongest evidence base.
2. **Parque Popular** (Comuna 1) — the archetypal dense NE-ladera exposure.
3. **Villatina** (Comuna 8) — the historic 1987 disaster; the demo's emotional anchor.

All three are Valle de Aburrá hillside (ladera) zones where NISAR L-band InSAR
coherence/kinematics is the relevant signal — complementing the SGC-grounded agent.

## Coordinate precision (next step)

The detailed studies are PDFs with maps as images; no shapefile/geopackage ships in
the corpus (204 PDFs, 0 vector layers). Exact WGS84 AOI polygons therefore come from:
1. **GraphRAG extraction** of each study's coordinate lists + zonation (Phase B, once
   Azure OpenAI is wired), then reprojecting the MAGNA-SIRGAS Medellín-local
   coordinates — **after confirming the local CRS** (origin/false E-N) from an
   authoritative source; and/or
2. digitizing the zonation polygons from the study figures.

Until then the AOIs above are committed at comuna/sector scale, clearly marked
*(estimate)*, which is sufficient for demo framing and honest under the evidence rule.
