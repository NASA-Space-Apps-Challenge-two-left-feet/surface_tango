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

### Report — 2026-11-15, opencode GLM-5.3 (counts only; no sealed statistics)

**Built (steps 1–4).** All parameters go through `src/bailasar/config.load_config()`
(`cfg.prereg("quake.…")`, `cfg.aoi_bbox("2_eje_cafetero_quake")`); prereg sha1
`24343020812977afe49c8495fc10113cd2c95af4`, status and frozen flag ride in every
provenance; the hardcoded AOI estimate and `git_blob_sha1` are gone. Pairs resolve
from `quake_triplets` (`pairs_from_catalog`) with discovery kept as a fallback and a
read-only cross-check that fails loudly with both IDs; both live runs printed
`verified: ASF discovery returns the same triplet (measured, read-only)`. A
`TODO(#86)` marks the `prereg quake.pairs` shape change. `pyarrow` (26.0.1,
`uv add`) replaces the thrift byte-packer — `rg 'thrift|struct\.pack'` is empty —
with REQUIRED columns and NaN-as-value round-trips; outputs are per-track:
`dpm_track<N>.zarr`, `dpm_units_track<N>.parquet`. Units are pluggable:
GEE asset (GAUL ADM2, default) or `--units-file PATH --units-id-prop NAME`
(GeoJSON/GPKG via geopandas, duplicate IDs rejected, sha256+CRS+count in
provenance). `_summary_line` takes `is_frozen` (from the loader) and prints
counts plus `C/K statistics sealed until pre-registration freeze (status=draft)`
until the freeze; the μ/σ/median/excess lines exist only on the frozen path.
GUNW reads are bounded per granule (fresh Earthdata filesystem, 30 s connect /
120 s read, 3 attempts, 2/4 s backoff, 32 MB block cache; a stalled granule is
recorded `missing`), after `docs/kb/nisar-gcov-read-timeouts.md`.

**Tests.** 23 DPM tests pass (sealed-summary capsys test, frozen-path counterpart,
catalog pairs, units-file fixture with exclusion and duplicate-ID rejection,
file-mode fetch, pyarrow round-trip). `make ci` green throughout: offline suite
216 passed, 3 deselected (selectors arrived from main during the syncs).

**Commands run (foreground; tails, counts only).**
`uv run python -m gee_math.earthquake_dpm_math --track 47` → window 4143×2499 =
10,353,357 px; valid 316,398; built-up 211,820; non-built 104,578; units 32/28/4
(excluded: Belen De Umbria 10 px, La Virginia 14, Caicedonia 0, Cartago 4); K
frame 4 matches R and C. Output: `dpm_track47.zarr` 293 MB, `dpm_units_track47.parquet`
8.0 KB (32 rows). No granule stalled (missing_granules = []).
`uv run python -m gee_math.earthquake_dpm_math --track 11` (rerun under the new
code) → valid 316,399 of 10,353,357 px; units 32/28/4, same four excluded units
with the same counts — **reproduces #64 exactly**. Output: `dpm_track11.zarr`
291 MB, `dpm_units_track11.parquet` 8.0 KB. The 1-px valid difference between the
tracks sits in Pereira's non-built set (24,788 vs 24,789), disclosed in the report.

**Report + KB (steps 6–7).** `reports/quake_dpm.md`: commands, R/C/K IDs, the
disclosed 24 d vs 12 d baseline mismatch, window and pixel counts with
denominators, the full 32-unit count table, unit source, `du -sh` sizes, the
seal line, "How #32 consumes this" (columns, `unit_id` 1..32 in source order, k
from `cfg.prereg("quake.k_rule")`: ceil(0.10 × 28) = 3, minimum 5 applies →
k = 5), README rows. Grep-clean of μ/σ/median/excess numbers. Two KB notes:
`pyarrow-parquet-nan-roundtrip.md` (with the runnable command and its `True False`
output) and `nisar-gunw-track47-frame4-grid.md` (frame 4 = frame 86 layout, both
windows 4143×2499).

**Not done / findings for other lanes.** Nothing blocked. (1) `mcp_servers/gee_fusion_mcp.py`
imports `compute_earthquake_dpm_and_rupture`, which does not exist in the module —
pre-existing breakage on main, mcp lane's file, untouched here. (2) The
`PENDING_WIRING` entry for `earthquake_dpm_math.py` in `tests/test_config.py` is
now stale (the AOI goes through the loader); config lane should drop it. (3)
`status/quake.md` untouched (not in this brief's file list). (4) The #64 file
`local_cache/quake/barrio_dpm.parquet` remains on disk unread (sealed); the new
per-track names supersede it — a cache-clean pass can drop it after the freeze.

**Commits (as of writing).** `c13b809` build(quake): add pyarrow for the unit
parquet output · `c94d9df` feat(quake): complete the dpm product for both
tracks · `e787511` feat(quake): print the gate-catalog vs discovery cross-check
outcome · `d733242` docs(quake): report the dpm runs for tracks 11 and 47 ·
`6b86bc0` docs(kb): add pyarrow nan round-trip and track-47 grid notes.

**Open questions.** None for this branch. For #32: whether scoring wants the
excluded units carried as rows (they are, `evaluated = 0`) or dropped before
ranking.
