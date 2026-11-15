---
title: CHIRPS Daily publication lag — late-2026 windows return 0 images; record the rain band missing
status: unverified
source: https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY
accessed: 2026-11-15
quote: ""
used_in: [scripts/build_cache.py, "README missing states"]
verified_by: pending
supersedes: null
---

Measured evidence: the 2026-10-29..2026-11-13 window returned 0 images in all three AOI cache builds (2026-11-14 21:18–21:22 Bogotá; `rain_15d_mm` = `missing`, 0/262144 finite in every `local_cache/<aoi>/manifest.json`). The multi-week publication-lag claim still needs a primary-source read (CHC/CHIRPS docs) before this note becomes `verified`. Never substitute a synthetic rain field; the cache window comes only from `--chirps-start`/`--chirps-end` (PR #78).

Checked https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY on 2026-11-15: states dataset availability ending before the measured cache window, but does not state a multi-week publication lag or verify the local cache results. Page fetched successfully through the web tool; HTTP status was not exposed.

Checked https://chc.ucsb.edu/data/chirps on 2026-11-15: does not state a multi-week publication lag; its linked daily README and FAQ were also requested. Page fetched successfully through the web tool; HTTP status was not exposed.

Checked https://data.chc.ucsb.edu/products/CHIRPS-2.0/README-CHIRPS2-Daily.txt on 2026-11-15: unreachable (HTTP 404).

Checked https://wiki.chc.ucsb.edu/CHIRPS_FAQ on 2026-11-15: unreachable (web tool reported HTTP 400, Timeout fetching).
