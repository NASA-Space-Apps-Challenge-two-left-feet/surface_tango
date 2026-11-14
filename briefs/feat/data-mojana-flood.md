# Brief: feat/data-mojana-flood — La Mojana dual-pol flood classes (agent: grok2)

- **Goal:** classify open water and flooded vegetation in La Mojana from NISAR GCOV HH/HV, with the dry-baseline rule and sensitivity ranges.
- **Issue:** #34 (plan 03-05) · **Plan reference:** docs/designs/bailasar.md § Hazard 3; requirements FLOOD-01, FLOOD-02
- **Inputs:** the 38 La Mojana GCOV (Jun 17 → Nov 14); MERIT Hydro HAND via GEE (`init_ee()`); Sentinel-1 VV/VH water mask for the L-vs-C comparison; thresholds from `config/preregistered.yaml` (`flood:`).
- **Outputs:** `gee_math/flood_polarimetric_math.py` pure functions + CLI writing `local_cache/mojana/` class rasters and `reports/mojana.md`; `tests/test_flood.py`.
- **Files you may touch:** `gee_math/flood_polarimetric_math.py`, `tests/test_flood.py`, `reports/mojana.md`, this brief.
- **Out of scope:** quad-pol H/ᾱ or Freeman (Colombia is dual-pol), attributing water to the breach vs season, biomass, UI.
- **Steps:**
  1. Known-answer tests first: open-water fraction f per date (HH γ0 < −18 dB inside HAND < 18 m); driest date = min f; if (f_wet − f_dry)/f_wet < 0.20 or f_wet = 0 → no baseline: report absolute water extent per date and **Class 2 = null**; Class 1: ΔHH < −5.5 dB; Class 2: ΔHH > +3 dB **and** |Δ(HV/HH)| < 1.5 dB; all thresholds read from config; label them uncalibrated.
  2. Sensitivity: hectares at each dB threshold ±1 dB and HAND 12/18/24 m; valid-pixel denominator.
  3. Run on real GCOV; write `reports/mojana.md` with granule IDs, chosen reference date and why, hectares per class with denominators and sensitivity ranges *(measured)*, and the S1 comparison.
- **Acceptance:** `make ci` green; tests cover baseline/no-baseline branches, f_wet = 0, both classes, threshold read from config; report has IDs and denominators.
- **Outward or paid actions needing approval:** none allowed (local only).
- **If blocked:** write `BLOCKED: <reason>` below and stop.
- **Coordination:** issue #19 (EstebanOchoaedos) wires this module to the config in Phase 1; keep his config hook if it lands first.

## Facts from the hour-2 gate (measured 2026-11-14, ASF search, read-only)
- NISAR public window starts 2026-06-17. All products found are **provisional** (`PR`, CRID P05023); label them PROVISIONAL.
- Eje Cafetero (quake), GUNW are **single-pol HH** (`SH`), 12-day pairs, except around the event:
  - Track 11 descending, frame 86: … Jun 26→Jul 8 (K), Jul 8→Jul 20 (R), **Jul 20→Aug 13 (C, 24-day; also an `UR` Urgent-Response copy)**, Aug 13→Aug 25 …
  - Track 47 ascending, frame 4: Jun 17→Jun 29, Jun 29→Jul 11 (K), Jul 11→Jul 23 (R), **Jul 23→Aug 16 (C, 24-day)** …
  - **C spans 24 days, R and K 12 days** (the Aug 1 / Aug 4 acquisitions are missing). Per the gate table this is "closest available, mismatch recorded": never hide it; the built-up vs non-built excess E is relative, which partly absorbs extra temporal decorrelation, but report the mismatch next to every number.
- GUNW counts in window: Aburrá 11, Eje Cafetero 11 (+UR), La Mojana 31. GCOV: 14 / 14 / 38.
- AOI bboxes [W,S,E,N] used for search (estimates until set in `config/bailasar.yaml`): Aburrá [-75.70, 6.12, -75.42, 6.45]; Eje Cafetero [-75.85, 4.40, -75.40, 5.15]; La Mojana [-75.40, 7.90, -74.20, 9.20].
- GUNW layers: coherence at 20 m and 80 m, unwrapped phase 80 m, ionosphere screen **included but not applied** (docs/kb/nisar-gunw-layers.md).
- Credentials are in the linked `.env` (Earthdata token works; GEE via `gee_math/ee_session.init_ee()`; never print values). `config/` loader (#17) is not merged yet: read `config/preregistered.yaml` with `yaml.safe_load`, never hardcode its numbers.

## Rules (from AGENTS.md, non-negotiable)
- No synthetic or fabricated data. Missing stays NaN and is marked `missing`. Tests may use small hand-written arrays with hand-computed expected values (tests/ only).
- Every number you report: *(measured)* with the command and granule IDs, or *(estimate)*. Nulls are reported.
- Touch only the files listed below. If you need anything else, write `BLOCKED: <reason>` at the end of this brief and stop.
- Commit locally with Conventional Commits (`git commit -F <file>`), one logical change per commit, body ends with `Co-Authored-By: <your agent name>` and `Refs: #<issue>`. Run `make ci` before each commit and fix failures (never `--no-verify`).
- **Do not** push, merge, switch branches, reset, stash, open PRs, write to GCS, or run paid LLM calls. The orchestrator reviews the full diff and does those.

## Report (append to the end of this file when done)
What you built, commands run with their output tail, measured numbers with IDs, what you could not do, open questions.
