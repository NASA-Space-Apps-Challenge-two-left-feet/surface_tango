---
title: 2026-08-10 Colombia earthquake: Mw 7.4, depth 116.13 km, near San José del Palmar (Chocó)
status: verified
source: https://earthquake.usgs.gov/fdsnws/event/1/query?eventid=us6000tjl2&format=geojson
accessed: 2026-11-15
quote: '"depth":"116.13","depth-type":"from location"'
used_in: [validation/event_facts.json, video 0-4 s]
verified_by: EstebanOchoaedos
supersedes: docs/kb/event-usgs-verified-display-fields.md (depth claim only)
---

Secondary sources so far (Wikipedia, US Embassy alerts, Time). Before any constant is shown: record the USGS event ID and the SGC bulletin and quote them. Casualty counts vary by date; do not show them without a dated primary source.

Checked on 2026-11-15: the USGS event ID, M 7.4 (mww) and location are verified in [event-2026-08-10-earthquake-v2](event-2026-08-10-earthquake-v2.md). The depth is now verified from the USGS preferred origin. The quote is verbatim from `products.origin[0].properties` of the FDSN response above. Preferred-origin evidence: `products.origin[0]` has `"source":"us"` and `"preferredWeight":158`, the highest of the three origin products (the `pt` and `at` origins have weight 6 and depth 120 km), and the event `geometry.coordinates` repeat it: [-76.2558, 4.8601, 116.13]. EstebanOchoaedos read "116.1 km" on the Origin tab of https://earthquake.usgs.gov/earthquakes/eventpage/us6000tjl2 on 2026-11-15. These are agency estimates, not BailaSAR measurements. This note supersedes only the depth claim of [event-usgs-verified-display-fields](event-usgs-verified-display-fields.md) ("depth reconciliation remains pending"); its other fields stand. 116.13 km is the verified USGS preferred-origin estimate; `validation/event_facts.json` displays it as `depth_km` 116, rounded to whole km and labelled a USGS estimate ([event-usgs-verified-display-fields-v2](event-usgs-verified-display-fields-v2.md)). The SGC manual bulletin gives 105 km ([event-2026-08-10-earthquake-sgc](event-2026-08-10-earthquake-sgc.md), read by EstebanOchoaedos on 2026-11-15); the agencies use different networks and velocity models, so their depths differ. The 96 km figure used earlier had no source: it was first added in commit 11242b8 without a citation, matches neither USGS nor SGC, and has been removed. Do not show 96 km.
