---
title: Verified display fields for USGS event us6000tjl2
status: verified
source: https://earthquake.usgs.gov/fdsnws/event/1/query?eventid=us6000tjl2&format=geojson
accessed: 2026-11-14
quote: 'M 7.4 - 4 km SSW of San José del Palmar, Colombia'
used_in: [validation/event_facts.json, agents/bulletin.py]
verified_by: OpenAI Codex (primary GeoJSON read)
supersedes: docs/kb/event-2026-08-10-earthquake-v2.md
---

The primary event GeoJSON was read directly. Its reviewed event properties supply
the event identifier, magnitude/type, descriptive location, and origin timestamp.
The UTC calendar date is derived deterministically from `properties.time`.
Magnitude and descriptive location are agency estimates for that event, rather
than observatory measurements. No uncertainty interval is supplied here.

Only these supported fields are promoted in validation/event_facts.json. The
previous depth is removed from displayable facts and remains null. Preferred
origin and individual product depths must not be treated as interchangeable;
the SGC summary remains inaccessible, so depth reconciliation remains pending.
No casualty total or additional event constant is inferred.

Evidence metadata and unresolved verification items use underscore-prefixed
records, which the bulletin fact extractor excludes. A null depth is also
excluded, so neither can become an unsupported numeric placeholder.
