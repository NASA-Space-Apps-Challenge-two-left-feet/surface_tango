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

### Report — grok, 2026-11-14 21:10 Bogotá

#### What was built

Numpy pipeline and CLI in `gee_math/landslide_insar_math.py`, with known-answer tests in `tests/test_landslide.py`. The legacy `compute_landslide_insar_kinematics` entrypoint is unchanged.

Commits on this branch after rebase onto `origin/main` (hashes rewritten by the rebase):

- `1f70847` `feat(landslide): add Aburrá InSAR noise-floor pipeline`
- `9aa36a7` `fix(landslide): derive FABDEM slope in a meter projection`

`ee.Terrain.slope` on the geographic FABDEM mosaic is masked. At the AOI center (−75.56, 6.285) the geographic slope was null and the slope after `reproject(crs="EPSG:3857", scale=30)` was 7.772° *(measured, `PYTHONPATH=. uv run python -u /tmp/diag_slope_proj.py`)*. The native FABDEM posting is 1 arc-second (nominal scale 30.922 m). The same center slope, 7.772°, came back when the mosaic used that native projection before the meter reprojection *(measured, `/tmp/diag_fabdem_native.py`)*.

The 80 m FABDEM grid for `1_aburra_medellin_bello` then had finite slope on 176472/176472 pixels, of which 29712 have slope ≤ 5°. Median elevation 2207.4 m. AOI-center elevation 1508.970 m *(measured, `/tmp/diag_fabdem_grid.py`)*.

Provisional P05023 stores the D-102272 UByte mask in the low 8 bits of a uint32. The first granule's AOI window had codes 16777228 (152460), 11 (24347), 16777340 (43) and 111 (9). Low 8 bits are 12, 11, 124 and 111. `product_valid_land` uses that byte. A hand test locks those codes.

#### Live run

Command, from this worktree:

```
PYTHONPATH=. PYTHONUNBUFFERED=1 uv run python -u -m gee_math.landslide_insar_math
```

Exit 0. Duration 2944.59 s. Wrote `reports/aburra.md` at 2026-11-14 21:10 Bogotá (log 2026-11-15T02:10:16Z).

Tail:

```
stack track 47 frame 5 ASCENDING: kept downslope rates on 46009 pixels; noise floor 7.898 mm (9 pairs)
stack track 11 frame 85 DESCENDING: kept downslope rates on 42508 pixels; noise floor 10.359 mm (8 pairs)
kept downslope rates on 88517 pixels; noise floor 9.105 mm (17 pairs)
wrote .../reports/aburra.md
```

Search: ASF GUNW 17; single-pol HH 17; 0 UR copies dropped. All 17 pairs returned a finite residual RMS. One earlier attempt had timed out on `NISAR_L2_PR_GUNW_029_047_A_005_030_...` (`FSTimeoutError`); the rerun read it (stable 29597, RMS 6.027 mm).

#### Measured result

Verdict *(measured, command above, `local_cache/aburra/summary.json`)*:

kept downslope rates on 88517 pixels; noise floor 9.105 mm (17 pairs)

The published floor is the median of the 17 per-pair residual RMS values (9.105440970850369 mm before `format_mm`).

| Stack | Pairs | Grid | Kept | Positive (downhill) | Negative |
|---|---:|---:|---:|---:|---:|
| track 47 frame 5 ASCENDING | 9 | 457×387 = 176859 | 46009 | 21737 | 24272 |
| track 11 frame 85 DESCENDING | 8 | 457×387 = 176859 | 42508 | 23271 | 19237 |

Stack floors: 7.898 mm (9 pairs) and 10.359 mm (8 pairs). These are medians of each stack's RMS values. 88517 is the sum of the two grids, not a count on one map.

Every pair is listed with its granule ID in `reports/aburra.md`. Two pairs are 24-day (2026-07-20 → 2026-08-13, track 11; 2026-07-23 → 2026-08-16, track 47) and stay in the denominator. Latest secondary date in the table is 2026-10-15. Product wavelength c/centerFrequency = 0.241963 m; displacement uses λ = 0.24 m.

