# Project page text (reviewed draft, #45)

**Team:** two left feet — Surface Tango · NASA Space Apps 2026 challenge "Dancing with the SARs" · Medellín, Colombia

## Plain-language summary

Surface Tango brings public radar observations and their limits together in one map and evidence-backed bulletin. It examines open water in La Mojana, ground motion in the Aburrá Valley, and an earthquake damage proxy in the Eje Cafetero. NISAR L-band data and public context layers pass through geospatial tools and LangGraph hazard agents. The agents write bilingual prose; measured quantities and sourced event facts come from tool outputs, while missing observations remain visible. The earthquake proxy has no verified neighborhood damage labels and cannot support a response-priority claim.

## What the data shows

- **La Mojana (headline):** A provisional NISAR mask mapped **4,487 ha of absolute open water** on 2026-06-17, rounded from 4,486.59 ha (5,539 of 197,758 valid pixels; *measured, uncalibrated threshold*). The sensitivity range is 2,799–6,726 ha (3,455–8,304 positive pixels over the same valid-data domain; *measured, rounded*). The dry reference cannot support a flood-change estimate. Evidence: `uv run python -m gee_math.flood_polarimetric_math`; GCOV granule `NISAR_L2_PR_GCOV_023_047_A_005_4005_DHDH_A_20260617T103906_20260617T103941_P05023_F_F_J_001`; [report](../reports/mojana.md).
- **Aburrá Valley:** The landslide analysis found **no motion above its 9.105 mm noise floor** across 17 GUNW pairs (*measured, provisional*). The hillslope kept fraction stayed below the sign-flip null on both tracks. Evidence: `uv run python -m gee_math.landslide_insar_math`; the [report](../reports/aburra.md) lists the pair IDs and per-track denominators. This is a measured null for the analyzed window, not proof that no landslide occurred.
- **Eje Cafetero:** The coherence-loss proxy contrast is inconclusive. The frozen control pair replaced an older control pass; a temporal-baseline mismatch remains. The scorecard is **uninformative** because no verified neighborhood damage labels were adopted. Evidence: [frozen-pair interpretation, commands and granule IDs](../reports/quake_dpm_interpretation.md) and [power check](../validation/README.md#power-check-and-headline-plan-02-03-25). The proxy is not a validated damage map.
- **Bulletin:** A live run produced an English and Spanish bulletin from the hazard graph. Its quantities were filled from evidence fields, not invented by the language model. Evidence: [live-run report](../reports/bulletin_demo.md).

## How it works

Separate FastMCP servers provide radar and contextual evidence to LangGraph hazard agents. A synthesis step writes the bulletin from checked tool outputs. Source identifiers and cache provenance travel with the results. The interface labels each panel as live, cached, not cached, gate result or error, so an unavailable layer is explicit. The [README](../README.md) describes the implemented architecture and current component states.

## AI disclosure

Built with Claude Code + gstack, OpenAI Codex, Google Antigravity/Gemini, OpenCode (GLM), Grok and LangGraph. AI-written bulletins carry the **SI-Assisted Analytics** badge. Agency attribution does not imply endorsement.

## Data and reuse

The analysis uses public NISAR observations distributed by ASF DAAC and public contextual sources listed in the [README](../README.md#data-sources-and-citations). Apache-2.0 is **proposed** for team-owned code; the team has not finalized that choice. Third-party data and derived cache assets have separate terms, and release redistribution remains under review in [DATA_LICENSES.md](../DATA_LICENSES.md).
