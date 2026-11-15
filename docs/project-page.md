# Project page text (draft, #45)

**Team:** two left feet — Surface Tango · NASA Space Apps 2026 challenge "Dancing with the SARs" · Medellín, Colombia

## Plain-language summary

Floods, landslides and earthquakes in Colombia compound each other, but radar answers arrive too slowly and too raw for the people who need them. **Surface Tango** is a multi-agent observatory that turns NISAR L-band radar into a sentence a person can act on. Two FastMCP servers do the geospatial computation under strict time budgets; three LangGraph hazard agents interrogate them; a synthesis step writes a bilingual (ES/EN) bulletin in which **no number comes from the language model** — every quantity is a placeholder filled from a measured tool output or a primary-sourced event constant, and anything withheld stays visibly "not available".

## What we measured (all numbers cited to commands and granule IDs in the repo)

- **La Mojana floods (headline):** 4,487 ha of open water mapped on 2026-06-17 (5,539 of 197,758 valid pixels, 90 m NISAR GCOV posting; sensitivity 2,799–6,726 ha across uncalibrated thresholds) — measured by `gee_math/flood_polarimetric_math`.
- **Aburrá Valley landslides:** a **calibrated null** — no motion above the 9.105 mm noise floor across 17 GUNW pairs, against a sign-flip null on both stacks — measured by `gee_math/landslide_insar_math`.
- **Eje Cafetero earthquake (M 7.4, USGS us6000tjl2):** coherence-loss damage proxy with frozen pre-registered pairs; the scorecard is honestly **uninformative** (no verified barrio damage labels); the contrast E_C − E_K is disclosed with its baseline mismatch (C 24 d vs R/K 12 d).
- **Agent stack:** the hazard graph ran end to end into a live bilingual bulletin (`reports/bulletin_demo.md`), with every number traced to its tool evidence field.

## Why it is different

Nulls are first-class results. The pre-registration is frozen and hashed; the scoring rule is pre-registered so the radar must beat geography itself; every panel answers one of live · cached · not cached · gate result · error — never blank, never fabricated.

## AI disclosure

Built with Claude Code, OpenAI Codex, Google Antigravity/Gemini, OpenCode (GLM), Grok and LangGraph. Bulletins are AI-written prose over measured tool outputs and carry the **SI-Assisted Analytics** badge.

## Data sources

NISAR L1/L2 products (ASF DAAC, provisional CRID P05023), Copernicus Sentinel-1/2, FABDEM/MERIT terrain, FAO GAUL admin units, USGS/SGC event parameters, WorldPop. Public data only; code Apache-2.0; see DATA_LICENSES.md.
