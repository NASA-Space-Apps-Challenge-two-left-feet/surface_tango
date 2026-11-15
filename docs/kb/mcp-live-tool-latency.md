---
title: Live tool budgets require a complete uncensored owner-run sample set
status: verified
source: https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango/blob/main/docs/designs/bailasar.md
accessed: 2026-11-14
quote: 'Agents route, tools compute.'
used_in: [mcp_servers/tool_latency.py, reports/tool_latency.md, reports/tool_latency_plan.json]
verified_by: OpenAI Codex
supersedes: null
---

This describes the runner contract, not measured tool performance. The D6 budget
procedure is implemented with sequential valid live function calls, application
cache wrappers unwrapped, explicit provenance, and an owner-selected worker
watchdog. A cached, errored, missing or gate result cannot produce a live budget.
Incomplete tool runs leave their budget absent; dry-run preflight changes none.

Inputs resolve from the committed catalog and operational AOIs. Preflight checks
source IDs, explicit arguments, server bootstrap and preregistration before any
measurement is allowed. Cloud execution belongs to the roles listed in AGENTS.md;
this agent was instructed to prepare only an offline owner handoff.

The percentile uses NumPy's explicit linear quantile method (primary reference:
https://numpy.org/doc/stable/reference/generated/numpy.quantile.html). Its result
and the configured padding rule are operational estimates for the sampled workload;
sample range is not a confidence interval. reports/tool_latency.json distinguishes
offline readiness from real measurements and contains no invented timing values.
