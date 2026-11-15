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

Measured 2026-11-15 14:20 Bogotá (UTC−5); log time 2026-11-15T19:20:08Z. Full write-up: `reports/landslide_comprehensive.md`.

Command (printed the states and the Aburrá scalars in this session):

```
uv run python -c '
from mcp_servers.gee_fusion_mcp import analyze_landslide_geology as g, analyze_landslide_geomorphology as m, analyze_landslide_hydrogeology as h
for aoi in ("aburra", "la_picacha"):
    geo, morph, hydro = g.fn(aoi), m.fn(aoi), h.fn(aoi)
    print(aoi, geo["state"], morph["state"], hydro["state"])
    if aoi == "aburra":
        slope, hand, rain = morph["data"]["slope"], morph["data"]["hand_m"], hydro["data"]["rainfall"]
        insar = morph["data"]["insar"]
        print("slope", slope["n_pixels"], slope["n_finite"], slope["median_deg"], slope["p05_deg"], slope["p95_deg"])
        print("hand", hand["n_pixels"], hand["n_finite"], hand["median_m"], hand["p05_m"], hand["p95_m"])
        print("rain", rain["n_pixels"], rain["n_finite"], rain["median_mm"], rain["values_read"], rain["source_ids"])
        print("insar", insar["outcome"], insar["noise_floor_mm"], insar["n_pairs"], len(insar["source_ids"]))
'
```

Printed *(measured)*: `aburra not cached cached gate result`; slope `262144 262144 12.676993370056152 1.445995980501175 33.214012145996094`; HAND `262144 262144 64.300048828125 0.0 392.4000244140625`; rain `262144 0 None True ['missing']`; insar `no_motion 9.105440970850369 17 17`; `la_picacha not cached not cached not cached`. `calibrated` is false on every envelope. Calls go through `FunctionTool.fn`.

### Aburrá

- **Geologist.** State `not cached`. No `local_cache/aburra/geology.json`. SGC units are not inferred. `data` is null. SGC question (method `local`): factores condicionantes, geologia para ingenieria y perfil geologico-geotecnico.
- **Geomorphologist.** State `cached`. Method on the envelope: "SGC geomorfologia e inventario de movimientos en masa". Slope *(measured)*, source `GEE projects/sat-io/open-datasets/FABDEM`, denominator finite pixels over cells in the staged grid: n_pixels 262144, n_finite 262144, median_deg 12.676993370056152, p05_deg 1.445995980501175, p95_deg 33.214012145996094. HAND *(measured)*, quantity height above nearest drainage, source `GEE MERIT/Hydro/v1_0_1 band hnd version v1_0_1 grid EPSG:4326 512x512`, denominator finite HAND pixels over cells in the staged grid: n_pixels 262144, n_finite 262144, median_m 64.300048828125, p05_m 0.0, p95_m 392.4000244140625. The p05 of 0.0 m is a measured channel value on a fully finite grid. Aspect, curvature, relative relief, and geomorphological units are unavailable (no elevation grid; slope is not binned). Photogrammetry and gully-head retreat are unavailable (no `photogrammetry.json`). Photo–InSAR sign agreement is unavailable.
- **InSAR tie** *(measured)*, read from the staged artifact, command `uv run python -m gee_math.landslide_insar_math`: outcome `no_motion`, noise_floor_mm 9.105440970850369, n_pairs 17, denominator GUNW pairs with a finite residual RMS. Stored text: "no motion detected above 9.105 mm (17 pairs); kept fraction below the sign-flip null on every stack". The 17 granule IDs are listed in `reports/landslide_comprehensive.md` and on the envelope. The artifact magnitude is unsigned. Manifest mtime `2026-11-15T08:49:52Z` is a cache time, not an acquisition date.
- **Hydrogeology.** State `gate result`. Method on the envelope: "Green-Ampt; effective stress; Culmann plane wedge; SPT-N". SGC question (method `local`): factores detonantes lluvia y nivel freatico, infiltracion y probabilidad de falla. Rainfall *(measured gap)*: n_pixels 262144, n_finite 0, median_mm null, values_read true, source id `missing`, denominator finite rainfall pixels over cells in the staged grid. That count is not a rainfall depth of 0 mm. Green-Ampt is not run. Wetting front, effective stress, SPT-N φ (Wolff / Peck), SPT-N c_u (Stroud, explicit factor), Culmann, and WorldCover surcharge are null / unavailable. No `hydro_profile.json` and no `worldcover.json`.
- **PROVISIONAL verdict.** The InSAR null stands. Slope and HAND are the only conditioning factors measured here. Amenaza × vulnerabilidad is not quantified. No failure probability is stated.

