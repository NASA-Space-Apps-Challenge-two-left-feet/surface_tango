# Brief: feat/data-aburra-insar — Aburrá landslide InSAR with honest noise floor (agent: grok)

- **Goal:** turn Aburrá GUNW pairs into LOS/downslope displacement with an explicit noise-floor verdict.
- **Issue:** #33 (plan 03-04) · **Plan reference:** docs/designs/bailasar.md § Hazard 1; requirements SLIDE-01, SLIDE-02
- **Inputs:** the 11 Aburrá GUNW (12-day pairs, single-pol HH) in the Jun 17 → Nov 14 window; FABDEM via GEE (`init_ee()`); unwrappedPhase, ionosphericPhaseScreen, connectedComponents, coherenceMagnitude (80 m).
- **Outputs:** `gee_math/landslide_insar_math.py` pure functions + CLI writing `local_cache/aburra/` products and `reports/aburra.md`; `tests/test_landslide.py`.
- **Files you may touch:** `gee_math/landslide_insar_math.py`, `tests/test_landslide.py`, `reports/aburra.md`, this brief.
- **Out of scope:** HKLSI calibration claims, Granizal 2025 as a detection (it predates NISAR), flood/quake code, UI.
- **Steps:**
  1. Known-answer tests first: subtract the **provided** ionosphere screen; stratified troposphere = LOS-vs-elevation linear fit on stable valley-floor pixels; mask layover/shadow; keep the reference connected component; d_LOS = −λΔφ/4π with λ = 0.24 m (check the sign convention against the product spec and cite it in a comment); projection onto downslope (slope/aspect from FABDEM).
  2. Noise-floor rule: keep a rate only where |rate| > stable-pixel residual RMS **and** the sign agrees across two independent pairs; otherwise output exactly "no motion detected above X mm (n pairs)".
  3. Run on all available Aburrá pairs; write `reports/aburra.md` with granule IDs, n pairs, noise floor in mm *(measured)*, and the verdict (a null is a valid result).
- **Acceptance:** `make ci` green; tests cover iono subtraction, tropo fit on a hand-built ramp, sign convention, noise-floor accept/reject; report has IDs and denominators.
- **Outward or paid actions needing approval:** none allowed (local only).
- **If blocked:** write `BLOCKED: <reason>` below and stop.
- **Coordination:** issue #19 (EstebanOchoaedos) wires this module to the config in Phase 1; keep his config hook if it lands first, and do not remove functions he added.

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

## Update 2026-11-14 19:55 Bogotá (orchestrator): resume
Your first run (grok) stopped on a 600 s background-wait timeout before any commit. State it left:
- `gee_math/landslide_insar_math.py` modified (about 1.5k lines) and `tests/test_landslide.py` new, both uncommitted; `uv run pytest -q tests/test_landslide.py` gives 12 passed *(measured 19:50)*. Your log claimed 15: reconcile.
- It stopped while wrapping long lines, before the known-answer tests were complete and before any live Aburrá pair was processed. `reports/aburra.md` doesn't exist yet.
Resume order: review your diff, finish the known-answer tests (iono subtraction, tropo ramp, sign convention, noise-floor accept/reject), run `make ci`, commit (Refs: #33), then run the live Aburrá pairs and write `reports/aburra.md` with granule IDs, n pairs and the noise floor in mm *(measured)*. A null verdict is valid.
- Your worktree was synced onto the latest `origin/main` by the orchestrator. Run `make sync` again before every commit.
- AOIs now live in `config/bailasar.yaml` under `aois:` (`1_aburra`, `2_eje_cafetero_quake`, `3_la_mojana_caregato`). Read them from there with `yaml.safe_load`; don't copy the bboxes into code.
- The gate catalog is `nisar_colombia_granules_2026.json` at the repo root (not under `local_cache/`). `scripts/discover_nisar_colombia.py` is the reference for parsing NISAR names (stream, product, polarization, dates).
- Ruff no longer checks line length (E501 is ignored; the formatter owns it). Don't spend time wrapping lines.
- New README rule (AGENTS.md "README kept current"): `README.md` is not in your file list, so don't edit it. Instead, add a short "README rows" subsection to your Report with the setup/run command and the Status-table row (component · state · issue · report) for the orchestrator to paste.
- Run long jobs (live downloads, GEE exports) in the foreground, or poll them to completion. The CLI ends background work after its wait timeout.

## Report (append to the end of this file when done)
What you built, commands run with their output tail, measured numbers with IDs, what you could not do, open questions.
