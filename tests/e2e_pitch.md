# Offline `make pitch` walkthrough checklist (issue #40)

Executed 2026-11-15 05:30 COT (uvicorn variant) and 07:33 COT (full Docker
variant, image rebuilt after #183). All items measured, none skipped.

## Setup

- [x] Stack up: `OFFLINE_DEMO_MODE=1 make pitch` (Docker; requires the
  `--build` flag — fixed in #183; a stale 02:55 image 404s `/api/bulletin`).
- [x] Cache: shared `local_cache/` linked into the worktree.

## Network isolation (measured)

- [x] Every browser request stays on 127.0.0.1 (Playwright route blocking;
  blocked external requests: **0** across all five views).

## Per-view checks (live, flood, landslide, earthquake, synthesis)

- [x] Every panel renders an explicit state (live · cached · not cached ·
  gate result · error); no blank panels, no MISSING.
- [x] Bulletin box renders the recorded live-run bulletin
  (`/api/bulletin`, 2,752 chars ES) with the serving-model tag and the
  SI-Assisted Analytics badge.
- [x] Flood timeline: 11 measured date stops; scrubbing updates the mask
  overlay and the pixel-denominator readout.
- [x] Quake chapter states derive from the cache manifest (post-freeze
  unsealed co-event panel; no stale "sealed" hard-code).
- [x] Zero JavaScript errors (Playwright pageerror listener).

## Evidence commands

    make pitch                                   # after docker compose up --build
    curl -s localhost:8000/api/bulletin          # 2,752-char ES bulletin
    curl -s localhost:8000/api/flood-series      # 11 dates
    Playwright route-block non-localhost; walk ?chapter={live,flood,landslide,earthquake,synthesis}

## Known limits

- Docker is not installed on every team laptop; the uvicorn variant
  (`OFFLINE_DEMO_MODE=1 uv run uvicorn app:app`) covers the same checks.
- The MCP servers are not exercised inside Docker by this walkthrough (the
  bulletin is the recorded one); the live graph run is documented in
  reports/bulletin_demo.md.
