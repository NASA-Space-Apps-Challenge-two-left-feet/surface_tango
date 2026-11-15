# Brief: feat/quake-dpm-v2 — finish the quake damage proxy (agent: opencode GLM-5.3)

- **Goal:** take the merged quake damage proxy (#64) from "track 11, municipios, hand-written Parquet" to a complete, reproducible product. The work:
  - both tracks;
  - parameters read through the shared config loader;
  - a real Parquet engine;
  - pluggable unit polygons, so barrios drop in when #24 adopts them;
  - statistics that **cannot leak before the pre-registration freeze**;
  - a written report.
- **Issue:** #31 (plan 03-02) · **Owner:** LEONOB2014 · **Reference:** `docs/designs/bailasar.md` § Hazard 2; `validation/README.md` (pre-registration, deviation 1, "Differences from blob 8d91f1d").
- **Inputs:**
  - `gee_math/earthquake_dpm_math.py` (merged in #64): read all of it before changing anything.
  - `tests/test_earthquake_dpm.py`.
  - The shared loader `src/bailasar/config.py`: `load_config()`, `cfg.prereg("…")`, `cfg.is_frozen` (#85).
  - The hour-2 gate catalog `nisar_colombia_granules_2026.json` → `quake_triplets`, with tracks 11 and 47.
  - `reports/gate.md`.
  - Maru's `reports/ground_truth.md` and `reports/ground_truth_armenia_boundaries.md` (#97): candidate polygon layers, **not adopted**.
  - Credentials from the linked `.env`: Earthdata token; Earth Engine via `gee_math/ee_session.init_ee()`.
- **Files you may touch:**
  - `gee_math/earthquake_dpm_math.py`
  - `tests/test_earthquake_dpm.py`
  - `pyproject.toml` + `uv.lock` (add `pyarrow` only)
  - `reports/quake_dpm.md` (new)
  - `docs/kb/` (new notes only)
  - this brief
- **Out of scope:**
  - `validation/scoring.py` and the scorecard (#32, Maru)
  - `config/preregistered.yaml` and `validation/README.md` (#25/#26, Jack)
  - the MCP servers, the UI, the README
  - adopting barrio polygons (Maru #24 decides)
  - any GCS upload

## Hard rule: C-pair statistics stay sealed (read this twice)
A previous run printed C-pass statistics before the freeze, which is deviation 1 in `validation/README.md`. That must not happen again.
- Until `cfg.is_frozen` is true, **no statistic of the C pass or the K pass** may be:
  - printed;
  - logged;
  - written into any `.md`, `.txt` or `.json` you create;
  - or shown in your chat output.

  Sealed statistics include μ, σ, median Z per class, excess E, per-unit DPM values and any quantile.
- The sealed statistics stay only inside the git-ignored `local_cache/quake/` outputs (Zarr attrs, Parquet).
- `_summary_line()` (currently around line 1087) prints them today. Gate it: when the pre-registration is not frozen, it prints only **pixel and unit counts** (window size, valid pixels, built-up and non-built pixel counts, units evaluated and excluded) and the line `C/K statistics sealed until pre-registration freeze (status=<status>)`.
- **Test it:** a test runs the summary path on hand-made inputs with `status: draft` and asserts that stdout contains no μ/σ/median/excess values, using `capsys`.
- **Don't open or read** the existing `local_cache/quake/dpm_track11.zarr` attrs or `barrio_dpm.parquet` values. You may check that they exist and count their rows or bands.

## Steps
1. **Parameters through the shared loader.**
   - Replace the module's own YAML reading with `src/bailasar/config.load_config()` (`cfg.prereg("quake.…")`). If `src/` isn't importable, use the same path insert `tests/test_config.py` uses.
   - Record `cfg` hash and status in the provenance.
   - Don't hardcode any threshold.
2. **Pairs from the gate catalog.** Read R/C/K for a track from `nisar_colombia_granules_2026.json` → `quake_triplets`, the gate's frozen choice, instead of re-discovering them.
   - Keep `discover_pairs` only as a fallback.
   - If a discovered pair differs from the catalog, fail with both IDs printed.
   - `config/preregistered.yaml` `quake.pairs` is changing shape in #86. Don't depend on it in this PR; add a TODO naming #86.
3. **Real Parquet.**
   - Add `pyarrow` to `pyproject.toml` (`uv add pyarrow`).
   - Replace `write_parquet`/`read_parquet` and the thrift byte-packing with `pyarrow.parquet`. Keep the column names, types and NaN semantics.
   - Keep the round-trip test, now through pyarrow.
   - Delete the hand-written writer.
4. **Pluggable units.** Units come from one of:
   - the GEE asset (current: GAUL ADM2 municipios, `--units-asset`, `--units-name-prop`);
   - or a local GeoJSON/GeoPackage file (`--units-file PATH --units-id-prop NAME`).

   Record in provenance: the source (asset ID or file path + sha256), the CRS and the feature count.
   - Add a hand-made 3-polygon GeoJSON fixture test: rasterization assigns the right pixels, a unit with fewer than 20 built-up pixels is excluded and counted, unit IDs are unique.
   - Don't download or adopt Maru's candidate layers. Only make the code ready for them.
5. **Track 47.** Run `uv run python -m gee_math.earthquake_dpm_math --track 47` in the **foreground** (watch the output), then re-run track 11 with the new code to confirm the counts match #64: 32 units, 28 evaluated, 4 excluded; valid 316,399 of 10,353,357 px. A mismatch is a finding: report it, don't paper over it.
   - If track 47's K arrives from a different frame, record it.
   - If a granule read stalls, apply the per-granule session, timeout and retry pattern in `docs/kb/nisar-gcov-read-timeouts.md`, and record a stuck granule as `missing`.
6. **Report** `reports/quake_dpm.md`, with counts only and no sealed statistics:
   - the command per track;
   - R/C/K granule IDs;
   - baseline days and the mismatch (C 24 d vs R and K 12 d, disclosed);
   - window size;
   - valid, built-up and non-built pixel counts with denominators;
   - units: total, evaluated and excluded, with names and pixel counts;
   - the unit source;
   - the outputs and their sizes (`du -sh`);
   - the "sealed until freeze" line;
   - a short "How #32 consumes this" section: the column names, unit ID and where the pre-registered `k` comes from;
   - a "README rows" subsection for the orchestrator.
7. **KB.** If you verify something new, such as GUNW mask semantics or pyarrow NaN handling, add a note from `docs/kb/TEMPLATE.md`.

## Acceptance
- `make ci` green. All existing DPM tests still pass, plus new ones: the sealed-summary test, the units-file fixture test and the pyarrow round-trip.
- `rg -n 'thrift|struct\.pack' gee_math/earthquake_dpm_math.py` is empty.
- Track 11 rerun reproduces #64's counts (or the mismatch is explained). Track 47 outputs exist in `local_cache/quake/` with their sizes listed.
- `reports/quake_dpm.md` has **no** μ/σ/median/excess numbers. The orchestrator will grep for them before merging.
- One logical change per commit (Conventional Commits, `Refs: #31`, `Co-Authored-By: opencode GLM-5.3`). Run `make sync` before each commit.

## Outward or paid actions needing approval
None allowed. Read-only ASF and Earth Engine calls with the existing credentials are fine. **Don't:**
- push, merge, switch branches, reset, stash or rebase;
- run `gh`;
- write to GCS;
- call a paid API beyond those reads.

## If blocked
Write `BLOCKED: <reason>` at the end of this file and stop. Examples: the loader can't express a needed key, or a granule is missing for track 47.

## Report (append to the end of this file when done)
What you built, commands run with their output tail (counts only), what you could not do, open questions.
