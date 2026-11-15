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

Checked https://github.com/asfadmin/Discovery-asf_search on 2026-11-15: does not state the version-specific bytes mapping in the repository overview. Page fetched successfully through the web tool; HTTP status was not exposed.

Checked https://github.com/asfadmin/Discovery-asf_search/blob/master/CHANGELOG.md on 2026-11-15: the v14.1.0 entry describes a session keyword argument, not a bytes-field change. Page fetched successfully through the web tool; HTTP status was not exposed.

Checked https://github.com/asfadmin/Discovery-asf_search/blob/master/asf_search/Products/NISARProduct.py on 2026-11-15: states the current implementation assigns `self.properties['bytes']` a dictionary keyed by `entry['Name']`, containing bytes and format per file; does not establish that this fetched master file is the v14.1.0 implementation. Page fetched successfully through the web tool; HTTP status was not exposed.

Checked https://github.com/asfadmin/Discovery-asf_search/blob/v14.1.0/asf_search/Products/NISARProduct.py on 2026-11-15: unreachable (web tool reported Cache miss; no HTTP status exposed).

Checked https://raw.githubusercontent.com/asfadmin/Discovery-asf_search/v14.1.0/asf_search/Products/NISARProduct.py on 2026-11-15: unreachable (web tool reported Cache miss; no HTTP status exposed).

Checked https://github.com/asfadmin/Discovery-asf_search/compare/v14.0.4...v14.1.0 on 2026-11-15: unreachable (web tool reported Cache miss; no HTTP status exposed).
