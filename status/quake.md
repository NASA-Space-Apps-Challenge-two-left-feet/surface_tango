# Status: quake

_Last update: 2026-11-14 (UTC−5)_

- Doing: 01-02 config loader (#17), branch `feat/quake-config-loader-for-prereg`
- Done:
  - `src/bailasar/config.py`: one loader for `config/preregistered.yaml` + `config/bailasar.yaml`; no defaults (missing key, null value or AOI without a gate bbox raises `ConfigError`); read-only views; `git hash-object`-compatible hash; `require_frozen(expected_hash)` for CFG-02 (#26)
  - `tests/test_config.py`: 27 offline tests, including a guard that fails on any new hardcoded flood threshold or AOI coordinate in `scripts/`, `gee_math/`, `mcp_servers/`, `agents/`, `src/`, `app.py`
- Blocked: none (`.secrets.baseline` landed on main; branch synced to `origin/main` 7ce0917)
- Handoffs (files owned by other plans still carry config literals; listed in `PENDING_WIRING` in `tests/test_config.py`, remove the entry once wired):
  - `gee_math/flood_polarimetric_math.py` lines 50, 67, 76 (HAND 18 m, −5.5 dB, +3.0 dB) → 01-04
- Needs the 01-01 owner (`pyproject.toml`): `src/` is not on the import path yet (pytest `pythonpath` is `["."]`). `tests/test_config.py` adds it itself; other modules need either `[tool.pytest.ini_options] pythonpath = ["src", "."]` plus a build backend so `uv sync` installs `bailasar`, or the same path insert.
