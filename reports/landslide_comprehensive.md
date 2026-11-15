# Comprehensive landslide analysts — Aburrá and La Picacha

**Label: PROVISIONAL.** This pass reads staged public cache and the existing InSAR artifact. It does not issue a failure probability, and it does not say the score beats a baseline.

Measured 2026-11-15 14:20 Bogotá (UTC−5); log time 2026-11-15T19:20:08Z.

## Reproduce

Analyst states and the scalar lines below were printed by this command:

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

Printed *(measured)*:

```
aburra not cached cached gate result
slope 262144 262144 12.676993370056152 1.445995980501175 33.214012145996094
hand 262144 262144 64.300048828125 0.0 392.4000244140625
rain 262144 0 None True ['missing']
insar no_motion 9.105440970850369 17 17
la_picacha not cached not cached not cached
```

Gap reasons, provenance, and the 17 granule IDs are fields of those same envelopes (`m.fn("aburra")["data"]["insar"]["source_ids"]` has length 17).

Envelope states *(measured)*:

| AOI | geology | geomorphology | hydrogeology |
|---|---|---|---|
| aburra | not cached | cached | gate result |
| la_picacha | not cached | not cached | not cached |

Each envelope records this command string (the aburra call of the same three tools):

```
uv run python -c "from mcp_servers.gee_fusion_mcp import analyze_landslide_geology as g, analyze_landslide_geomorphology as m, analyze_landslide_hydrogeology as h; print(g.fn('aburra')['state'], m.fn('aburra')['state'], h.fn('aburra')['state'])"
```

`calibrated` is false on every envelope. Direct calls use `FunctionTool.fn`. The decorated name is not a plain function.

The InSAR noise floor inside the geomorphology envelope was produced earlier by `uv run python -m gee_math.landslide_insar_math` and stored on `local_cache/aburra/landslide_evidence.json`. This pass reads that artifact. It does not recompute the stacks.

Cache time on both Aburrá envelopes that have provenance: `2026-11-15T08:49:52Z`. The envelope says this is the mtime of the AOI manifest, not an acquisition date.

## Per-AOI verdict

**Aburrá — PROVISIONAL.** The InSAR outcome is `no_motion`: no motion detected above 9.105440970850369 mm on 17 pairs. The stored sentence is "no motion detected above 9.105 mm (17 pairs); kept fraction below the sign-flip null on every stack". The only conditioning factors measured in this pass are the FABDEM slope summary and the MERIT HAND summary below. Geology, orthophoto displacement, gully-head retreat, a finite rainfall depth, SPT, a water-table series, a Culmann factor of safety, and a WorldCover load are gaps. Amenaza × vulnerabilidad is not quantified. No failure probability is stated.

**La Picacha — PROVISIONAL.** `config/bailasar.yaml` key `6_la_picacha_landslide` holds bbox `[-75.6404, 6.2313, -75.6191, 6.2367]`. The landslide node maps that key to analyst AOI `la_picacha`. No staged geology, DEM, HAND, orthophoto history, InSAR evidence, rainfall, strength profile, or WorldCover record exists for that AOI, so all three tools return `not cached` with `data` null. No risk number is stated. The comment on the config key is not remeasured here.

## Aburrá — geologist

State `not cached`. Reason: no staged public geology layer for aburra (expected `local_cache/aburra/geology.json`; SGC units are not inferred). `data` is null.

SGC question the node asks, method `local`: "SGC guia metodologica escala detallada: factores condicionantes, geologia para ingenieria y perfil geologico-geotecnico".

No dominant unit, engineering class, fault, or contact is reported.

## Aburrá — geomorphologist and photogrammetry

State `cached`. Reason: staged terrain and the InSAR tie; photogrammetry only where a record exists.

Envelope method: "SGC geomorfologia e inventario de movimientos en masa".

SGC question the node asks, method `local`: "SGC guia metodologica escala detallada: geomorfologia e inventario de movimientos en masa".

### Slope *(measured)*

Source id: `GEE projects/sat-io/open-datasets/FABDEM`.

Denominator: finite pixels over cells in the staged grid.

| n_pixels | n_finite | median_deg | p05_deg | p95_deg |
|---:|---:|---:|---:|---:|
| 262144 | 262144 | 12.676993370056152 | 1.445995980501175 | 33.214012145996094 |

### HAND *(measured)*

Quantity: height above nearest drainage. HAND is not used as relative relief.

Source id: `GEE MERIT/Hydro/v1_0_1 band hnd version v1_0_1 grid EPSG:4326 512x512`.

Denominator: finite HAND pixels over cells in the staged grid.

| n_pixels | n_finite | median_m | p05_m | p95_m |
|---:|---:|---:|---:|---:|
| 262144 | 262144 | 64.300048828125 | 0.0 | 392.4000244140625 |

