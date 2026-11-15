# Brief: feat/quake-epicenter-build — damage proxy over the Chocó epicenter AOIs

**Runnable by any agent with GEE + Earthdata (ADC works; `init_ee()`), or directly — the build scripts use NO LLM, so the token-gateway exhaustion does not block this.** Heavy GEE/download job; run in the foreground.

- **Goal:** produce the coherence-loss damage proxy over the two new operational AOIs added in #190 — **`4_choco_epicenter_quake`** (the demo money shot: the optically-blind USGS epicenter) and **`5_valle_del_cauca_quake`** — so the earthquake chapter shows real L-band damage-proxy coverage at the epicenter. **Chocó first.**
- **Issue:** #31 (additional coverage). **Reference:** `scripts/discover_nisar_colombia.py`, `scripts/build_cache.py`, `gee_math/earthquake_dpm_math.py` (`resolve_aoi`, `discover_pairs`, `run_dpm_pass`), `reports/quake_extended_aois.md` (measured coverage + co-event triplets), `docs/kb/quake-epicenter-optical-blind.md`.

## Hard constraints
- **These are operational AOIs, NOT the frozen scorecard.** `config/preregistered.yaml` is **frozen** (`36a90fa`) — never edit it. The frozen `quake.pairs` are Eje Cafetero; these AOIs use **their own co-event R/C/K triplets** from the gate (discovered, not the frozen pairs).
- **No synthetic data.** Missing stays NaN + `missing`. Every number *(measured)* with denominator + scene IDs.
- **No outside narrative/statistics** — only ASF search, GEE, public geography, the USGS event page.
- **Caveats carry over:** baseline mismatch (C 24 d), "proxy contrast, PROVISIONAL, not a validated scorecard", post-event-control where applicable. Never "beats baseline".

## Steps
1. **Extend the gate catalog.** Add the two AOIs' granules + co-event triplets to the discovery output (run `scripts/discover_nisar_colombia.py` — it reads AOIs from `config/bailasar.yaml`, which now includes `4_choco_epicenter_quake`/`5_valle_del_cauca_quake`). Verify the Eje/Aburrá/Mojana entries and the frozen quake triplets are unchanged (same data); if the script would overwrite them, write the new AOIs to a separate catalog and keep the committed one intact. Record the co-event R/C/K per track per AOI (Chocó: co-event on tracks 11/47/148; Valle: 11/47/112/148 — measured in `reports/quake_extended_aois.md`).
2. **Build the Chocó cache** (`4_choco_epicenter_quake`): coherence R/C/K from its own co-event triplet, GCOV, and ancillary (WorldCover, FABDEM, `hand_m`), with the provenance manifest. Missing bands → NaN + `missing`.
3. **Run the damage proxy** over Chocó with its own triplet (use the DPM module's `--aoi` + the AOI's discovered pairs; do not reuse the frozen Eje pairs): non-built Z, clamp, masks, built-up classes, unit counts. Emit `local_cache/choco_epicenter/quake_evidence_track<N>.json` via `scripts/write_hazard_evidence.py` (extend it for the new AOI if needed).
4. **Report** `reports/quake_epicenter.md`: per track, window + valid/built-up/non-built pixel counts with denominators, the co-event triplet IDs, the E_C−E_K excess (frozen-method, PROVISIONAL), the baseline-mismatch + post-event caveats, and the "optically-blind epicenter" framing (link the KB note). Then repeat for Valle del Cauca if time allows.
5. Confirm `analyze_earthquake_dpm(aoi="choco_epicenter", track=N)` serves the evidence.

## Acceptance
- `make ci` green; the Chocó cache + at least one track's damage proxy + `reports/quake_epicenter.md` with measured counts and co-event IDs; the frozen `config/preregistered.yaml` untouched; the committed gate catalog's existing AOIs/triplets unchanged.
- No number without a source; nothing claims "beats baseline".

## Rules
- Files you may touch: `scripts/discover_nisar_colombia.py`, `scripts/build_cache.py`, `scripts/write_hazard_evidence.py`, `gee_math/earthquake_dpm_math.py` (AOI/triplet parameterization only), `tests/test_*`, `reports/quake_epicenter.md`, `nisar_colombia_granules_2026.json` (only to ADD the new AOIs without changing existing entries), this brief. Writing `local_cache/choco_epicenter/` + `local_cache/valle_del_cauca/` is expected.
- `make sync` + `make ci` before each commit (Conventional Commits, `Refs: #31`). Earth Engine via `init_ee()`; foreground; stalled granule → `missing`; no `.resample("nearest")`. Do **not** push, merge, switch branches, reset, stash, open PRs, run `gh`, or write to GCS.

## If blocked
Write `BLOCKED: <reason>` and stop (e.g. a granule missing for a track, or the triplet parameterization needs an orchestrator decision).

## Report (append when done)
Per AOI/track: window + pixel counts with denominators, co-event triplet IDs, E_C−E_K (PROVISIONAL), caveats, output sizes, and the tool-serves-it check.
