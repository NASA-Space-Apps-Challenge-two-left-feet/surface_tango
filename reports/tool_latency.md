# Tool latency — issue #28

**Status: owner-run handoff; live measurements have not been collected.**

The user chose preparation for a cloud owner. No cloud request, storage upload,
GEE computation or paid model call was made, and `breaker_budgets_s` is unchanged.
This report is not a completed latency benchmark and contains no proposed budgets.

## Offline evidence

Command: `uv run python -m mcp_servers.tool_latency --plan reports/tool_latency_plan.json`

Machine output: `reports/tool_latency.json`. It records the command, catalog
references, planned input IDs and readiness blockers without copying
raw URLs or credentials. Preflight imports no live server and opens no raster.
Exit status `2` means the run is incomplete; it does not stand for measured latency.

| Tool | Current readiness | Measured p95 / budget |
|---|---|---|
| `search_nisar_granules` | Metadata workload resolves from the operational AOI and committed catalog window; owner execution still required | Not measured |
| `stage_nisar_gcov_to_gcs` | Real GCOV metadata is referenced; explicit authorized bucket and staging-write authorization required | Not measured |
| `stage_nisar_gunw_ionosphere_corrected_to_gcs` | Real GUNW metadata is referenced; bucket, staging-write authorization and committed freeze required | Not measured |
| `analyze_landslide_kinematics` | GEE bootstrap, real staged arguments/IDs and committed freeze missing | Not measured |
| `analyze_flood_inundation` | GEE bootstrap, real staged arguments/IDs and committed freeze missing | Not measured |
| `analyze_earthquake_dpm` | GEE bootstrap, real staged arguments/IDs and committed freeze missing | Not measured |

Metadata source: `nisar_colombia_granules_2026.json`, produced by
`uv run python scripts/discover_nisar_colombia.py` (see `reports/gate.md`).
The plan selects a fixed earliest listed provisional Aburrá GCOV dual-pol scene
and a fixed earliest listed provisional Aburrá GUNW scene. These are reproducible
metadata workloads, not a claim that the internal product layers were verified.
The exact source IDs are in the plan/machine report; no source IDs or GCS artifact
paths were invented. The AOI bbox is resolved from config, not duplicated.

## Cloud-owner procedure

Allowed roles come from AGENTS.md: LEONOB2014, Jack4Codes and EstebanOchoaedos.
Use a normal configured worktree and the owner's existing credentials. Credentials
belong in the ignored environment/normal credential store, never in a plan/report.

- Copy the plan to an ignored local-cache plan and fill the real staged artifacts
  and source IDs that are missing. All benchmark arguments must be explicit;
  stale function defaults for dates/baselines/polarization are not accepted.
- Repair/merge the real server bootstrap and science prerequisites through their
  owners. The current trunk GEE file has decorators without an initialized MCP
  server. Do not measure a stub or successful-looking placeholder result.
- Commit the real preregistration record and frozen config before any coherence
  staging/analysis. Preflight checks both the frozen state and the recorded hash,
  and refuses uncommitted changes to those records.
- Confirm the staging tool's actual bucket configuration. Its current source reads
  `GCS_NISAR_BUCKET`; the runner refuses to use a fallback bucket. The owner must
  explicitly select the correct permitted bucket in the environment.
- Run the command below with an owner-selected watchdog duration for the entire
  tool worker, including startup. The placeholder is intentionally not a guessed
  runtime or a proposed circuit-breaker budget.

```text
uv run --env-file .env python -m mcp_servers.tool_latency --plan local_cache/tool_latency_plan.json --execute --owner Jack4Codes --watchdog-s <owner-selected-seconds>
```

Use the actual allowed owner name. Storage-writing requests additionally require
`--allow-staging-writes`; add it only when that concrete upload plan is authorized.
The runner forces live mode in its worker and unwraps the cache decorator, so a
circuit-breaker timeout cannot truncate the values being used to estimate it.
Module startup/authentication and SSE transport overhead are outside the timed
function region. Library retries inside the function remain part of its latency.

The D6 procedure requires **10 successful sequential calls per tool** (planned
sample denominator from the approved issue). No warm-up is discarded, and an
error/cached/gate/unavailable result aborts that tool without a budget. The raw
successful durations are *(measured)*, with command and source IDs. Empirical
p95 and **p95 + 0.5 seconds** are *(estimates)* for that exact workload, not an SLA.
The report includes the measured sample range; it is not a confidence interval.
No confidence interval is asserted from this small measurement set.

After reviewing a successful live run, the owner may add `--apply-budgets` to
record proposals for fully measured tools only. The runner recomputes each
proposal from its complete sample set and changes only the breaker-budget block.
Defaults, failed/incomplete tools and all unrelated operational settings remain
unchanged. A partial run still exits incomplete even if valid tool proposals were
explicitly applied. Review the resulting config diff before any commit/push.

New scoring/pair tools introduced by #35 need their own real workload entries once
registered and usable. Biomass remains excluded per the decided architecture.
No work on #35/#36 was performed as part of this #28 handoff.
