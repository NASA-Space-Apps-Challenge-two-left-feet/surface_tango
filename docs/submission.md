# BailaSAR — submission draft

Draft for NASA Space Apps 2026, as identified in [AGENTS.md](../AGENTS.md). Pending results and links must be completed from evidence before submission.

## Project summary

BailaSAR is a Colombian multi-hazard observatory prototype designed to turn public NISAR L-band radar observations into understandable surface-change evidence for landslides in the Aburrá Valley, an earthquake damage proxy in the Eje Cafetero, and flooding at La Mojana / Caregato. The planned mission-control map combines radar and optical comparisons with tool-grounded bulletins, while an offline cache preserves real observations and their provenance. Agents coordinate analysis and explanation; deterministic tools supply the values. The project treats missing data, unsupported signals and inconclusive comparisons as reportable outcomes. Discovery evidence is available, while hazard validation and integrated demonstrations remain pending. Sources: [README](../README.md), [design and decisions](designs/bailasar.md), [gate report](../reports/gate.md).

## Challenge and problem

The repository identifies the challenge as **“Dancing with the SARs”**: making NISAR surface-change observations visible and useful through an interactive application. BailaSAR focuses on how communities and emergency analysts might inspect slope movement, earthquake-related change and flood extent in Colombian landscapes. Its research question is whether radar adds useful evidence beyond contextual information such as population and terrain. A damage proxy requires independent validation before it can support claims about damage or response priorities. Sources: [design](designs/bailasar.md), [README](../README.md).

## Approach

The agreed approach uses NISAR L-band GUNW coherence and unwrapped phase, plus GCOV backscatter, with public contextual datasets. ASF's documented product layers are recorded in the [verified GUNW note](kb/nisar-gunw-layers.md). The following are intended analyses, not completed findings:

- **Aburrá landslides:** inspect unwrapped phase with the supplied ionosphere screen and terrain-based corrections, then compare motion estimates against a stable-pixel noise floor. Unsupported motion is reported as a null. Granizal is historical context, not a claimed NISAR detection.
- **Earthquake damage proxy:** compare pre-event and co-event coherence for the **2026-08-10** event identified in the [design](designs/bailasar.md#hazard-2-aug-10-2026-earthquake-damage-and-first-aid-earthquake_dpm_mathpy-earthquake_agent-the-video-headline) and [gate report](../reports/gate.md). Evaluate built-up change and a proposed neighborhood-level first-aid ranking against a population-based baseline and a control pair. Pre-registration, independent damage labels and the informative-scorecard gate constrain any performance claim; a proxy is not confirmed building damage.
- **La Mojana flood:** compare HH/HV backscatter against an acceptable dry reference, with drainage-height gating. Flood thresholds are uncalibrated locally and require sensitivity reporting. Without an acceptable baseline, report water extent without change attribution and a null for unsupported flooded-vegetation change. Attribution to the Caregato breach remains unresolved.

The architecture retains separate FastMCP servers, `mcp-nisar-asf` and `mcp-gee-fusion`, using SSE. Their planned tools discover and stage observations, select earthquake pairs, calculate statistics, serve tiles, rank neighborhoods and score the baseline comparison. LangGraph routes ingestion to landslide, earthquake and flood agents, then to cross-hazard synthesis. Agents write prose with placeholders filled from tool outputs or sourced event constants; they never generate numerical results. Sources: [AGENTS.md](../AGENTS.md), [design and binding decisions](designs/bailasar.md).

The cache guard is designed to serve real pre-staged tiles and statistics with source IDs and cache-build provenance when live tools time out. Uncached requests return “not cached”; missing pixels remain missing. The offline release cache and end-to-end demonstration remain pending in the [README](../README.md). Biomass, surface-rupture analysis, S-band fusion, split-spectrum ionosphere processing and the math lab are outside submission scope.

## Results

The [gate report](../reports/gate.md) records catalog discovery and candidate earthquake pairs, not validated hazard performance. It flags provisional or urgent-response products and mismatched co-event versus reference/control temporal baselines. These caveats must accompany subsequent earthquake results. Layer availability and polarization inferred from filenames still require per-granule checks.

- Earthquake scorecard and baseline/control comparison: `{result: see reports/<quake-scorecard-file>}`.
- Aburrá motion above the noise floor, or documented null: `{result: see reports/<aburra-noise-floor-file>}`.
- La Mojana flood classes, valid-data denominator and sensitivity: `{result: see reports/<mojana-flood-file>}`.
- Tool latency, bulletin checks and offline demonstration: `{result: see reports/<integration-evidence-file>}`.

The report paths in braces are placeholders, not existing reports. No improvement over baseline, hazard extent, motion rate or operational readiness is claimed. Completed results must cite their producing command, source granule or scene IDs, denominator and applicable interval, with measured results or estimates labelled under [AGENTS.md](../AGENTS.md).

**Unverified KB facts:** Colombia-wide polarization/revisit claims ([note](kb/nisar-polarization-colombia.md)), Colombia-specific S-band coverage or absence ([note](kb/nisar-sband-colombia.md)), and the quantitative decorrelation formula and masonry interpretation ([note](kb/method-coherence-decorrelation.md)) remain unverified and are not used as findings here. The original archive-start claim is superseded by the [verified public-record correction](kb/nisar-public-record-v2.md). The earthquake depth is verified as agency estimates: USGS preferred-origin estimate 116 km ([note](kb/event-2026-08-10-earthquake.md)); SGC manual bulletin 105 km ([note](kb/event-2026-08-10-earthquake-sgc.md)). BailaSAR displays the USGS value, rounded to 116 km and labelled a USGS estimate.

## Data sources

These are intended public inputs; inclusion does not establish ingestion or validation. Provider names follow the [README source table](../README.md#data-sources-and-citations). Only external links already present in the repository are used.

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

- Repository: [BailaSAR / surface_tango](https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango), using the repository identity in the [design](designs/bailasar.md). Public accessibility remains to be confirmed before submission.
- Video: `{link: public submission video pending}`.
- Project page: `{link: Space Apps project page pending}`.
