---
title: NISAR L2 file names encode stream, product, track, direction, frame, polarization (+ an optional mode letter), the acquisition times and the CRID
status: unverified
source: https://nisar-docs.asf.alaska.edu/
accessed: 2026-11-14
quote: "NISAR_L2_PR_GCOV_023_047_A_005_4005_DHDH_A_20260617T103906_20260617T103941_P05023_F_F_J_001"
used_in: [scripts/discover_nisar_colombia.py (NAME_RE), nisar_colombia_granules_2026.json, gee_math/flood_polarimetric_math.py]
verified_by: null
supersedes: null
---

The quote is a real granule name returned by ASF search on 2026-11-14 (measured). Observed fields: `L2`, stream `PR` (provisional; `UR` = urgent response), product (`GCOV`/`GUNW`/`GOFF`), cycle, track (`047`), direction (`A`/`D`), frame (`005`), mode, polarization (`SH` single-pol HH for GUNW; `DHDH` dual-pol or `SHSH` for GCOV) optionally followed by a one-letter mode (`_A_`, `_M_`), start/stop times (GUNW has two pairs), CRID (`P05023`, `P05036`). A regex without the optional mode letter silently missed the DHDH GCOVs. To verify: quote the ASF/JPL product naming spec.
