---
title: Earth Engine must be initialised with the gcloud ADC identity and an explicit project; the earthengine CLI's saved login can be a different account
status: unverified
source: https://google-auth.readthedocs.io/en/latest/reference/google.auth.html#google.auth.default
accessed: 2026-11-14
quote: "This function acquires credentials from the environment in the following order"
used_in: [gee_math/ee_session.py, mcp_servers/gee_fusion_mcp.py, app.py, scripts/prestage_tiles.py, scripts/build_cache.py, AGENTS.md "Language"]
verified_by: null
supersedes: null
---

Measured on 2026-11-14: `ee.Initialize()` with no arguments picked the credentials saved by `earthengine authenticate`, which belonged to a different Google account, and the project's Earth Engine calls failed. Passing `google.auth.default(scopes=EE_SCOPES)` credentials plus `project=GCP_PROJECT_ID` fixed it (#52); every module now goes through `gee_math/ee_session.init_ee()`. To verify: cite the Earth Engine Python initialization guide for the order of credential lookup.
