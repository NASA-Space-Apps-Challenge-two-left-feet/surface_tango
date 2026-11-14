# Handoff: feat/frontend-video-mathlab-import — import the Gemini math-lab (issue #55)

**Why it matters:** SaritaRpo's #41 (math-lab corrections) is blocked: the math-lab was a Gemini Canvas artifact and was never added to the repo. This task brings it in, unchanged in behaviour, so she can start #41.

## Input (the owner provides it before you start)
- `~/Downloads/mathlab_gemini.html`: the math-lab HTML exported by LEONOB2014 from the Gemini Canvas.
- If that file does not exist: write `BLOCKED: math-lab HTML not exported yet` at the end of this file and stop. Do **not** recreate the math-lab yourself (that is the separate fallback issue #56).

## Task
1. Copy `~/Downloads/mathlab_gemini.html` to `static/mathlab/index.html`.
2. Make **only** these edits:
   - Pin every `<script src>` and `<link href>` from a CDN to an exact version (e.g. `d3@7.9.0`, never `d3@7` or `latest`). Prefer cdnjs.cloudflare.com or cdn.jsdelivr.net/npm/. Do not vendor large libraries.
   - Remove any NASA logo, flag, meatball image or `logo=nasa` badge.
   - Insert at the top of `<body>` a visible banner: *"Educational. Not part of the analysis; values here are illustrative physics, not measured results."*
   - Insert as the first line inside `<head>`: `<!-- source: Gemini Canvas, BailaSAR architecture chat; exported 2026-11-14; imported unchanged except pinned CDNs, removed logos and this banner -->`.
3. Write `static/mathlab/README.md` (10–20 lines): where it came from, how to open it (`/static/mathlab/index.html` via `make up`, or the file directly), and this checklist of corrections for #41 (Sarita, not you):
   - Module 1: mark S-band "not available over Colombia".
   - Module 2: use the provided ionosphere screen; show the noise-floor test.
   - Module 3: dual-pol HH/HV only; quad-pol thresholds labelled "quad-pol only".
   - Module 4: replace the GOFF slip story with coherence decorrelation γ = exp(−8π²σ²/λ²).
   - Module 5: keep, marked as an educational extra, not part of the analysis.
4. Do **not** fix the modules themselves. Do not touch `static/index.html` or `app.py` (SaritaRpo's files).

## Files you may touch
- `static/mathlab/index.html` (new)
- `static/mathlab/README.md` (new)
- this brief (report section only)

## Acceptance
- `make sync` first, then `make ci` green.
- Open `static/mathlab/index.html` in a browser: all modules render, and the browser console shows no errors. Report which modules you saw and any console error verbatim.
- `rg -n 'logo=nasa|meatball' static/mathlab/` returns nothing.
- `rg -n '@latest|@[0-9]+/' static/mathlab/index.html` returns nothing (all versions exact).
- Commit with a Conventional Commit, e.g. `feat(mathlab): import the gemini math-lab artifact`, with `Refs: #55, #41` in the body.

## Forbidden
No `git push`, `merge`, `checkout`, `switch`, `reset`, `rebase` (other than `make sync`), `stash`; no `gh`; no network uploads; never print `.env`. Generate no synthetic data and no numbers that look like results. The orchestrator reviews the diff and pushes.

## Report (append below when done)
- Commit hash(es):
- `make ci` tail:
- Modules seen rendering:
- Console errors (verbatim) or "none":
- CDN libraries and pinned versions:
- Anything removed (logos, etc.):
- Open questions:
