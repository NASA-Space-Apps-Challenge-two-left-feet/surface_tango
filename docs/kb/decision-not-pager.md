---
title: USGS PAGER colors are fatality and loss alerts, which this product does not emit
status: unverified
source: https://earthquake.usgs.gov/data/pager/background.php
accessed: 2026-11-15
quote: "The estimated losses trigger the appropriate color-coded alert, which determines the suggested levels of response."
used_in: [config/bailasar.yaml, mcp_servers/decision.py, static/decision.js]
verified_by: pending
supersedes: null
---

USGS PAGER estimates fatalities and economic losses and paints green, yellow, orange, or red from those ranges. Surface Tango has no population-exposure or loss model on the evidence envelopes, so the posture card uses different evidence-state names and does not copy the PAGER scale or its thresholds. A teammate still needs to confirm the quote against the page.
