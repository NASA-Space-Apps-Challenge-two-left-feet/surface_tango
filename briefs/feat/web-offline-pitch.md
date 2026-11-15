# Brief: feat/web-offline-pitch — the offline La Mojana pitch, end to end (owner: @SaritaRpo)

**You run this on your own laptop, in your own Claude Code, under your own account.** It is frontend + video only: no Earth Engine, no GCS, no Earthdata. Everything comes from the cache release you download and from the merged reports.

- **Goal:** `make pitch` becomes a complete, network-free walkthrough of the ratified headline (La Mojana flood, #102). The curtain slider and all story chapters render from the downloaded cache, every panel shows exactly one of the five states, and `video/assemble.py` produces a silent 30-second draft cut that follows the locked storyboard timings. Voice-over is added later at recording (#43); this brief does not record audio.
- **Issues:** #37 (slider + story map) and #39/#43 prep (video assembly). Plan 03-08 / 04-02.
- **Lane rule:** you own `static/`, `app.py`, `video/`, `status/frontend-video.md`. Touch nothing else. If you need another lane's file, write `BLOCKED: <reason>` in `status/frontend-video.md` and stop.

## Inputs (all offline)
- The **team cache release** `cache-2026-11-15` (download step below): `local_cache/{eje_cafetero,aburra,mojana}/` with cubes, COGs, Sentinel tiles and per-AOI manifests. `coherence_C`/`coherence_coseismic` and the `quake/` folder are **withheld** — treat them as `not cached`, never blank.
- Measured reports already on `main`: `reports/mojana.md` (#98), `reports/aburra.md` (#109), `reports/quake_dpm.md` (#111, counts only), `validation/README.md` (power check + headline).
- The locked storyboard: `video/storyboard.md` (#119) — the 30-second cue sequence, dates, denominators and the PROVISIONAL / uncalibrated labels. **Every on-screen number must come from a report; copy none by hand.**

## What to build
1. **Five panel states, every panel.** Each mission-control and story panel renders exactly one of: `live` · `cached` · `not cached` · `gate result` · `error`. Never blank. Drive them from `local_cache/<aoi>/manifest.json` band `status` (`cached` / `missing` / `withheld`) and the story-evidence gates already in `static/` (#120).
2. **La Mojana as the headline chapter.** The curtain slider and the story chapters center on La Mojana open water (the measured HH mask) with the Sentinel-1-vs-NISAR comparison. Aburrá shows its null verdict ("no motion above 9.105 mm"); the quake panel shows the damage-proxy context with C/K **sealed** and the scorecard as "uninformative".
3. **`make pitch` runs with the network off.** Start the offline profile, load `http://localhost:8000`, and confirm no panel calls the network and none is blank. Record the check in `status/frontend-video.md`.
4. **`video/assemble.py`** (new): from `video/storyboard.md`'s timings and the staged frames/screenshots, render a **silent** 30-second draft cut (1920×1080, 30 fps) with on-screen cards showing each measured number and its source. Use `ffmpeg` (the `loudnorm`/`concat` recipe pattern). Mark every VO slot as a placeholder. Output goes under `video/` but the rendered `.mp4` is **git-ignored** (add the pattern to `.gitignore` if absent); commit only the script and a short `video/README.md` on how to run it.
5. **Move `static/prepare_story_cache.py` to `scripts/`** (it is server-published under `static/` today) and update the command in `status/frontend-video.md`. (Carryover from #117.)

## Out of scope
- Any Earth Engine / GCS / Earthdata call, or rebuilding the cache (data lane).
- New science numbers — you only display what the reports measured.
- Recording real voice-over or committing media binaries.
- The MCP servers, agents, config, or any hazard math.

## Acceptance
- `make ci` green (offline tests + hooks).
- `make pitch` serves every panel in one of the five states with the network disabled; no blank panels; the quake C/K layers show `not cached`.
- Every on-screen number traces to a report (cite the file in the panel or a data attribute).
- `uv run python video/assemble.py` writes a 30 s silent draft `.mp4`; the `.mp4` is git-ignored; the script and `video/README.md` are committed.
- Draft PR into `main`, Conventional Commit title, `Refs: #37`, update `status/frontend-video.md`.

## Rules (AGENTS.md, non-negotiable)
- No synthetic or fabricated data; missing stays missing (transparent / "no data"), never zero-filled.
- Every number is *(measured)* with its source, or *(estimate)*; nulls are reported.
- No NASA logos, flags or identifiers in any frame or badge; no likeness of anyone under 18; the SI-Assisted Analytics card on AI-written text.
- One worktree, short-lived branch, `make sync` before every commit, `make ci` before the PR. Never `--no-verify`.
- Do **not** push to `main`, merge, or edit another lane's files. Open a draft PR and let the orchestrator review and merge.

## Report (append here when done)
What you built, the `make pitch` offline check result, the assemble command and its output path, measured numbers shown with their report sources, and anything you could not do.
