---
title: Esri World Imagery is visor context, not a measurement
status: verified
source: https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer?f=pjson
accessed: 2026-11-15
quote: "World Imagery provides one meter or better satellite and aerial imagery in many parts of the world and lower resolution satellite imagery worldwide."
used_in: static/context-basemap.js, static/index.html
verified_by: curl of the MapServer JSON and tile/12/1976/1188
supersedes: null
---

The curtain requests this public tile service in `{z}/{y}/{x}` order
and keep a dark background layer beneath it. The service copyright line is
"Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community."
A failed request leaves the dark field. It does not fill an unobserved pixel
inside an area of interest, and it is not a Surface Tango measurement.
