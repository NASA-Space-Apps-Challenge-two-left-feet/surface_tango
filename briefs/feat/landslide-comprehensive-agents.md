# Brief: feat/landslide-comprehensive-agents — a complete landslide risk assessment (agent: grok2)

- **Goal:** extend the landslide lane from today's single InSAR noise-floor verdict into a **comprehensive, SGC-grounded landslide risk assessment** per AOI, with three complementary analyst sub-agents — **geologist**, **geomorphologist (with photogrammetric analysis)**, and **groundwater / hydrogeology analyst** — that quantify the *conditioning factors* (geologic profiles, geomorphology) and the *triggers* (heavy rain, groundwater-level variation, loads). Together they give the big picture: one coherent amenaza → vulnerabilidad → riesgo story for each Valle de Aburrá AOI (La Picacha, Aburrá, …), in the SGC framework. Hazard-modeling / landslide lane (LEONOB2014).
- **Issue:** #33 (follow-up: comprehensive landslide analysis). **Reference:** `agents/orchestrator.py` (`domain_node`, `build_and_run_multi_hazard_graph`), `mcp_servers/gee_fusion_mcp.py` (`analyze_landslide_kinematics`, the `@mcp.tool` pattern), `mcp_servers/evidence.py` (the #122 evidence envelope), `gee_math/landslide_insar_math.py` (the existing InSAR math), `knowledge/graphrag/retrieve.py` (`ground()` — the SGC-methodology grounding), `reports/landslide_aoi_selection.md`, `config/preregistered.yaml`.

## The conceptual frame (SGC, public)

The SGC *Guía metodológica … escala detallada* (public; grounded in `knowledge/graphrag/`) defines **Riesgo = Amenaza × Vulnerabilidad**. Amenaza ← *factores condicionantes* (geología, geomorfología, inventario de movimientos, cobertura/uso del suelo, modelo geológico-geotécnico) + *factores detonantes* (**lluvia, sismo, nivel freático**) → zonificación + **probabilidad de falla**. These three analysts fill that frame with **measured** evidence; each grounds its reasoning by querying the GraphRAG for the relevant SGC method before interpreting.

## What to build — three analysts, their MCP tools, their math

Each analyst = a pure-logic `gee_math/` module (the computation, unit-tested with hand-computed expected values listed in `validation/ALLOWLIST.md`) + an `@mcp.tool` in `mcp_servers/gee_fusion_mcp.py` returning the **#122 evidence envelope** (`state` ∈ live/cached/not cached/unavailable/error, `calibrated`, `data`, `provenance` with source IDs, `unavailable`/`error`). The landslide `domain_node` calls them and the GraphRAG grounding; the bulletin agent renders prose with `{placeholders}` — **agents never produce numbers**.

### 1. Geologist → `analyze_landslide_geology(aoi)` · `gee_math/landslide_geology.py`
- The **conditioning lithology / geologic units** under each AOI, from **public geology** (SGC Atlas Geológico de Colombia open feature layer, or a GEE public geology/lithology asset — pick one, record its asset ID + dates in provenance). Per AOI: the dominant units, their engineering-relevant class (rock/soil/colluvium), and structural context (faults/contacts intersecting the AOI).
- Feeds SGC *"factores condicionantes: geología para ingeniería"* and the geologic profile the hydrogeology analyst needs.

### 2. Geomorphologist (+ photogrammetry) → `analyze_landslide_geomorphology(aoi)` · `gee_math/landslide_geomorphology.py`
- **Geomorphology from the terrain:** slope, aspect, curvature, relative relief and geomorphological units from a public DEM (FABDEM / MERIT already in the cache pipeline) — the SGC geomorphology factor.
- **Photogrammetric sub-analysis** (standard multi-epoch photogrammetry, public method): an **aerial-photo / orthoimage history** of the AOI (IGAC / Colombia en Mapas public frames, or multi-date optical), each epoch **registered to a recent orthophoto** (space resection / co-registration), yielding **multi-epoch surface displacement** and, where a gully exists, **gully-head retreat** (distance/time). Tie it to the **NISAR L-band InSAR** coherence/kinematics already computed (`landslide_insar_math.py`) — photogrammetry = the long-record decadal signal, InSAR = the recent mm-scale signal; report both, note where they agree/disagree.
- Feeds SGC *"geomorfología + inventario/actividad de movimientos en masa"*.

