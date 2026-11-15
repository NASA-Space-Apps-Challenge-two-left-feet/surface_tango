---
title: The orchestrator LLM uses Vertex AI Gemini (ADC) as primary; activate with two commands when hosted token-gateways are exhausted
status: verified
source: config/bailasar.yaml
accessed: 2026-11-15
quote: "Gemini via Vertex AI (ADC, no key)"
used_in: [agents/llm.py, config/bailasar.yaml, "#36"]
verified_by: LEONOB2014
supersedes: null
---

All hosted token-gateways (Featherless, Nebius Token Factory, OpenRouter,
Blaxel) ran out of credits on 2026-11-15. The orchestrator chain
(`config/bailasar.yaml` `llm:`) now lists **Gemini via Vertex AI** first
(`gemini-2.5-flash`, then `gemini-2.0-flash`), falling back to the gateways when
their keys/credits return. The agents only write placeholder prose, so Gemini
Flash (hosted on the project's GCP budget) is ample and costs ~fractions of a
cent per bulletin.

`agents/llm.py` builds a `vertex`-type provider with **ADC** (the same identity
as `init_ee()`) and `GCP_PROJECT_ID` — no API key. The import of
`langchain-google-vertexai` is lazy and ADC-checked, so if the library or ADC is
absent the entry is **skipped** (like a missing key) and the chain falls through;
`build_models` raises a message naming Vertex only when nothing is usable.

**Activate (two commands, verified ADC project `loyal-curve-472605-g7`):**
1. `gcloud services enable aiplatform.googleapis.com --project=loyal-curve-472605-g7`
2. `uv add langchain-google-vertexai`

Then the graph uses Gemini automatically (ADC already works). The demo itself is
credit-free regardless: `make pitch` serves cached bulletins (`BulletinCache`,
`local_cache/llm_bulletins`) with no live LLM call.
