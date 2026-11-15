# Status: quake

## Config loader (#17, Jack4Codes)

_Last update: 2026-11-14 (UTC−5)_

- Doing: 01-02 config loader (#17), branch `feat/quake-config-loader-for-prereg`
- Done:
  - `src/bailasar/config.py`: one loader for `config/preregistered.yaml` + `config/bailasar.yaml`; no defaults (missing key, null value or AOI without a gate bbox raises `ConfigError`); read-only views; `git hash-object`-compatible hash; `require_frozen(expected_hash)` for CFG-02 (#26)
  - `tests/test_config.py`: 27 offline tests, including a guard that fails on any new hardcoded flood threshold or AOI coordinate in `scripts/`, `gee_math/`, `mcp_servers/`, `agents/`, `src/`, `app.py`
- Blocked: none (`.secrets.baseline` landed on main; branch synced to `origin/main` 7ce0917)
- Handoffs (files owned by other plans still carry config literals; listed in `PENDING_WIRING` in `tests/test_config.py`, remove the entry once wired):
  - `gee_math/flood_polarimetric_math.py` lines 50, 67, 76 (HAND 18 m, −5.5 dB, +3.0 dB) → 01-04
- Needs the 01-01 owner (`pyproject.toml`): `src/` is not on the import path yet (pytest `pythonpath` is `["."]`). `tests/test_config.py` adds it itself; other modules need either `[tool.pytest.ini_options] pythonpath = ["src", "."]` plus a build backend so `uv sync` installs `bailasar`, or the same path insert.

## Scoring functions (#18, Maru816)

- Implemented the pure scoring library and known-answer tests: percentile ranking, precision@k, Wilson intervals, whole-barrio paired bootstrap, built-up excess, informative gate and directional claim rule.
- Stable original unit identity resolves tied rankings consistently across repeated bootstrap draws. Test fixtures and API boundaries are documented in `validation/ALLOWLIST.md`.
- Publication scope: issue #18 only. Real-data scorecard assembly (#32) remains blocked by accepted labels, frozen pre-registration and pipeline inputs. No co-event data were opened.
- Validation: publication checks use `make check`, `make test`, explicit hooks on new files and `make ci`. Pure-logic fixtures use no source granules.

## Ground truth (#24, Maru816)

- Completed the source review and documented candidate municipal damage reports and neighborhood boundaries for Armenia, Pereira and Manizales in `reports/ground_truth.md`.
- Armenia boundary audit and conservative name crosswalk are documented separately. Supporting raw GIS snapshots, CSVs and map remain in ignored local cache; no geometry was silently repaired and no damage labels were assigned.
- Acceptance gaps remain: complete neighborhood assessment coverage, official boundary adoption/vintage/terms, stable identities, topology review and ambiguous locations. This is a research handoff, not accepted scientific ground truth.
- The official power/headline decision (#25), configuration freeze (#26) and real scorecard (#32) remain with their respective tasks. The latest upstream data gate (#23) is available.
- Validation: publication checks use `make check`, `make test`, explicit hooks on new files and `make ci`. Only research documents and the optional diagnostic helper are included.

## Power check and headline (#25, Jack4Codes)

_Last update: 2026-11-15 (UTC−5)_ · branch `feat/config-power-check-headline`

- Done: filled `validation/README.md` power-check and headline rows from the merged ground truth (#24) and La Mojana result (#34).
  - **Power check: uninformative.** No verified barrio damage labels (`reports/ground_truth.md`), so 0 evaluable units; positives/prevalence/k undefined. Documented null, not a failure. Applied the 02-02 fallback ("scorecard uninformative"), which unblocks C viewing.
  - **Headline: La Mojana flood** — open-water extent ~2,799–6,726 ha on 2026-06-17 *(measured, PROVISIONAL, uncalibrated)* from `reports/mojana.md`. Quake uninformative; Aburrá has no report on `main` yet.
- Decision recorded for the orchestrator to ratify at review (it sets the video story).

## Pre-registration freeze (#26, Jack4Codes)

_Last update: 2026-11-15 (UTC−5)_ · branch `feat/config-freeze-prereg`

- Done: froze `config/preregistered.yaml` — `status: frozen`, and filled `ground_truth_source` with the uninformative record (name/date/url pointing at `reports/ground_truth.md`), because the loader refuses a frozen config with null values and the ground truth is uninformative (#24/#25).
- Frozen hash recorded in `validation/README.md`: `b4f9cb89910e78fa7ad9fd53a2a4b3fca437b438` (`config.py` `preregistered_hash` and `git hash-object` agree; `require_frozen()` passes). Blob differences from `8d91f1d` listed: noise_floor (#72), pairs (#86), freeze+ground_truth (#26).
- Cross-lane (quake test, LEONOB2014): updated `tests/test_earthquake_dpm.py::test_preregistered_thresholds_load_frozen_values` from `status == "draft"` / `is_frozen False` to `frozen` / `True`, the direct consequence of the freeze. 275 offline tests pass.

## Control pairs K fix (#131, Jack4Codes)

_Last update: 2026-11-15 06:45 (UTC−5)_ · branch `fix/config-prereg-control-pairs`

- Done: replaced `control_K` on both tracks after the freeze (deviation 2 in `validation/README.md`); needs the orchestrator's ratification. Track 47: pre-event `20260617→20260629`; track 11: post-event fallback `20260825→20260906` (no independent pre-event pair on frame 086), labelled `control_K_timing: post_event`. Re-frozen hash `36a90fa104382f9217746ef730248ed24e223346`.
- Guard: `tests/test_config.py::test_control_pairs_share_no_date_with_r_or_c_and_are_labelled` fails on the old K (checked) and passes on the new one. `get_earthquake_pair_set` now reports `control_K_timing`. 302 offline tests pass.
- Handoff (LEONOB2014): `gee_math/earthquake_dpm_math.py` still reads R/C/K from `nisar_colombia_granules_2026.json` → `quake_triplets` (`TODO(#86)`), which still has the old K. The DPM control pass uses the old K until it reads `cfg.prereg("quake.pairs")` or the gate catalog is updated.