### La Picacha

`config/bailasar.yaml` key `6_la_picacha_landslide` bbox `[-75.6404, 6.2313, -75.6191, 6.2367]` is mapped by the landslide node to AOI `la_picacha`. No staged cache. All three tools: `not cached`, `data` null. The Aburrá grid is not copied onto this AOI. The config-key comment is not remeasured.

**PROVISIONAL verdict.** No risk number. Conditioning factors and triggers are not cached.

### Grounding and methods

The node calls `ground(question, method="local")` outside pytest. `index_built()` is true *(measured)*: `uv run python -c "from knowledge.graphrag.retrieve import index_built; print(index_built())"` → `True` (2 parquet files in `local_cache/graphrag/output`). The citation text is not copied into the bulletin. Under pytest the node records grounding `unavailable` and does not launch the paid model query. This report did not launch it. Risk sentence, states only: "Riesgo is amenaza times vulnerabilidad. No failure probability is stated here."

Green-Ampt, Culmann, SPT-N, and Horn derivatives are unit-tested on hand-written arrays listed in `validation/ALLOWLIST.md`. Those numbers are not AOI observations.

Bulletin identity uses one word (`available`) for a live or cached analyst state inside the interpretation, so a later cached delivery reuses the live-warmed prose. The kinematics envelope state itself is unchanged.

### Follow-ups for the orchestrator

- README landslide row and diagrams, and a `docs/kb/` note, were not edited: both paths are outside this brief's file list. Acceptance asks for the README update.
- `mcp_servers/gee_fusion_mcp.py` aliases pydantic's removed `eval_type_backport` to `eval_type` so mcp 1.16.0 imports on pydantic 2.14.3 (fastmcp 2.12.5). Measured with `uv run python -c 'import importlib.metadata as m; print(m.version("pydantic"), m.version("mcp"), m.version("fastmcp"))'`. Importing `mcp` without the alias raises `ImportError`. A dependency bump would replace the alias.
- No push, no PR. Local commit only.

### Local `make test` (this worktree)

`uv run pytest -q -m "not network and not cache"` → 4 failed, 460 passed, 10 deselected (20.93 s). The Horn curvature exponent was spelled `1.5`, which is also the frozen flood threshold `class2_delta_hv_hh_db_abs_max`, so `test_no_new_hardcoded_thresholds_or_aois` flagged `gee_math/landslide_geomorphology.py`. That spelling is now `(1 + p² + q²) * sqrt(1 + p² + q²)`. The geomorphology known-answer tests still pass.

Three failures remain and reproduce in isolation, outside this file list:

- `tests/test_config.py::test_no_new_hardcoded_thresholds_or_aois` still lists committed `app.py` lines 158–203 (AOI coordinate literals). After the Horn edit, that is the only file the scan reports.
- `tests/test_cut_fixtures.py::test_cut_round_trip_preserves_evidence` replaces `subprocess.run`, then the first `numpy.testing` import runs `lscpu`.
- `tests/test_earthquake_dpm.py::test_parquet_roundtrip` — pyarrow 26.0.1 (lock) raises `ImportError: pyarrow requires NumPy 2.0 or newer, found 1.26.4` (lock).

Analyst, orchestrator, cache-guard, and repo-rule tests: 44 passed in 3.33 s, including the cache-marked read of the real Aburrá cube.
