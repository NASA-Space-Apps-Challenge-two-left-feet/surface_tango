## v0.2.0 (2026-11-15)

Evaluation snapshot for judging. This release does not change
`config/preregistered.yaml`. v0.1.0 was never tagged, so the lists
below are the untagged history commitizen collected. The regional
cube page was added (#213) and then removed (#219). It is not in
this snapshot.

### Feat

- **web**: serve a cloud-free navigator background (#221)
- **web**: fold the physics inspector and the story map (#218)
- **web**: add a satellite context basemap under the visor (#216)
- **web**: window the Aburrá LOS raster onto La Picacha (#214)
- **web**: add the atlas regional cube explorer (#213)
- **web**: share one curtain frame across cached layers (#210)
- **landslide**: add geology, geomorphology, and hydrogeology analysts (#211)
- **web**: make cached NISAR L-band the primary panel (#209)
- **web**: add the hazard decision layer and open-water HAND overlay
- **web**: AOI coverage/footprint framing + scientific InSAR LOS colormap (#207)
- **release**: start the 16 GB demo VM on request during judging (#200)
- **web**: AOI navigator — grouped list, zoom-to-AOI, honest states (#204)
- **agents**: landslide GraphRAG grounding scaffold + measured AOIs (#203)
- **web**: tango-basic two-feet animation + README brand pass (#196)
- **quake**: epicenter AOIs hour-2 gate (measured R/C/K triplets) (#193)
- **agents**: add Vertex AI Gemini (ADC) as the primary orchestrator LLM (#192)
- **quake**: extend AOIs to the Choco epicenter + capture the insight (#190)
- **web**: apply the team brand across the mission control (#188)
- **web**: first-class verdict card for the aburra calibrated null (#168)
- **agents**: render measured nulls inside the live bilingual bulletin (#166)
- **cache**: generalize hand_m to all AOIs; stage the v2 evidence release (#163)
- **agents**: live bilingual bulletin from the hazard graph (#36) (#162)
- **quake**: report the frozen-pair coherence-loss excess E_C − E_K (#161)
- **flood**: compare L- and C-band open water on every La Mojana date (#160)
- **landslide**: add the aburra stable-pixel false-positive rate (#155)
- **agents**: harden the hazard graph (plan validation, arg preflight) (#153)
- **agents**: add guarded bilingual hazard graph (#151)
- **mcp**: prepare owner-run live latency collection (#146)
- **web**: open the offline pitch on la mojana with report-sourced numbers (#140)
- **config**: budget analyze_flood_inundation from 10 timed calls (#138)
- **cache**: add MERIT hand_m to the mojana cube with flood fixture (#137)
- **mcp**: serve flood and quake evidence from the cache artifacts (#136)
- **agents**: display quake depth 116 km as the usgs estimate (#132)
- **config**: freeze the pre-registration and record its hash (#130)
- **data**: serialize measured runs into the mcp landslide evidence artifact (#127)
- **mcp**: make the fusion tools evidence-envelope adapters (#122) (#126)
- **config**: fill quake R/C/K pair ids per track from the hour-2 gate (#86)
- **web**: show verified cache layers in the story map (#117)
- **mcp**: add scoring wrapper tools over validation.scoring (#110)
- **quake**: complete the dpm product for both tracks with sealed statistics (#111)
- **landslide**: add aburra insar noise-floor pipeline with a calibrated null verdict (#109)
- **mcp**: enforce sse transport, request-bound cache fallback and bulletin checks (#103)
- **mcp**: enforce SSE transport and request-bound cache fallback
- **bulletin**: validate placeholders and verified event fields
- **flood**: add la mojana dual-pol classification with bounded gcov reads (#98)
- **scoring**: add neighborhood ranking and uncertainty functions (#96)
- **agents**: trace langgraph runs to langsmith when a key is set (#95)
- **config**: add landslide noise_floor keys to preregistered.yaml (#91)
- **config**: set search_nisar_granules breaker budget from timed calls (#87)
- **config**: add one loader for preregistered and operational yaml (#85)
- **diagrams**: add animated architecture and lakehouse SVG generators (#89)
- **cache**: build real-data cache for all three AOIs (#78)
- **cache**: add release staging, manifest verifier and make fetch-cache (#67)
- **cache**: pre-stage sentinel-1 and 2 curtain slider tiles (#65)
- **quake**: add pre-registered coherence-loss DPM pipeline for track 11 (#64)
- **gate**: run the hour-2 nisar gate over the three aois
- **agents**: add orchestrator llm fallback chain across providers (#51)
- import baseline scaffold and team workflow rules (#14)

### Fix

- **web**: drop the regional cube page (#219)
- **web**: mark the flood telemetry row when its node finishes (#217)
- **web**: ignore macOS sidecar tiles in the curtain index (#215)
- **mcp**: alias pydantic eval_type_backport in the NISAR server (#212)
- **web**: make the C-band↔L-band curtain transition actually work (#202)
- **cache**: rebuild the pitch image so docker changes take effect (#183)
- **quake**: read the frozen pairs and rebuild the control pass (#180)
- **cache**: link shared worktree assets without Windows symlink rights (#175)
- **web**: package offline pitch inputs in the image (#172)
- **flood**: keep the L/C test independent of local cache (#165)
- **mcp**: unblock the latency runner and budget from its owner run (#158)
- **web**: read the Aburrá sign-flip verdict by column (#157)
- **cache**: lock writers and make fetch rollback crash-safe (#135)
- **config**: re-choose control pairs that share no date with r or c (#134)
- **cache**: make fetch-cache transactional, streamed and retry-safe (#128)
- **web**: enforce the published story evidence gates (#120)
- **web**: reject sentinel tiles from failed cache refreshes (#118)
- **landslide**: read and verify the pre-registered noise-floor keys (#115)
- **diagrams**: clear overlaps in the lakehouse svg and bring it current (#114)
- **diagrams**: clear overlaps in the architecture svg and bring it current (#113)
- **flood**: kill a stalled granule reader on windows too (#106)
- **web**: load staged tiles in mission control (#105)
- **readme**: drop semicolon that broke the mermaid sequence note (#82)
- **mcp**: drop dead module-level netrc login from the asf server (#79)
- **web**: prepare offline rehearsal with validated cache inputs (#71)
- **mcp**: rebuild gee fusion server and clear baseline lint
- **gate**: start earth engine with the adc identity everywhere (#52)

### Refactor

- **cache**: move story preparation out of static assets (#174)
- port repo tooling to python and set the language rule (#77)
