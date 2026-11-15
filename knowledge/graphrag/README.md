# Landslide conceptual-grounding GraphRAG

A local **Microsoft GraphRAG** knowledge graph (built with **Azure OpenAI**) that
grounds the landslide agent in Colombia's official landslide methodology and
Medellín's prioritized detailed-risk studies — so the agent reasons inside the
**SGC framework** (*amenaza · vulnerabilidad · riesgo*) instead of from scratch.

## What's committed vs. not

- **Committed (our code/config):** `settings.yaml`, `sources.yaml`, `ingest.py`,
  `retrieve.py`, `prompts/`, this README.
- **Never committed (git-ignored under `local_cache/graphrag/`):** the extracted
  text (`input/`), the built index (`output/`, LanceDB), the cache and logs. The
  source PDFs live **outside** the repo. The SGC guide and the POT resolutions are
  **public official documents**, cited by resolution number in `sources.yaml`; the
  derived index is not committed (AGENTS.md: external material is never copied in).

## Corpus (`sources.yaml`)

SGC *Guía metodológica* (escala detallada + 1:25.000) for the conceptual
framework, plus Medellín POT detailed-risk resolutions for the prioritized Valle
de Aburrá polygons: **La Picacha, Parque Popular, Carabineros, Parque Complex 2,
Colegiatura**, and the city-wide *zonas con condición de riesgo* (Res. 202250081537
de 2022). ~8 docs, ~3.9 MB of extracted text.

## Build it

1. **Azure OpenAI** — create a resource and deploy two models: a chat model
   (e.g. `gpt-4o-mini`) and an embedding model (e.g. `text-embedding-3-small`).
   Put the values in the repo `.env` (never in git):
   ```
   GRAPHRAG_API_KEY=<azure key>
   GRAPHRAG_API_BASE=https://<resource>.openai.azure.com
   GRAPHRAG_API_VERSION=2024-10-21
   GRAPHRAG_CHAT_DEPLOYMENT=<your chat deployment name>
   GRAPHRAG_CHAT_MODEL=gpt-4o-mini
   GRAPHRAG_EMBEDDING_DEPLOYMENT=<your embedding deployment name>
   GRAPHRAG_EMBEDDING_MODEL=text-embedding-3-small
   ```
2. **Extract text** → git-ignored `local_cache/graphrag/input/`:
   ```
   uv run python -m knowledge.graphrag.ingest
   ```
3. **Build the graph** (Azure OpenAI does entity/relationship/community extraction):
   ```
   uv run graphrag index --root knowledge/graphrag
   ```

## Query it (agent grounding)

```
uv run python -m knowledge.graphrag.retrieve --method global \
  "Which Valle de Aburra polygons are prioritized as high landslide risk and why?"
uv run python -m knowledge.graphrag.retrieve --method local \
  "What conditioning and triggering factors does the SGC method use for landslide hazard?"
```

`retrieve.ground(question, method)` returns an evidence envelope
(`state: grounded | not_built | error`) — never a fabricated answer, matching the
project's no-synthetic-data rule. The landslide agent calls `local` for
study-specific questions and `global` for prioritization/overview questions.

## Entity types (domain-tuned)

`place · organization · hazard_factor · triggering_factor · exposed_element ·
risk_zone · mass_movement · methodology` — the SGC ontology, so the graph links
methodology concepts to the evidence in each study.
