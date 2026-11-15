---
title: The Aburrá landslide null is confirmed by two independent calibrations — a sign-flip null and the stable-pixel false-positive rate
status: verified
source: reports/aburra.md
accessed: 2026-11-15
quote: "No motion detected above 9.105 mm (17 pairs)"
used_in: [gee_math/landslide_insar_math.py, reports/aburra.md, "#109", "#144"]
verified_by: LEONOB2014
supersedes: null
---

The keep-rule (keep a pixel where |LOS| exceeds the per-pair residual RMS and the
downslope sign agrees across two date-independent pairs) passes noise: with 8–9
pairs it keeps ~25% of hillslope pixels, signs near 50/50. The verdict **"no
motion detected above 9.105 mm (17 pairs)"** is confirmed two ways *(measured,
PROVISIONAL)*:
1. **Sign-flip null (#109):** re-run the rule with each pair's sign randomly
   flipped (200 draws, seed 20261115). The hillslope kept fraction is **below**
   the null mean on both tracks (track 11: 0.3748 vs 0.4131; track 47: 0.4073 vs
   0.4857).
2. **Stable-pixel false-positive rate (#144):** apply the same rule to the
   known-stable valley-floor pixels. The hillslope kept fraction sits **above**
   that rate and **below** the sign-flip p95 (track 47: hillslope 0.4073, stable
   0.3600 of 24,155, null p95 0.5390), so the excess over noise is not a
   candidate. A null is a valid headline.
