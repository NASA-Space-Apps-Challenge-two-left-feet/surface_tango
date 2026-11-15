---
title: ASF auth — asf_search search is anonymous, Earthdata tokens work as Bearer headers, earthaccess 0.19 login offers no token strategy
status: verified
source: https://earthaccess.readthedocs.io/api/auth/
accessed: 2026-11-15
quote: "login(strategy: str = 'all', persist: bool = False, system: ...) -> earthaccess.auth.Auth"
used_in: [mcp_servers/nisar_asf_mcp.py, scripts/build_cache.py, "#28"]
verified_by: opencode-acting-orchestrator (measured)
supersedes: null
---

The quote is the installed signature (earthaccess 0.19.0, `inspect.signature`, 2026-11-15): netrc/environment/all strategies only, no token parameter. `asf_search` granule search needs no credentials (same pattern as the hour-2 gate script). Streaming NISAR HDF5 from ASF works with `Authorization: Bearer <EARTHDATA_TOKEN>` (fsspec; the whole 3-AOI cache was built this way 2026-11-14 21:18–21:22, measured). `earthaccess.login(strategy="netrc")` at module level crashes import wherever `~/.netrc` lacks a machine entry (`LoginStrategyUnavailable`, measured on the team Mac, 2026-11-15); removed from the server in #79. Preference order: anonymous search → token Bearer → netrc/environment password as a last resort; never plaintext netrc copies per machine.
