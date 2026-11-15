# Surface Tango — NASA Space Apps 2026 project page text

Ready-to-paste text for the Space Apps project page. Every number is measured, with
its source report; nothing is fabricated, and null results are reported as results.
No NASA logos, flags or identifiers appear in our media or badges — agency names are
attribution, never endorsement.

---

## High-level summary

**Surface Tango** turns the first public **NISAR L-band** radar into defensible
evidence about surface change in Colombia — floods, landslides and earthquake
damage — with a ranked first-aid answer and **no number without a source**. It is a
multi-agent observatory: specialized agents interrogate geospatial tools, and a
synthesis agent writes a bilingual (Spanish/English) bulletin whose every figure
comes from a tool output, never from the language model. When the data shows no
signal, the system says so — **an honest null is a valid headline.**

---

## What it does

Over three cascading-disaster lanes in Colombia, Surface Tango answers one question
each, from real NISAR data, and shows exactly one honest state per panel
(**live · cached · not cached · gate result · error** — never blank):

- **La Mojana floods (headline):** where open water is, and **why L-band matters.**
- **Aburrá Valley landslides:** are slopes moving above the radar noise floor?
- **Eje Cafetero earthquake:** which neighborhoods changed — and where the honest
  answer is "we cannot tell yet."

## The measured results

- **Flood — why L-band (the money result).** On the same uncalibrated threshold,
  the usual C-band radar (Sentinel-1) **missed a median of 0.64 of the open-water
  pixels NISAR L-band saw, across 10 dates** — e.g. **3,351 of 4,946** on
  2026-07-11. L-band sees water under vegetation that C-band misses.
  *(Measured, PROVISIONAL, uncalibrated; open water, not a flood-change estimate.
  Source: `reports/mojana_lvsc.md`, with every Sentinel-1 scene ID.)*
- **Landslide — an honest null.** **No motion detected above the 9.105 mm noise
  floor** across 17 interferometric pairs in the Aburrá Valley; the kept fraction
  stays below a sign-flip null on both tracks. *(Measured, PROVISIONAL. Source:
  `reports/aburra.md`.)*
- **Earthquake — coverage, not a damage claim.** The M7.4 epicenter (San José del
  Palmar, Chocó; USGS `us6000tjl2`, depth ≈116 km per USGS) sits where optical and
  C-band go blind. **NISAR L-band covers it** — 96 granules with co-event
  interferograms on three tracks. The damage-proxy run is a **measured null** (no
  positive co-event coherence-loss excess over control; confounded by a post-event
  control and a baseline mismatch), and the first-aid scorecard is **uninformative**
  because no verified neighborhood damage labels exist. We never claim "beats
  baseline." *(Source: `reports/quake_epicenter_dpm.md`, `validation/README.md`.)*

## How it works

- **Two FastMCP servers (SSE)** expose the geospatial tools; a **cache guard** wraps
  every call with a measured time budget and, on timeout, serves only real
  pre-staged tiles with full provenance (source IDs, cache-build time) — an uncached
  request returns an explicit "not cached," never a guess.
- **A LangGraph graph** routes ingestion → landslide / earthquake / flood agents →
  cross-hazard synthesis. **Agents never produce numbers:** the bilingual bulletin
  is a template of `{placeholders}` filled from tool outputs, and a contract error
  fires if any number lacks a backing tool result.
- **A FastAPI mission-control UI** (MapLibre + Deck.gl, map libraries vendored
  locally) shows the three-panel optical / C-band / L-band comparison and the story
  map. The offline demo runs **fully air-gapped** — no network needed.
- **Scientific rigor is enforced, not promised:** frozen pre-registration, no
  synthetic data (missing pixels stay "no data"), and every figure carries its
  command, denominator and source granule IDs.

## What makes it different

Most "multi-agent AI" demos invent confident answers. Surface Tango is built so it
**cannot** invent a disaster signal: numbers come only from deterministic tools, and
it reports nulls and "not cached" honestly. That discipline — plus L-band seeing
water and covering an epicenter that optical satellites cannot — is the project.

## Deployment

The full observatory is deployed as a **docker-compose container stack on Google
Cloud** (Compute Engine). The offline/pitch mode serves measured evidence from a
local Zarr v3 cache with a hashed bulletin cache, so the demo is reproducible and
network-independent.

## Data and tools

- **NASA NISAR** L2 GUNW / GCOV (NASA JPL and ISRO), distributed by **ASF DAAC** via
  Earthdata — provisional stream (CRID P05023).
- **ESA / Copernicus** Sentinel-1 (C-band) and Sentinel-2 (optical).
- **Google Earth Engine** public catalogs; **WorldPop**; **OpenStreetMap**.
- **USGS** and Colombia's **SGC** earthquake parameters (cited as agency estimates).
- Public data only; no personal data. Agency names are attribution, not endorsement;
  no NASA logos or identifiers in our media.

## AI disclosure

Built with Claude Code + gstack, OpenAI Codex, Google Antigravity / Gemini, OpenCode
(GLM) and Grok, orchestrated with LangGraph. AI-written bulletins carry an
**"SI-Assisted Analytics"** badge. All measured numbers come from deterministic
tools and public data, never from a language model.

## Links

- Repository: https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango
- Live demo (Google Cloud): http://136.119.19.137:8000
- 30-second video: `{paste the uploaded video URL}`

## Team

Team **two left feet** — Medellín, Colombia. *Two left feet, one coordinated surface
tango.*
