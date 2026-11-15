---
title: The quake control pair K must share no acquisition date with R or C; track 11 uses a post-event K fallback, so it is "post-event control only"
status: verified
source: docs/designs/bailasar.md
accessed: 2026-11-15
quote: "K shares no date with R or C"
used_in: [config/preregistered.yaml, gee_math/earthquake_dpm_math.py, validation/README.md, "#134", "#141"]
verified_by: LEONOB2014
supersedes: null
---

The design's control pass K must be an independent pair that shares no acquisition
date with the reference R or co-event C. The #86 K pairs ended on R's first
acquisition (track 11: 2026-07-08; track 47: 2026-07-11), breaking this rule;
#134 (deviation 2) re-chose them from the gate catalog and the date rule only:
- **Track 47:** the independent 12-day pre-event pair on the same track/frame
  (`…023_047_A_004_024…20260617…20260629…`).
- **Track 11:** frame 086 has no other pre-event pair in the gate, so the design's
  **post-event fallback** is used (`…029_011_D_086_030…20260825…20260906…`),
  recorded as `control_K_timing: post_event`.

Consequence: track 11 is reported as **"radar vs baseline, post-event control
only"** — condition 3 of the beats rule cannot be met and residual demolition,
debris and aftershock change are expected, so it never states "radar beats
baseline". The pre-registration is frozen (hash `36a90fa…`); K was recorded in
`quake.pairs`. **Open (#141):** the DPM pipeline still reads K from the gate
catalog, not the frozen `quake.pairs` — the interpretation must use the frozen K.
