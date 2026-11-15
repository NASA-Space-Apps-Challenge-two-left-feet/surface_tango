---
title: In asf_search 14.1.0 a NISAR result's `bytes` property is a dict per file, not one integer
status: unverified
source: https://github.com/asfadmin/Discovery-asf_search
accessed: 2026-11-14
quote: null
used_in: [scripts/discover_nisar_colombia.py]
verified_by: null
supersedes: null
---

Measured on 2026-11-14 with asf_search 14.1.0: summing `properties["bytes"]` failed because the value is a mapping per file. The gate script no longer reads it; file sizes come from an HTTP open (`fs.open(url).size`, e.g. 7.1–7.3 GB per La Mojana GCOV, docs/kb/nisar-gcov-read-timeouts.md). To verify: cite the asf_search changelog entry that changed the field.
