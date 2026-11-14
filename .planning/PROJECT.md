# BailaSAR

## What This Is

An interactive NISAR L-band observatory for three Colombian hazards: Aburrá Valley landslides, the 2026-08-10 M7.4 earthquake (damage assessment and first-aid ranking), and the La Mojana / Caregato flood. It is built by a 6-person team for NASA Space Apps 2026 ("Dancing with the SARs", Medellín, Nov 14–15). The source spec is `docs/designs/bailasar.md` (approved, with eng review D1–D17).

## Core Value

One honest, measured radar result, shown in a 30-second video. Ideally it is the quake first-aid ranking scored against a population-only baseline and a control pair. If the data says "uninformative" or "no gain", that verdict is the headline.

## Requirements

### Validated

(None yet — ship to validate)

### Active

See `.planning/REQUIREMENTS.md` (v1: GATE, DATA, CFG, QUAKE, SCORE, SLIDE, FLOOD, MCP, AGENT, BULL, UI, VID, SUB, KB).

### Out of Scope

- Biomass agent / root cohesion — dropped from the hackathon scope (TODO 1)
- ISRO S-band fusion — no Colombia coverage found (TODO 2)
- GOFF surface rupture — the quake was 96 km deep, so there is no rupture (TODO 3)
- Quad-pol H/ᾱ, Freeman — Colombia is dual-pol HH/HV (TODO 4)
- RSLC→coherence generation — not feasible in 30 h; a missing GUNW pair counts as missing
- "What radar knew" time-machine replay (TODO 5)

## Context

- The repo starts from the imported Gemini scaffold (PR #14), with the synthesizer removed.
- Data: NISAR L2 GCOV/GUNW from ASF. The public record starts 2026-06-17; products before 2026-11-06 may be provisional.
- Rules: `AGENTS.md`. Trunk-based, one worktree per branch, local CI gate, no synthetic data, living KB in `docs/kb/`.

## Constraints

- **Timeline**: ~28 build hours; the submission deadline D must be recorded (SUB-01)
- **Evidence**: measured numbers only, with denominators and intervals; nulls reported; no synthetic data
- **Demo**: ≤30 s video with English subtitles; no NASA logos; AI disclosure
- **Budget**: GitHub Actions minutes; one job on ready PRs only
- **Security**: credentials only in `.env`; secret scan before the repo goes public

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Two MCP processes, SSE (D1, D4) | Owner's choice; process isolation | — Pending |
| Import Gemini baseline without synthesizer (D2) | One shared interface for 6 lanes | ✓ Good (PR #14) |
| Frozen `config/preregistered.yaml` + operational `config/bailasar.yaml` (D5, D13) | Freeze proof survives operational tuning | — Pending |
| Ground-truth timebox hour 4 + power check + headline decided at hour 4 (D10, D11) | Avoid finding out at hour 14 that the quake headline cannot work | — Pending |
| Breaker budgets measured at the hour-2 gate (D6, kept in D14) | Measured, not guessed | — Pending |
| Known-answer logic tests with hand-written arrays (D15) | Tests exist before the number they protect | — Pending |
| Video recorded through the agent stack (D17) | Owner's choice; accepted risk | ⚠️ Revisit |

---
*Last updated: 2026-11-14 after GSD Core ingest of docs/designs/bailasar.md*
