---
title: 2026-08-10 Colombia earthquake: Mw 7.4, depth 116.13 km, near San José del Palmar (Chocó)
status: verified
source: https://earthquake.usgs.gov/fdsnws/event/1/query?eventid=us6000tjl2&format=geojson
accessed: 2026-11-15
quote: 'products.origin[0].properties.depth = "116.13"'
used_in: [validation/event_facts.json, video 0-4 s]
verified_by: EstebanOchoaedos
supersedes: null
---

Secondary sources so far (Wikipedia, US Embassy alerts, Time). Before any constant is shown: record the USGS event ID and the SGC bulletin and quote them. Casualty counts vary by date; do not show them without a dated primary source.

Checked on 2026-11-15: the USGS event ID, M 7.4 (mww) and location are verified in [event-2026-08-10-earthquake-v2](event-2026-08-10-earthquake-v2.md). The depth is now verified from the USGS preferred origin: 116.13 km in `products.origin[0]` (source us) of the FDSN response above, matching `geometry.coordinates` [-76.2558, 4.8601, 116.13]; the event page Origin tab shows 116.1 km (read by EstebanOchoaedos on 2026-11-15). These are agency estimates, not BailaSAR measurements. The earlier 96 km figure does not appear in any USGS product; it likely came from SGC via a secondary source and stays unverified (the SGC bulletin returned HTTP 403 on 2026-11-14). Do not show 96 km.
