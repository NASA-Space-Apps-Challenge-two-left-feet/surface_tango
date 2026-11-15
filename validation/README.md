# Pre-registration (BailaSAR)

Commit this file, filled in, **before** anyone views co-event (C-pair) coherence (design doc, Hazard 2).

| Field | Value |
|---|---|
| `config/preregistered.yaml` hash (`git hash-object`) | _pending_ |
| Commit of this file | _pending_ |
| Ground-truth source (name, date, URL) | _pending (hour-4 timebox, D10)_ |
| Barrio polygons source | _pending_ |
| Expected evaluable units / positives / prevalence / k (power check, D11) | _pending_ |
| Video headline chosen at hour 4 | _pending_ |
| R / C / K GUNW IDs | _pending (hour-2 gate)_ |

If the ground truth or polygons are missing at hour 4: write "scorecard uninformative" here and unblock C viewing.

## Deviations

| # | When (Bogotá) | What happened | Who saw it | Pre-registration state at the time | Consequence |
|---|---|---|---|---|---|
| 1 | 2026-11-14, about 19:45 | The quake DPM executor (opencode, branch `feat/data-quake-dpm`, #31) printed summary statistics of the **C pass** (co-event coherence loss: non-built μ/σ, median Z by class, excess E) and of the K control pass in its run log and draft report, before this file was filled in. The brief asked for them to be stored only. | The executor agent and the orchestrator session (LEONOB2014's lead). Not shared with the team: removed from the report before the branch was pushed, and kept only in the git-ignored `local_cache/quake/`. | `config/preregistered.yaml` blob `8d91f1df0d53c394f22e65a7b114579f8fc9f0e7` (`git hash-object`), status `draft`, unchanged since `b4c797e` (#14). | The freeze (#26) must keep every parameter in that blob unchanged; the frozen hash recorded above should equal `8d91f1d…`, or each difference must be listed here with its reason. The C-pass numbers stay withheld from reports, the UI and the team until the freeze. The scorecard (#32) reports this deviation next to its result. |
