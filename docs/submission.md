# Surface Tango — submission draft

Draft for NASA Space Apps 2026, as identified in [AGENTS.md](../AGENTS.md). Pending results and links must be completed from evidence before submission.

## Project summary

Surface Tango turns public NISAR L-band observations into evidence about surface change in Colombia. Its mission-control map covers landslides in the Aburrá Valley, an earthquake damage proxy in the Eje Cafetero, and open water in La Mojana. The analyses preserve source IDs and report missing observations and inconclusive comparisons. La Mojana open water is the video headline; Aburrá has a calibrated null verdict, and the earthquake scorecard is uninformative without verified neighborhood damage labels. A live bilingual bulletin has a demo capture; the offline demo's data layer is verified end to end — every mission-control endpoint serves measured evidence or an explicit state — with the visual walkthrough and recorded cut being finalized. The full observatory is deployed as a docker-compose container stack on Google Cloud (Compute Engine, `us-central1-a`); its public demo URL is being finalized. Sources: [README](../README.md), [La Mojana report](../reports/mojana.md), [Aburrá report](../reports/aburra.md), [power check](../validation/README.md), [bulletin demo](../reports/bulletin_demo.md).

## Challenge and problem

The challenge is **“Dancing with the SARs”**: making NISAR surface-change observations visible and useful through an interactive application. Surface Tango lets communities and emergency analysts inspect slope movement, earthquake-related change and open water with the evidence and its limits visible together. The earthquake proxy needs independent damage labels before it can support a claim about damage or response priorities. Sources: [design](designs/bailasar.md), [README](../README.md), [power check](../validation/README.md).

## Approach

The approach uses NISAR L-band GUNW coherence and unwrapped phase, plus GCOV backscatter, with public contextual datasets. ASF's documented product layers are recorded in the [verified GUNW note](kb/nisar-gunw-layers.md). The three analyses have different evidence states:

