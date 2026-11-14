# Allow-list: the only places resampling or hand-written arrays may appear

| Path | What | Why it is not synthetic data |
|---|---|---|
| `validation/scoring.py` (bootstrap functions) | seeded barrio-block resampling | statistical CI on measured data, seed in `config/preregistered.yaml` |
| `tests/test_*.py` | small hand-written arrays with hand-computed expected values | known-answer logic tests (D15); never reach the app, cache or video |
| `tests/test_cache_release.py` | tiny hand-written byte strings and known-answer manifest verifier cases | isolated temporary-directory tests only; never reach the app or distributed cache |
