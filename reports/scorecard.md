# Issue #32 — Quake scorecard: documented uninformative result

**Result: uninformative.** No verified barrio damage-label dataset and no
accepted barrio evaluation geometry are available. Rankings, precision@k,
Wilson intervals, paired bootstrap intervals, E_C, E_K and E_C − E_K are
**not computed**. No radar advantage or damage absence is established.
Unknown, unvisited and unreported barrios remain unknown.

This completes the documented-null report permitted by plan 03-03 and its
phase goal. It does not represent an informative real-data evaluation or close
the GitHub issue. Publication branch: `codex/issue-32-uninformative`.

## Decision and evidence

The decision follows the committed upstream power check and frozen
pre-registration, not an inspection of radar values:

- `reports/ground_truth.md` (#24): source research found leads but no accepted
  barrio label dataset; boundary adoption and unit identity remain unresolved.
- `validation/README.md` (#25, #26): the official power decision is
  “scorecard uninformative”; the selected video headline is La Mojana flood.
- `config/preregistered.yaml`: frozen blob
  `36a90fa104382f9217746ef730248ed24e223346`, matching the recorded approval hash.
  Its ground-truth entry explicitly points to the uninformative research record;
  a non-null source field does not establish usable labels.

Evidence snapshot: upstream `f07a4f2`,
reviewed on 2026-11-15 (Bogotá). Commands:

```text
git show f07a4f2:validation/README.md
git show f07a4f2:reports/ground_truth.md
git show f07a4f2:config/preregistered.yaml
git rev-parse f07a4f2:config/preregistered.yaml
```

These are versioned decision documents and configuration metadata. No C/K
rasters, real unit tables, cache files or credentials were opened. No source
granule was processed for this report. The upstream decision records no
verified evaluable cohort; that is an evidence-availability finding, not a
measured count of undamaged barrios. Positive count, prevalence and k are
undefined for this report, rather than assigned zero.

## Scorecard disposition

| Output | Disposition |
|---|---|
| Informative gate | Cannot pass: no accepted labeled barrio cohort |
| Radar / population / access / control rankings | Not computed |
| Precision@k and Wilson intervals | Not computed |
| Paired barrio bootstrap and radar-minus-baseline difference | Not computed |
| E_C, E_K and E_C − E_K | Not computed; no co-event or control data accessed |
| Beats-baseline claim | Not evaluated |

The frozen informative rules remain authoritative; this report introduces no
threshold or exception. #31 implementation updates are merged upstream, while
its issue remains open. Additional DPM processing cannot supply the missing
independent ground truth and is unnecessary for this documented-null outcome.

Both deviations in `validation/README.md` accompany this result. An earlier
producer session viewed C/K summary statistics before freeze (deviation 1).
The frozen control pairs were later corrected because they shared an acquisition
with R (deviation 2); the recorded re-frozen blob above is the current approval.
The track-11 control is post-event and cannot support an unconditional
beats-baseline claim; the track-47 control is pre-event. Old-control statistics
are discarded by the upstream decision. The configured temporal-baseline
mismatch remains disclosed. No paired comparison, control interpretation or
reproduction of any producer statistic is attempted here.

## Scope and future evaluation

This documentation branch starts from the latest fetched trunk. Earlier
uncommitted integration code, fixtures and formatting changes are preserved in
their original worktree and are not included in this publication. This report
does not certify that older integration against the updated producer contract.
No scientific configuration, data loader or scoring behavior changes here.

An informative evaluation would require accepted labels and assessment coverage,
accepted barrio geometry and stable IDs, sourced covariates, aligned producer
outputs and independently valid C/K masks, plus the owners' cohort/provenance
review under the frozen rules. Those are requirements for a future evaluation,
not blockers to recording the present uninformative result.

## Verification scope

Documentation consistency, source-blob identity and whitespace were checked.
Repository evidence-rule tests and the normal commit hooks are required for
this documentation-only publication. No real-data scorecard or co-event run is
part of verification. Full offline/demo acceptance is not claimed by this report.
