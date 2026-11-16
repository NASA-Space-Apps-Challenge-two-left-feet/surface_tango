# Surface Tango

**Team:** two left feet · Medellín, Colombia
**Challenge:** Dancing with the SARs

## Summary

Where should help go first when a disaster leaves gaps in the map? Surface Tango is an interactive observatory that helps Colombian risk management teams use public NISAR L-band radar observations. It pairs a dated map with a bilingual briefing so analysts can see what the satellite observed and decide where to verify conditions on the ground.

In La Mojana, NISAR mapped **4,487 hectares of absolute open water** on June 17, 2026, based on **5,539 of 197,758 valid pixels** (measured, rounded, provisional). The estimate uses an uncalibrated threshold; flood change remained unclassified. NISAR also covered the epicenter of the August 10 earthquake near San José del Palmar, Chocó, where the damage analysis remained inconclusive. In Valle de Aburrá, the analysis detected no slope motion above the measured noise floor. These cases show why response teams need to see both what a satellite measured and where field verification is still needed.

[La Mojana method, command and source granule](https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango/blob/47e767a/reports/mojana.md#open-water-fraction-by-date) · [Chocó analysis](https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango/blob/47e767a/reports/quake_epicenter_dpm.md) · [Aburrá analysis](https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango/blob/47e767a/reports/aburra.md#verdict)

## Project Links

- **Project video:** [INSERT PUBLIC VIDEO URL]
- **Interactive demo:** [Open Surface Tango Mission Control](https://surface-tango-827987874406.us-central1.run.app/)
- **Source code:** [Surface Tango on GitHub](https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango)

The video demonstrates the satellite comparison curtain, the La Mojana time series, and how the findings are presented with their evidence limits. The interactive demo lets reviewers explore the flood, landslide, and earthquake views and read the bilingual briefing. The first visit may show a waiting screen while the demo server starts.

<!-- Before pasting this section, replace the video placeholder and confirm playback in a signed-out browser without an access request. Include the source code link only if judges can open it without signing in or requesting access. Review the final media for permissions and attribution. Exclude any photo, video, or audio of a person under 18. Follow the team's brand rules for agency marks. -->

## Project Information

Mission Control lets users slide between Sentinel-2 optical imagery, Sentinel-1 C-band radar, and NISAR L-band radar. A dated timeline shows La Mojana’s measured open-water extent. Analysts can inspect terrain context and missing data. The response view suggests topics for field checks, such as access and shelter, while leaving impact and aid quantities unavailable where evidence is insufficient.

We built it with Python, Google Earth Engine, FastAPI, FastMCP, LangGraph, Zarr, MapLibre, Deck.gl, and Docker Compose. The side-by-side view makes differences between sensors visible. Spanish and English briefings support local users. Prepared data supports offline review, and the demo server starts on demand and shuts down when idle to limit hosting costs and idle compute.

Our intended impact is better prioritization of field checks. A proposed pilot would test how authorities combine these observations with local reports when deciding whether to issue public warnings.

### Use of Super Intelligence

LangGraph coordinates agents for floods, landslides, and earthquakes. A language model drafts a briefing with placeholders. Validated tool results supply the figures and sources. AI-written briefings carry the **SI-Assisted Analytics** badge. Development used Claude Code with gstack, OpenAI Codex, Google Antigravity/Gemini, OpenCode (GLM), and Grok. The [recorded bilingual run](https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango/blob/47e767a/reports/bulletin_demo.md) documents the runtime workflow.

## Resources and Attribution

- [NASA Science: NISAR mission](https://science.nasa.gov/mission/nisar/) and [ASF DAAC NISAR data](https://asf.alaska.edu/notices/nisar-l-band-data-now-publicly-available/). Surface Tango uses provisional NASA–ISRO L-band GCOV backscatter and GUNW interferograms. The [ASF GUNW guide](https://nisar-docs.asf.alaska.edu/gunw/) describes the phase and coherence products.
- [Google Earth Engine public catalog](https://developers.google.com/earth-engine/datasets). ESA/Copernicus Sentinel-1 and Sentinel-2 provide radar and optical comparisons. FABDEM and MERIT Hydro provide terrain and drainage context. The [repository inventory](https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango/blob/47e767a/DATA_LICENSES.md) also documents CHIRPS, JRC Global Surface Water, WorldPop, ESA CCI biomass, and OpenStreetMap, with their roles and availability.
- [USGS earthquake record](https://earthquake.usgs.gov/earthquakes/eventpage/us6000tjl2) and [Servicio Geológico Colombiano bulletin](https://www.sgc.gov.co/detalleevento/SGC2026pqqmro/resumen). These provide agency estimates for the earthquake. [Esri World Imagery attribution](https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango/blob/47e767a/docs/kb/context-satellite-basemap.md) covers the optional context basemap.
- [Methods and evidence](https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango/tree/47e767a/reports). Reports preserve commands, granule or scene IDs, denominators, and limitations. The [preregistration](https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango/blob/47e767a/validation/README.md) records the analysis rules and evaluation limits. Third-party data retain their own terms.