`p05_m` is 0.0 m with `n_finite` equal to `n_pixels` (262144). That is a measured channel value on a fully finite grid.

### Terrain products withheld

| Product | State |
|---|---|
| aspect, profile curvature, plan curvature, relative relief | unavailable — no elevation grid is staged |
| geomorphological units | unavailable — no unit layer is staged; slope is not binned |
| derivatives | null |
| photogrammetry (co-registration, epoch path, gully-head retreat, signed downslope) | unavailable — no `local_cache/aburra/photogrammetry.json` |
| photo–InSAR sign agreement | unavailable — signed photogrammetric displacement is missing; InSAR is reported alone |

### InSAR tie *(measured)*

| Field | Value |
|---|---|
| outcome | no_motion |
| noise_floor_mm | 9.105440970850369 |
| n_pairs | 17 |
| measurement | measured |
| denominator | GUNW pairs with a finite residual RMS |
| command | `uv run python -m gee_math.landslide_insar_math` |

The artifact stores an unsigned noise-floor magnitude. This pass does not treat that magnitude as a signed downslope displacement.

Granule IDs (17), also listed on the envelope provenance:

- NISAR_L2_PR_GUNW_023_047_A_005_024_4000_SH_20260617T103906_20260617T103941_20260629T103906_20260629T103940_P05023_N_F_J_001
- NISAR_L2_PR_GUNW_024_011_D_085_025_4000_SH_20260626T232840_20260626T232914_20260708T232839_20260708T232914_P05023_N_F_J_001
- NISAR_L2_PR_GUNW_024_047_A_005_025_4000_SH_20260629T103906_20260629T103940_20260711T103905_20260711T103939_P05023_N_F_J_001
- NISAR_L2_PR_GUNW_025_011_D_085_026_4000_SH_20260708T232839_20260708T232914_20260720T232838_20260720T232913_P05023_N_F_J_001
- NISAR_L2_PR_GUNW_025_047_A_005_026_4000_SH_20260711T103905_20260711T103939_20260723T103904_20260723T103939_P05023_N_F_J_001
- NISAR_L2_PR_GUNW_026_011_D_085_028_4000_SH_20260720T232838_20260720T232913_20260813T232837_20260813T232912_P05023_N_F_J_001
- NISAR_L2_PR_GUNW_026_047_A_005_028_4000_SH_20260723T103904_20260723T103939_20260816T103903_20260816T103937_P05023_N_F_J_001
- NISAR_L2_PR_GUNW_028_011_D_085_029_4000_SH_20260813T232837_20260813T232912_20260825T232837_20260825T232911_P05023_N_F_J_001
- NISAR_L2_PR_GUNW_028_047_A_005_029_4000_SH_20260816T103903_20260816T103937_20260828T103903_20260828T103937_P05023_N_F_J_001
- NISAR_L2_PR_GUNW_029_011_D_085_030_4000_SH_20260825T232837_20260825T232911_20260906T232837_20260906T232911_P05023_N_F_J_001
- NISAR_L2_PR_GUNW_029_047_A_005_030_4000_SH_20260828T103903_20260828T103937_20260909T103903_20260909T103937_P05023_N_F_J_001
- NISAR_L2_PR_GUNW_030_011_D_085_031_4000_SH_20260906T232837_20260906T232911_20260918T232837_20260918T232911_P05023_F_F_J_001
- NISAR_L2_PR_GUNW_030_047_A_005_031_4000_SH_20260909T103903_20260909T103937_20260921T103903_20260921T103937_P05023_N_F_J_001
- NISAR_L2_PR_GUNW_031_011_D_085_032_4000_SH_20260918T232837_20260918T232911_20260930T232837_20260930T232911_P05023_N_F_J_001
- NISAR_L2_PR_GUNW_031_047_A_005_032_4000_SH_20260921T103903_20260921T103937_20261003T103903_20261003T103937_P05023_N_F_J_001
- NISAR_L2_PR_GUNW_032_011_D_085_033_4000_SH_20260930T232837_20260930T232911_20261012T232837_20261012T232912_P05023_N_F_J_001
- NISAR_L2_PR_GUNW_032_047_A_005_033_4000_SH_20261003T103903_20261003T103937_20261015T103903_20261015T103937_P05023_N_F_J_001

Provenance also includes the FABDEM and MERIT source ids above.

## Aburrá — groundwater and hydrogeology

State `gate result`. Reason: rainfall or strength inputs inspected; wetting front and Culmann withheld.

Envelope method: "Green-Ampt; effective stress; Culmann plane wedge; SPT-N".

SGC question the node asks, method `local`: "SGC guia metodologica escala detallada: factores detonantes lluvia y nivel freatico, infiltracion y probabilidad de falla".

### Rainfall grid *(measured gap)*

