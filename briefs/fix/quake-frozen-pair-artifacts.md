# Brief: fix/quake-frozen-pair-artifacts — rebuild the control pass from the frozen pairs (#141)

- **Goal:** make `gee_math/earthquake_dpm_math.py` read R/C/K and `control_K_timing` from `config/preregistered.yaml` (`quake.pairs`, per track), fail loudly if a frozen ID is absent from the gate catalog, carry `control_K_timing` into the DPM output, and re-serialize the quake evidence artifacts with the frozen-K statistics.
- **Issue:** #141. **Owner account:** alicealanapineda-byte (agents/executor pool: opencode Kimi K3).
- **Files you may touch:** `gee_math/earthquake_dpm_math.py`, `scripts/write_hazard_evidence.py`, `tests/test_earthquake_dpm.py`. Do not touch `config/` or the prereg hash.
- **Steps:**
  1. `resolve_pairs()` reads the frozen pairs per track (bailasar config loader); keep the gate catalog as evidence only — fail if a frozen ID is not in the catalog.
  2. Carry `control_K_timing` into the DPM output and the bulletin wording ("radar vs baseline, post-event control only" for track 11).
  3. Re-run the control pass for both tracks and re-serialize `local_cache/eje_cafetero/quake_evidence_track{11,47}.json` (needs Earthdata streaming — coordinate with LEONOB2014 for credentials runs).
  4. Add a test that the DPM pair IDs equal the frozen `quake.pairs` IDs for both tracks.
- **Acceptance:** `make ci` green; the evidence artifacts' `pairs.K.granule_id` matches the frozen `control_K`; `analyze_earthquake_dpm` serves frozen-K statistics.
- **Outward actions needing approval:** none (pipeline runs are local/network reads only).
- **If blocked:** write `BLOCKED: <reason>` in `status/quake.md` and stop.

## If blocked
No Earthdata credentials → implement + test the code changes, mark the re-serialization as blocked on the owner run.