- **Aburrá landslides:** the InSAR pipeline applies the ionosphere screen and compares motion estimates with a stable-pixel noise floor and a sign-flip null. It reports no motion above the measured noise floor. Granizal is historical context, not a claimed NISAR detection. [Method and verdict](../reports/aburra.md).
- **Earthquake damage proxy:** the pipeline compares pre-event and co-event coherence for the event recorded in the [gate report](../reports/gate.md). The frozen control-pair selection was corrected and disclosed in [deviation 2](../validation/README.md#deviations). The older cached K pass is discarded; a separate [interpretation](../reports/quake_dpm_interpretation.md) streamed the frozen K granules and found an inconclusive proxy contrast on both tracks. No verified neighborhood damage labels were adopted, so the scorecard is uninformative and no ranking-performance claim is made. A proxy is not confirmed building damage.
- **La Mojana open water:** provisional GCOV observations support an absolute open-water mask with a threshold sensitivity range and a per-date comparison with Sentinel-1 C-band observations. The C-band cut is uncalibrated. The dry reference has insufficient valid coverage, so the dual-polarization change classes remain unsupported. The result does not separate seasonal water from water related to the Caregato breach. [Method and measurements](../reports/mojana.md), [L/C comparison](../reports/mojana_lvsc.md).

The architecture uses separate FastMCP servers, `mcp-nisar-asf` and `mcp-gee-fusion`, with SSE transport and cache-backed evidence tools. LangGraph routes ingestion to landslide, earthquake and flood agents, then to checked bilingual synthesis. Agents write prose with placeholders filled from tool outputs or sourced event constants; they never generate numerical results. A [live run](../reports/bulletin_demo.md) captured a bilingual bulletin from the graph. Sources: [README](../README.md), [agent handoff](../agents/INTEGRATION_HANDOFF.md).

The cache guard serves real pre-staged tiles and statistics with source IDs and cache-build provenance when live tools time out. Uncached requests return “not cached”; missing pixels remain missing. The public release cache and end-to-end demonstration remain pending in the [README](../README.md). Biomass, surface-rupture analysis, S-band fusion, split-spectrum ionosphere processing and the math lab are outside submission scope.

## Results

The [gate report](../reports/gate.md) records catalog discovery and the earthquake pair choices. Its co-event baseline mismatch remains a limit on any earthquake interpretation.

- **La Mojana headline:** **4,486.59 ha of absolute open water** on 2026-06-17, from 5,539 of 197,758 valid pixels. Threshold sensitivity: 2,798.55–6,726.24 ha (3,455–8,304 pixels over the same valid-data domain). *(Measured, PROVISIONAL, uncalibrated.)* Command: `uv run python -m gee_math.flood_polarimetric_math`; source granule `NISAR_L2_PR_GCOV_023_047_A_005_4005_DHDH_A_20260617T103906_20260617T103941_P05023_F_F_J_001`. [Counts and sensitivity](../reports/mojana.md#sensitivity). These are open-water observations, not an attributed flood-change estimate.
- **Aburrá:** no motion detected above the **9.105 mm noise floor** across 17 GUNW pairs. The hillslope kept fraction is below the sign-flip null on both tracks; the [report](../reports/aburra.md#verdict) lists the per-track denominators and all source granule IDs. *(Measured, PROVISIONAL.)* Command: `uv run python -m gee_math.landslide_insar_math`.
- **Earthquake:** the first-aid ranking scorecard is **uninformative** because no verified neighborhood damage labels were adopted. No precision, improvement over baseline or operational priority claim follows from the proxy. [Power check](../validation/README.md#power-check-and-headline-plan-02-03-25).
- **Integration:** the offline agent contract is implemented and a live bilingual graph run is [captured](../reports/bulletin_demo.md). The offline demo's data layer is verified end to end (mission-control endpoints serve measured evidence or an explicit state); the full stack is deployed as a docker-compose container on Google Cloud (Compute Engine). The public demo URL and the public cache release remain pending. [Agent handoff](../agents/INTEGRATION_HANDOFF.md), [README status](../README.md#status).

**Unverified KB facts:** Colombia-wide polarization/revisit claims ([note](kb/nisar-polarization-colombia.md)), Colombia-specific S-band coverage or absence ([note](kb/nisar-sband-colombia.md)), and the quantitative decorrelation formula and masonry interpretation ([note](kb/method-coherence-decorrelation.md)) remain unverified and are not used as findings here. The original archive-start claim is superseded by the [verified public-record correction](kb/nisar-public-record-v2.md). The earthquake depth is verified as agency estimates: USGS preferred-origin estimate 116 km ([note](kb/event-2026-08-10-earthquake.md)); SGC manual bulletin 105 km ([note](kb/event-2026-08-10-earthquake-sgc.md)). Surface Tango displays the USGS value, rounded to 116 km and labelled a USGS estimate.

## Data sources

These public inputs have different ingestion and validation states; the [reports](../reports/) identify the sources used for each measured result. Provider names follow the [README source table](../README.md#data-sources-and-citations). Only external links already present in the repository are used.

| Dataset | Provider and citation | Intended role |
|---|---|---|
| NISAR L-band | NASA/JPL and ISRO; [ASF DAAC](https://asf.alaska.edu/notices/nisar-l-band-data-now-publicly-available/), [GUNW documentation](https://nisar-docs.asf.alaska.edu/gunw/) | Coherence, phase and backscatter |
| Sentinel-1 | ESA / Copernicus; [repository citation](../README.md#data-sources-and-citations) | C-band comparison |
| Sentinel-2 | ESA / Copernicus; [repository citation](../README.md#data-sources-and-citations) | Optical comparison |
| CHIRPS | Climate Hazards Center, University of California, Santa Barbara; [repository citation](../README.md#data-sources-and-citations) | Precipitation context |
| FABDEM | University of Bristol; [repository citation](../README.md#data-sources-and-citations) | Terrain context |
| MERIT Hydro | University of Tokyo, Institute of Industrial Science; [repository citation](../README.md#data-sources-and-citations) | Drainage context and flood gating |
| JRC Global Surface Water | European Commission, Joint Research Centre; [repository citation](../README.md#data-sources-and-citations) | Surface-water history |
| WorldPop | WorldPop, University of Southampton; [repository citation](../README.md#data-sources-and-citations) | Population exposure and baseline ranking |
| OpenStreetMap | OpenStreetMap contributors; [repository citation](../README.md#data-sources-and-citations) | Hospitals and roads, with extract provenance |
| Published damage reports | Issuing public agency and report citation pending selection, as recorded in the [README](../README.md#data-sources-and-citations) | Independent damage labels |

Direct provider links for entries citing the README are not recorded there and remain pending. The earthquake event reference already in the repository is [USGS](https://earthquake.usgs.gov/earthquakes/feed/v1.0/detail/us6000tjl2.geojson), documented in the [verified KB note](kb/event-2026-08-10-earthquake-v2.md); it is not a substitute for neighborhood damage reports.

## AI disclosure

This project is built with Claude Code + gstack, OpenAI Codex, Google Antigravity/Gemini, OpenCode (GLM), Grok and LangGraph.

This disclosure is copied from [AGENTS.md](../AGENTS.md#ai-disclosure). AI-written bulletins must carry the **SI-Assisted Analytics** badge. Submission media must contain no NASA logos, flags or identifiers, and no likeness of minors; UI headers and badges follow the same agency-branding restriction. Agency attribution does not imply endorsement.

## Team

GitHub handles and lanes from [AGENTS.md](../AGENTS.md#project-map):

- @LEONOB2014 — data gate and hazard modeling.
- @Jack4Codes — configuration, pre-registration and cloud tools.
- @Maru816 — scoring.
- @alicealanapineda-byte — agents, MCP transport, cache guard and bulletins.
- @EstebanOchoaedos — cloud checks, cache release, knowledge-base verification and README.
- @SaritaRpo — frontend and video.

## Links

- Repository: [Surface Tango / surface_tango](https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango). Public accessibility remains to be confirmed before submission.
- Live deployment: docker-compose container stack on Google Cloud (Compute Engine, `us-central1-a`); public demo URL `{link: gcloud demo URL pending — ingress on :8000 being opened}`.
- Video: `{link: public submission video pending}`.
- Project page: `{link: Space Apps project page pending}`.
