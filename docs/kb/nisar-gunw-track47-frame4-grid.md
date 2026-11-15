---
title: Track 47 GUNW frame 4 has the same 20 m coherence grid layout as track 11 frame 86 (EPSG:32618, 20 m posting, identical AOI window)
status: verified
source: measured on the public NISAR GUNW granules in reports/quake_dpm.md (2026-11-14/15 runs)
accessed: 2026-11-15
quote: ""
used_in: [gee_math/earthquake_dpm_math.py load_gunw_window (UTM 18N guard), reports/quake_dpm.md]
verified_by: opencode GLM-5.3 (agent, feat/quake-dpm-v2)
supersedes: null
---

Measured while streaming tracks 11 and 47 for the quake DPM (#31): the
ascending frame-4 GUNW products (`NISAR_L2_PR_GUNW_025/026/024_047_A_004_*`,
CRID P05023, provisional) carry their 20 m coherenceMagnitude in
`wrappedInterferogram/HH` under `frequencyA`, on an EPSG:32618 grid with 20 m
posting, exactly like the descending frame-86 track-11 products. Clipping to
the same AOI bbox [-75.85, 4.40, -75.40, 5.15] produced the identical window
4143×2499 px on both tracks (measured both runs; 0 coherence values outside
[0,1] on all six granules). Limits: provisional products, both frames inside
UTM zone 18N; other zones or validated products should re-check the grid
before relying on the 18N assumption.
