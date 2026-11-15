# Pre-registration (BailaSAR)

Commit this file, filled in, **before** anyone views co-event (C-pair) coherence (design doc, Hazard 2).

| Field | Value |
|---|---|
| `config/preregistered.yaml` hash (`git hash-object`) | `b4f9cb89910e78fa7ad9fd53a2a4b3fca437b438` *(frozen, #26)* — `config.py` `preregistered_hash` and `git hash-object` agree. |
| Commit of this file | Frozen 2026-11-15 (#26 freeze PR; squash commit on `main`). `config/preregistered.yaml` `status: frozen`; never edited after. |
| Ground-truth source (name, date, URL) | **Uninformative.** No complete barrio-level damage-assessment dataset was verified for Pereira, Armenia or Manizales. Public damage reports and boundary candidates were located but none adopted as labels. Source register: `reports/ground_truth.md` (#24, inspected 2026-11-14). |
| Barrio polygons source | Candidates located (official/IGAC boundaries, `reports/ground_truth_armenia_boundaries.md`); **none adopted** — official adoption, event-date validity and unit identity unresolved (#24). |
| Expected evaluable units / positives / prevalence / k (power check, D11) | **Not computable — scorecard uninformative.** 0 verified evaluable units and 0 damage labels, so positives, prevalence and k are undefined. No damage labels, prevalence, evaluated-unit count, precision or ranking were produced (`reports/ground_truth.md`). Unreported/unvisited barrios remain **unknown**, not undamaged. |
| Video headline chosen at hour 4 | **La Mojana flood** — open-water extent *(measured, PROVISIONAL, uncalibrated)*: ~2,799–6,726 ha on 2026-06-17 across the thresholded range (`reports/mojana.md`, #34). The quake scorecard is uninformative (above), so the quake does not headline. |
| R / C / K GUNW IDs | Filled in `config/preregistered.yaml` `quake.pairs` (tracks 11 and 47) in #26 (PR #86); the exact IDs are recorded with the frozen blob at freeze (#26). |

Fallback applied: the ground truth / polygons were not usable, so this records **"scorecard uninformative"** per plan 02-02, which unblocks C viewing. The quake scorecard (#32) is not produced from these labels.

## Power check and headline (plan 02-03, #25)

**Power check.** With no verified barrio damage labels (`reports/ground_truth.md`, #24), there are 0 evaluable units, so the quake precision@k scorecard cannot be made informative under the frozen rules (`config/preregistered.yaml` `quake.informative`: min_units 30, min_positives 5). This is a documented null, not a failure: the data inspected so far does not establish damage labels, and it does not establish that none exist.

**Headline decision → La Mojana flood.** The only hazard with a measured, headline-ready result is the La Mojana flood:

- Open-water extent *(measured)*: sensitivity range **2,799–6,726 ha** on 2026-06-17 (pixel counts 3,455–8,304; one of 10 usable dates, track 47 frame 5), `reports/mojana.md` → "Sensitivity", from `uv run python -m gee_math.flood_polarimetric_math` over AOI `3_la_mojana_caregato`, 74 granules *(measured)*.
- Honesty caveats carried into the video: products are **PROVISIONAL** (`PR` stream), thresholds are **uncalibrated** (read from config, not fitted), this is **absolute open-water** not change-detection, and the Class 1/2 change method is **degenerate** (reference date has 1 valid pixel), so it reports 0 ha.
- Aburrá (landslide) has no report on `main` yet; the quake is uninformative. So the headline is the flood.

This decision is recorded here for the orchestrator to ratify at review (it sets the video's story).

## Differences from blob `8d91f1d`

Every change to `config/preregistered.yaml` after blob `8d91f1df0d53c394f22e65a7b114579f8fc9f0e7` (deviation 1), with its reason.

| Change | Reason |
|---|---|
| Added `landslide.noise_floor: {min_pairs: 2, require_sign_agreement: true}` | The landslide honesty test (design doc, Hazard 1) needs these keys for `noise_floor_verdict` (#72). Both values are the design doc's rule ("the sign agrees across two independent pairs"). Landslide only: no quake or flood parameter changes, and none depends on C-pair coherence. |
| Filled `quake.pairs` (tracks 11 and 47) with the R/C/K GUNW IDs | The IDs come straight from the hour-2 gate (`nisar_colombia_granules_2026.json` → `quake_triplets`, #23); no threshold, weight, k-rule or informative-gate value changed (#86). Blob after this change: `56b29a0`. The pairs are identifiers, not fitted parameters; the DPM run (#111) selected the same track-11 triplet before this file recorded it. |
| Set `status: frozen` and filled `ground_truth_source` (name/date/url) with the uninformative record | The freeze (#26). `ground_truth_source` is non-null because the loader refuses a frozen config with nulls; the honest value is "none verified — scorecard uninformative" (#24/#25), pointing at `reports/ground_truth.md`, not a damage dataset. No threshold, weight, k-rule, informative-gate or pair value changed. Final frozen blob (`git hash-object` = `config.py` `preregistered_hash`): `b4f9cb89910e78fa7ad9fd53a2a4b3fca437b438`. |

## Deviations

| # | When (Bogotá) | What happened | Who saw it | Pre-registration state at the time | Consequence |
|---|---|---|---|---|---|
| 1 | 2026-11-14, about 19:45 | The quake DPM executor (opencode, branch `feat/data-quake-dpm`, #31) printed summary statistics of the **C pass** (co-event coherence loss: non-built μ/σ, median Z by class, excess E) and of the K control pass in its run log and draft report, before this file was filled in. The brief asked for them to be stored only. | The executor agent and the orchestrator session (LEONOB2014's lead). Not shared with the team: removed from the report before the branch was pushed, and kept only in the git-ignored `local_cache/quake/`. | `config/preregistered.yaml` blob `8d91f1df0d53c394f22e65a7b114579f8fc9f0e7` (`git hash-object`), status `draft`, unchanged since `b4c797e` (#14). | The freeze (#26) must keep every parameter in that blob unchanged; the frozen hash recorded above should equal `8d91f1d…`, or each difference must be listed here with its reason. The C-pass numbers stay withheld from reports, the UI and the team until the freeze. The scorecard (#32) reports this deviation next to its result. |

**Ratified** by @LEONOB2014 (orchestrator review, 2026-11-15): the video headline is La Mojana flood. Supporting L-vs-C comparison *(measured, `reports/mojana.md`)*: on 2026-07-11, Sentinel-1 (14 IW GRD scenes within ±6 days) missed 3,351 of the 4,946 NISAR open-water pixels.
