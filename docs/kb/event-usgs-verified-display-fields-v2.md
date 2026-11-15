---
title: Verified display fields for USGS event us6000tjl2, now including depth (116 km, USGS estimate)
status: verified
source: https://earthquake.usgs.gov/fdsnws/event/1/query?eventid=us6000tjl2&format=geojson
accessed: 2026-11-15
quote: '"depth":"116.13","depth-type":"from location"'
used_in: [validation/event_facts.json, agents/bulletin.py, tests/test_event_facts.py]
verified_by: EstebanOchoaedos
supersedes: docs/kb/event-usgs-verified-display-fields.md
---

Displayable fields of `validation/event_facts.json` for the 2026-08-10 quake: date, magnitude (7.4 mww), magnitude type, epicenter
and, new here, `depth_km` = 116. The date, magnitude and location evidence is unchanged from
[event-usgs-verified-display-fields](event-usgs-verified-display-fields.md).
The depth is the USGS preferred-origin estimate, 116.13 km (`products.origin[0]`, source `us`, `preferredWeight` 158; see
[event-2026-08-10-earthquake](event-2026-08-10-earthquake.md)), rounded half-up to whole km. It is an agency estimate,
not a BailaSAR measurement, and is labelled "USGS estimate" with the event as denominator. It is never taken from another
USGS product or from the SGC bulletin (105 km, [event-2026-08-10-earthquake-sgc](event-2026-08-10-earthquake-sgc.md)),
which stays evidence only. A bulletin placeholder for it must declare unit km, 0 decimal places and evidence "estimate".
