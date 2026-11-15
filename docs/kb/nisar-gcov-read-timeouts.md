---
title: NISAR GCOV reads need per-granule sessions with timeouts — one long-lived no-timeout session hung 85 min
status: unverified
source: https://earthaccess.readthedocs.io/
accessed: 2026-11-15
quote: ""
used_in: [gee_math/flood_polarimetric_math.py, "feat/data-mojana-flood 83d458c pending review"]
verified_by: pending
supersedes: null
---

From the Mojana hang diagnosis (orchestrator update 2026-11-14 21:20 Bogotá, measured): track 47 frame 5 GCOVs are ~7.1–7.3 GB each (3 of 11 measured); one long-lived earthaccess fsspec session streaming five layers (HHHH, HVHV, numberOfLooks, mask, inputDataExceptionMask) with no read timeout hung ~85 min after a transient ASF 502 (healthy ASF serves 1 MB in 2.2–3.8 s, 3 of 11 measured). Fix pattern (grok2, 83d458c, unpushed): fresh session per granule, `aiohttp.ClientTimeout(sock_connect=30, sock_read=120)` with retries and backoff, `cache_type="blockcache"` ~32 MB, strided reads at the analysis grid (90 m), a ~20 min subprocess cap so a stall cannot block the run, and hard-fail to `missing`.