Gate catalog, separate denominator: `nisar_colombia_granules_2026.json` `aois.1_aburra_medellin_bello.counts.GUNW` = 20, of which 17 PR and 3 UR *(measured by reading the file)*. The live search returned the 17 PR and no UR. The UR names share dates with PR pairs on track 11 frame 85.

FABDEM in the run: median elevation 2207.4 m on 176472/176472; AOI-center elevation 1509.0 m.

A kept pixel passed |LOS| > that pair's residual RMS, with the same downslope sign on two date-disjoint pairs of one native grid. Both signs are present. This is not a landslide inventory. HKLSI is not computed. Granizal 2025 is not a detection. Products are labeled PROVISIONAL.

One pair product checked after the run: `NISAR_L2_PR_GUNW_029_047_A_005_030_...npz` shape (457, 387), finite `d_los_mm` 175745 *(measured, `numpy.load`)*. Pair files on disk: 17.

#### Checks

- Before the slope commit: `uv run pytest -q tests/test_landslide.py tests/test_repo_rules.py` → 19 passed.
- `make ci` on `9fe0077` (pre-rebase hash of the slope fix) → pre-commit passed, 25 passed, 1 warning in `tests/test_llm.py` (LangGraph deprecation, untouched).
- `git fetch origin main` at commit time of the slope fix: this branch contained `origin/main`. The commit hook fetched again and passed.
- During the live run, `origin/main` gained 13 commits through `ea61e29`. The index was clean apart from the untracked report, so the branch was rebased onto `origin/main` with `git rebase origin/main` and no stash. `make sync` was not used: it rebases with `--autostash`, and stash was forbidden.
- `origin/main` then moved to `bac66dc` (README identity and stickers) while this report was being written. The brief appendix was copied aside, the tracked brief restored, and `git rebase origin/main` run again with no stash. The replay is `92b330c`, `1f70847`, `9aa36a7`. `docs/kb/gee-terrain-slope-needs-metric-crs.md` still cites the pre-rebase hash `9fe0077`.
- An earlier live attempt, before the slope fix, printed `stable=0` and `rms=nan` on every finished pair because the geographic slope was masked. It was killed before `reports/aburra.md` existed. Those pair files were removed and replaced by this run.

#### What was left undone

- No push, no merge, no branch switch, no reset, no stash.
- `README.md` was not edited. Rows are below.
- `docs/kb/` was not edited. `docs/kb/gee-terrain-slope-needs-metric-crs.md` on main cites the pre-rebase hash `9fe0077` and is `unverified`. The measurement above is the primary observation for this lane: geographic slope is masked, and EPSG:3857 at 30 m is finite.
- Cross-track agreement is not tested. LOS is the radar-grid cell nearest the AOI center, not the D-102272 §6 interpolation.

#### Open questions

- The orchestrator may want the KB note updated to the rebased hash `9aa36a7` and to the masked-versus-finite measurement.
- `scripts/build_cache.py` on main still computes slope from FABDEM in a way that note flags. That file is outside this brief.

#### README rows

Run:

```
uv run python -m gee_math.landslide_insar_math
```

The command reads the Aburrá box from `config/bailasar.yaml`, searches ASF, samples FABDEM, and writes `local_cache/aburra/` plus `reports/aburra.md`.

| Component | State | Issue | Report |
|---|---|---|---|
| Landslide InSAR noise floor | cached | #33 | reports/aburra.md |

State is cached: the live ASF + GEE run wrote `local_cache/aburra/pairs/` (17 npz), `local_cache/aburra/stacks/` (2 npz) and `local_cache/aburra/summary.json`. The UI does not read them.

Suggested measured sticker (img.shields.io, links to `reports/aburra.md`, no NASA mark): noise floor 9.105 mm on 17 pairs. The number is the median residual RMS from the command above.