| Field | Value |
|---|---|
| n_pixels | 262144 |
| n_finite | 0 |
| median_mm | null |
| values_read | true |
| source_ids | `missing` |
| measurement | measured |
| denominator | finite rainfall pixels over cells in the staged grid |

The zarr store opened and every sample was non-finite. `n_finite` 0 is a count of finite samples. It is not a measured rainfall depth of 0 mm. Green-Ampt is not run. `wetting_front` is null. Reason recorded: staged rainfall has no finite depth, so Green-Ampt is not run.

Provenance `granule_ids`: `["missing"]`.

### Stability products withheld

| Product | State |
|---|---|
| wetting front (Green-Ampt) | unavailable |
| effective-stress change | unavailable — no staged water-table series |
| SPT-N → φ (Wolff / Peck) | unavailable — SPT-N is not staged |
| SPT-N → cu (Stroud; factor is an input, never a hidden default) | unavailable — SPT-N is not staged |
| Culmann critical height and factor of safety | unavailable — no staged strength profile |
| WorldCover built-up surcharge | unavailable — no `local_cache/aburra/worldcover.json` |
| hydro profile | unavailable — no `local_cache/aburra/hydro_profile.json` |

`wetting_front`, `effective_stress_change_kpa`, `phi_deg_spt`, `cu_kpa_spt`, `culmann`, and `built_up_load` are null.

## La Picacha — three analysts

| Analyst | State | Reason |
|---|---|---|
| geology | not cached | no staged public geology layer for la_picacha (expected `local_cache/la_picacha/geology.json`; SGC units are not inferred) |
| geomorphology | not cached | no staged DEM, HAND, orthophoto history, or InSAR evidence for la_picacha |
| hydrogeology | not cached | no staged rainfall, strength profile, or WorldCover record for la_picacha |

`data` is null on all three. The Aburrá 512-cell grid is not copied onto this AOI.

## SGC grounding

The landslide node calls `knowledge.graphrag.retrieve.ground(question, method="local")` for geology, geomorphology, hydrogeology, and risk. The risk question is "SGC guia metodologica escala detallada: riesgo igual a amenaza por vulnerabilidad". The interpretation states analyst and grounding states only. Quantities stay in the tool envelopes. The risk sentence is: "Riesgo is amenaza times vulnerabilidad. No failure probability is stated here."

`index_built()` *(measured)*:

```
uv run python -c "from knowledge.graphrag.retrieve import index_built; print(index_built())"
```

Result: `True` (2 parquet files under `local_cache/graphrag/output`, directory listing count 4). The citation text is not copied into the bulletin: it is model prose, not a measured hazard quantity.

Under pytest the node records grounding state `unavailable`, records `index_state` `built` or `not_built`, and does not launch the model query. A built index makes `ground()` call a paid endpoint. This report did not launch that query.

Outside pytest, a missing module is `unavailable`, a missing index is `unavailable` (`index_state` `not_built`), a failed query is `error`, and a grounded query is `live` with the answer text left out of the bulletin.

## Methods named, and what was not run on these AOIs

Green-Ampt, effective stress (Δσ′ = −γ_w Δh, γ_w = 9.81 kN/m³), Culmann plane wedge, and the SPT-N correlations (Wolff / Peck for φ, Stroud for c_u with an explicit factor) are implemented and locked to hand-written arrays in `validation/ALLOWLIST.md`. Those fixture numbers are logic checks. They are not Aburrá or La Picacha observations, and they do not appear above.

Horn (1981) slope, aspect, and curvature need an elevation grid. None is staged, so those derivatives are null on the real AOIs. The same functions are unit-tested on a hand-written 3×3 array.

No live Earth Engine call is made. A missing cache file stays `not cached`. An inspected input that cannot support the science product stays `gate result`.

## Orchestrator follow-ups (outside this file list)

- README landslide row and diagrams were not edited. Acceptance asks for them; `README.md` is outside the brief's file list.
- No `docs/kb/` note was added. The knowledge-base path is outside the file list.
- `gee_fusion_mcp.py` aliases `pydantic._internal._typing_extra.eval_type_backport` to `eval_type` before importing FastMCP. Measured with `uv run python -c 'import importlib.metadata as m; print(m.version("pydantic"), m.version("mcp"), m.version("fastmcp"))'`: pydantic 2.14.3, mcp 1.16.0, fastmcp 2.12.5. Importing `mcp` without that alias raises `ImportError: cannot import name 'eval_type_backport'`. A dependency alignment would replace the alias.
- Bulletin placeholders are declared only for finite analyst scalars that carry source ids. This Aburrá pass can declare slope and HAND summaries and the rainfall pixel counts (source id `missing`, `n_finite` 0). Wetting-front depth and Culmann stay undeclared because those values are null.
