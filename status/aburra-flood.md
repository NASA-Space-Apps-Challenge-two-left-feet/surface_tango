# Status: aburra-flood

_Last update: 2026-11-14 (UTC−5)_

- Doing: 01-04 on `feat/flood-config-logic-tests` (local commits only, not pushed).
- Done:
  - Flood: thresholds read from the `flood:` section of `config/preregistered.yaml`; pure NumPy rules
    (`open_water_fraction`, `pick_reference_date`, `classify`) with the no-baseline rule; EE pipeline
    rewritten on the same params; Sentinel-1 VV moved to a comparison band; output labelled
    uncalibrated. `tests/test_flood.py`.
  - Landslide: `noise_floor_verdict`, signed downslope projection (no `abs()`), HKLSI labelled
    uncalibrated, displacement skipped (missing) when the ionosphere layer is missing; every function
    takes `params`. `tests/test_landslide.py`.
- Blocked (dependencies, not stopping work):
  - Landslide keys (`LANDSLIDE_PARAM_KEYS` in `gee_math/landslide_insar_math.py`) are not in
    `config/preregistered.yaml` yet; they need adding by Jack4Codes (config lane) before freeze.
    Until then the landslide pipeline has no default params.
  - `load_params` in the flood module is a local stand-in for the shared loader (01-02,
    `src/bailasar/config.py`).
  - `mcp_servers/gee_fusion_mcp.py` (alicealanapineda-byte) still calls the old signatures
    (flood: pre images + S1 dates with defaults; landslide: no `params`) and reads the removed
    `double_bounce_fraction` band; it needs updating in the MCP lane (01-05).
