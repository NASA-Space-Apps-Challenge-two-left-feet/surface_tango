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
- Left to #26: freeze `config/preregistered.yaml` (`status: frozen` + hash), listing the blob differences (landslide noise_floor #72, quake pairs #26). The hash/commit rows here are set at that freeze.
- Decision recorded for the orchestrator to ratify at review (it sets the video story).
