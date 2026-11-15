---
title: pyarrow.parquet keeps NaN as a value (not null) in round-trip, and nullable=False fields write REQUIRED columns
status: verified
source: measured in the repo venv (pyarrow 26.0.1, uv.lock); re-run the command below
accessed: 2026-11-15
quote: ""
used_in: [gee_math/earthquake_dpm_math.py write_parquet/read_parquet, tests/test_earthquake_dpm.py round-trip test, validation/scoring.py consumers]
verified_by: opencode GLM-5.3 (agent, feat/quake-dpm-v2)
supersedes: null
---

Measured in this repository's venv (pyarrow pinned by `uv.lock`): building
`pa.array([...  float('nan')], type=pa.float64())` inside fields declared
`pa.field(..., nullable=False)`, writing with `pq.write_table` and reading
with `pq.read_table` returns `float('nan')` — the NaN survives as a value and
never becomes `None`/null; metadata shows every column REQUIRED (nullable
False) and the file keeps the `PAR1` magic. Command:

    uv run python -c "
    import pyarrow as pa, pyarrow.parquet as pq, math
    t = pa.Table.from_arrays(
        [pa.array([1.25, float('nan')], type=pa.float64())],
        schema=pa.schema([pa.field('v', pa.float64(), nullable=False)]),
    )
    pq.write_table(t, '/tmp/t.parquet')
    back = pq.read_table('/tmp/t.parquet')
    print(math.isnan(back.column('v').to_pylist()[1]),
          pq.ParquetFile('/tmp/t.parquet').schema_arrow.field('v').nullable)
    "

printed `True False` on 2026-11-15. This is why the quake unit parquet can
carry NaN medians for excluded units (missing stays missing, never zero or
null). Limits: behavior of the pinned version only; a major pyarrow bump
should re-run the command.