### 3. Groundwater / hydrogeology analyst → `analyze_landslide_hydrogeology(aoi)` · `gee_math/landslide_hydrogeology.py`
This is the **trigger + stability** core. Standard public geotechnical methods (cite the method, not any outside project):
- **Heavy-rain trigger (wetting front):** rainfall → infiltration → **wetting-front depth** over time (Green-Ampt / the SGC guide's infiltration function); flag when the wet front reaches the likely failure surface → shallow-slide trigger. Use public rainfall (CHIRPS already in the stack) per AOI.
- **Groundwater-level variation:** water-table rise/drawdown → change in **pore pressure / effective stress** on the slope; report the stability sensitivity to a given water-table rise.
- **Slope stability:** the **Culmann plane-wedge** method → **critical height** / factor of safety for the AOI's geologic profile (from analyst 1) + geometry (slope from analyst 2), with **SPT-N → shear-strength (c, φ)** correlations where SPT is available, and **load quantification** (built-up load on the slope from the WorldCover/footprint layer) added to the driving stress.
- Feeds SGC *"factores detonantes (lluvia, nivel freático)"* → *"probabilidad de falla"*.

## Integration & the big picture

- The landslide `domain_node` runs: InSAR kinematics (existing) + the three new analysts, each grounding its interpretation via `knowledge/graphrag/retrieve.ground("<SGC method question>", method="local")`, then the **cross-hazard synthesis** composes the coherent per-AOI risk narrative (bilingual bulletin, `{placeholders}` only).
- Every AOI panel keeps the **honest-state** rule: where a datum is missing (no DEM/SPT/photo history for an AOI), the tool returns `not cached`/`unavailable` with the reason — **never a synthetic value**.
- Numbers are **measured**: each carries its command, source asset/granule IDs, denominators, and (where applicable) a confidence/interval. Nulls are reported as nulls.

## Acceptance

- `make ci` green; hand-written-array unit tests (listed in `validation/ALLOWLIST.md`) for each math module: the wetting-front depth, the Culmann critical height, the SPT-N correlation, the geomorphometric derivatives — with hand-computed expected values and no network.
- Three `@mcp.tool`s return valid #122 envelopes; a short `Client(mcp)` call shows each serving for `aburra` and `la_picacha` (measured where data exists, `not cached`/`unavailable` otherwise — honestly).
- `reports/landslide_comprehensive.md`: per AOI, the geology units, the geomorphology + photogrammetric displacement / gully retreat, the rain-trigger wetting front, the groundwater sensitivity, and the Culmann stability — every number *(measured)* with its command + source IDs, the SGC method it grounds in, and honest gaps. One-line coherent risk verdict per AOI, PROVISIONAL, never "beats baseline".
- The landslide bulletin renders the comprehensive narrative from tool outputs only (agents emit no numbers); README landslide row + diagrams updated in the same PR.

## Rules

- **No synthetic data**: a missing DEM tile/SPT value/photo frame stays missing (NaN, marked `missing`, shown "no data"); never zero-fill or invent.
- Measured numbers carry denominators + source IDs; frozen thresholds (if any new ones) go in `config/preregistered.yaml` only — do not edit the frozen file after freeze; operational params in `config/bailasar.yaml`.
- **Public data only** (SGC geology, IGAC/Colombia-en-Mapas photos, CHIRPS, FABDEM/MERIT, WorldCover, NISAR). No personal data. No NASA logos.
- Ground every method in the SGC guide via the GraphRAG (`knowledge/graphrag/retrieve.ground`) before interpreting; cite the standard geotechnical method by name (Green-Ampt, Culmann, SPT-N), not any outside project.
- Earth Engine only via `gee_math/ee_session.init_ee()`; foreground long jobs; a stalled granule → `missing`; don't `.resample("nearest")`.
- Files you may touch: `gee_math/landslide_geology.py`, `gee_math/landslide_geomorphology.py`, `gee_math/landslide_hydrogeology.py` (new), `mcp_servers/gee_fusion_mcp.py` (add the three tools only), `agents/orchestrator.py` (landslide node wiring only — do not change other lanes or the graph shape), `tests/test_landslide_*.py`, `reports/landslide_comprehensive.md`, `validation/ALLOWLIST.md` (append the new pure-logic test arrays), this brief. **Out of scope:** the frozen scorecard, the quake/flood lanes, the MCP transport, `config/preregistered.yaml` after freeze, the frontend.
- `make sync` before each commit. Do **not** push, merge, switch branches, reset, stash, open PRs, or run `gh` — the orchestrator (LEONOB2014) reviews and merges. When something outside this brief is needed, write `BLOCKED: <reason>` in `status/<lane>.md` and stop; never improvise.

## If blocked

Write `BLOCKED: <reason>` and stop — e.g. a public geology/SPT/photo source is not available for an AOI (then the tool returns `unavailable` honestly), or a method needs a frozen parameter not yet pre-registered (ask the orchestrator).

## Report (append when done)

Per AOI and per analyst: the measured outputs with commands + source IDs + denominators, the SGC method each grounds in, the honest gaps (`unavailable`/`not cached`), and the PROVISIONAL per-AOI risk verdict with its caveats.
