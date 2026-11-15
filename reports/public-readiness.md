# Public-readiness audit (secret scan + public readiness) — issue #46

- **Audit baseline:** `6e2a761` (`origin/main` when the audit started).
- **Final state audited:** `fc52bfd` (`origin/main` at commit time). The team merged #63–#71 while the audit ran; every affected finding was re-verified against the final tree after a user-approved `make sync` (no conflicts; `README.md`, `static/`, `video/`, `app.py` changed, so open findings cite line numbers at `fc52bfd`).
- **Time (UTC):** 2026-11-15T02:03–02:19Z (Sat Nov 14 2026, 21:03–21:19 Bogotá).
- **Tools:** gitleaks 8.30.1 (`gitleaks version`), detect-secrets v1.5.0 (`.pre-commit-config.yaml` rev).
- **Scope:** full git history over all refs (`git log --all`), working tree at branch `chore/data-public-readiness-audit`. Audit only: nothing was fixed, deleted or rewritten; no secret value was ever printed (gitleaks `--redact`; summaries carry rule/file/commit/line only).

## Verdict

**READY: 0 blockers** — 3 "fix before public" and 3 notes remain (listed below; none leaks a secret or makes a false public claim). The owner decides each.

Severity used: **blocker** = a real secret anywhere in history, or something that breaks a project rule / makes a false public claim if the repo went public now; **fix before public** = must be fixed on the way to public; **note** = judgement call.

## Commands run (exact; exit codes)

| # | Command | Exit | Result |
|---|---|---|---|
| 1 | `gitleaks git --log-opts="--all" --redact --report-format json --report-path /tmp/gitleaks-surface-tango.json .` | 1 | 15 findings, all `generic-api-key`. Exit 1 = "leaks found" (expected when findings exist). Run four times as refs moved during the audit (44 → 61 → 64 → 70 commits): identical 15 findings every time; final pass 70 commits / 35.36 MB in 4.51 s. The report stayed in `/tmp`; only rule/file/commit/line were read from it. |
| 2 | `uv run pre-commit run detect-secrets --all-files` | 0 | "Detect secrets … Passed" on the baseline tree and again on the post-sync final tree; no new entries vs `.secrets.baseline`; the baseline was never modified (`git status` clean). |
| 3 | `git log --all --name-only --format= \| sort -u` | 0 | 965 distinct paths in full history (stable across the last three passes). |
| 4 | forbidden-path greps over #3's list (`.env*`, `*.pem|*.p12|*.key`, `*credentials*.json|*service*account*.json|-[0-9a-f]{12}.json`, `.netrc|\.earthdata*`, `secrets/`, `local_cache`) | 1 (no hits) | Only the allowed `.env.example` matched a dotenv pattern; after excluding it: 0 hits, on every pass. |
| 5 | `git rev-list --objects --all \| git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \| awk '$1=="blob" && $3>10000000'` | 0 | No blob >10 MB on any pass. Largest blobs: two `uv.lock` versions, ~1.1 MB each. |
| 6 | branding greps: `grep -rn -i -e 'nasa' README.md static/ app.py docs/`, `grep -rn -i -e '0B3D91' -e 'logo=' <same + video/>` | 0 / 1 / 2 | At the baseline: 18 NASA-text hits (all ok, listed under check 5) and one `0B3D91` badge (`README.md:3`, since removed by #70). On the final tree `static/` (3 files), `app.py`, `video/` (2 files) have 0 hits of either kind; exit 2 was only the then-missing `video/` dir (it exists now, added by #68/#69). |
| 7 | numbers/dropped-scope greps + file reads (`README.md`, `static/**`, `video/**`, `docs/baseline/**`, `agents/**`, `app.py`) | 0 (hits) / 1 (no hits) | Baseline findings below; S-band and math-lab greps: no hits at any point. |
| 8 | `test -e LICENSE` | 1 | No LICENSE file; `README.md:182` says "License: to be decided by the team (TODO)". |
| 9 | `git grep -E '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'` over tracked files | 0 | Only vendored-tool attribution emails inside `.claude/gsd-core` (check 8); no team addresses, no phone numbers. |
| 10 | `git fetch origin` / `make sync` (user-approved) | 0 | `make sync` = `git rebase --autostash origin/main`, run twice (02:17, 02:19 UTC) as #63–#71 landed mid-audit; clean both times; audit deltas re-verified after each. |

## Open findings (state at `fc52bfd`)

| # | Severity | Check | Location | Finding (never a value) | Proposed fix | Owner lane |
|---|---|---|---|---|---|---|
| 1 | fix before public | 8 | `README.md:182` (repo root) | License is "to be decided by the team (TODO)" and no `LICENSE` file exists. Not a false claim (the old MIT badge was removed by #70), but a public repo ships with undefined licensing. | Owner chooses a license (the baseline README badge said MIT) and adds the `LICENSE` file before submission. | Orchestrator / owner |
| 2 | fix before public | 7 | `agents/orchestrator.py:100-145`; `agents/state.py:10`; `mcp_servers/gee_fusion_mcp.py:369`; `static/index.html:283,356-369` | Code/README mismatch on biomass: README marks it dropped/out of scope (`README.md:90`, `:108`, `:147`), but the LangGraph still wires a 4th unconditional `biomass_agent` (node + fan-out/fan-in, tool registered) and two static leftovers remain (a colorMap entry and the biomass inspector SVG). The diagram's numbers are covered by finding 3. | Gate biomass behind a `config/bailasar.yaml` flag (AGENTS unfinished-work rule) or remove the node from the 3-agent graph; delete the static leftovers. | Agents/MCP (alicealanapineda-byte) + Frontend + video (SaritaRpo) |
| 3 | fix before public | 6 | `docs/baseline/unapplied_patches/story_map_tour.js` (8 lines), `story_map_hud.html:33` | The unapplied patches still carry the fabricated narrative numbers (612/612.8 tC, 22.4 mm, 145 mm, 34°, 92/54/68/0/76 %, 31.2 ha, 180 Mg/ha). `BASELINE_NOTES.md:22` flags them and orders replacement with placeholders; the shipped story map (`static/story-map.js`, via #71) already uses `{placeholders}` (40 placeholder sites, 0 fabricated-number hits), so these patches are superseded but still publish fabricated values in repo text. | Replace the numbers with `{placeholders}` or delete the superseded patch files; update `BASELINE_NOTES.md:22` accordingly. | Frontend + video (SaritaRpo, #12) |
| 4 | note | 5 | `static/index.html:85`; bulletin code pending | The "SI-Assisted Analytics" badge (AGENTS § Branding) now exists as a UI element (`si-badge`, hidden until a bulletin loads), but the bulletin-side enforcement is still pending; `README.md:143` disclaims this honestly. | Implement badge rendering with the bulletin integration (#11). | Agents/MCP (alicealanapineda-byte) |
| 5 | note | 6 | `static/index.html:101,317,341,348,354,366,369` | Illustrative/uncited constants in the radar-inspector SVG diagrams: 5.6 cm, +3.5 dB, γ = 0.82 / 0.24, 180 Mg/ha, RFDI > 0.55. The README side is fully clean at `fc52bfd` (zero unmarked number claims; the circuit-breaker value is explicitly labelled a configuration estimate at `README.md:144`). | Mark the diagrams as illustrative or add citations. | Frontend + video (SaritaRpo) |
| 6 | note | 1 | `.claude/` (tree and history) | Internal agent tooling ships in the repo: `gsd-core` agents/workflows, vendored `re2js` / `tap-parser` (upstream attribution only) and `gsd-file-manifest.json`. All 854 hex values in the manifest were proven to be sha256 checksums of tracked files (854/854 verified, no values printed), so nothing sensitive leaks; publishing internal tooling and vendored code is an owner choice. | Owner decides whether `.claude/` belongs in the public repo; if kept, verify the vendored licenses permit redistribution. | Orchestrator / owner |

Counts *(measured)*: **0 blockers, 3 fix before public, 3 notes = 6 open findings at `fc52bfd`.**

## Resolved while the audit ran (#63–#71 merged mid-audit; no action needed)

- **Preloaded fabricated results in the UI (baseline blocker):** at the baseline, `static/index.html:151-165` preloaded an `ORANGE` alert, a hypothesis text (γ > 0.35, 22.4 mm creep, 145 mm rain) and a metrics JSON (`downslope_disp_mm_p99` 22.4, `rain_15d_mm_p95` 145.2, `fabdem_slope_deg_p95` 34.8) — none of these values exist in `config/` or `validation/`. #71 (`fc52bfd`) removed them: the panel now starts at "Awaiting measured results" (`static/index.html:267`) / "No report loaded" (`:412`); 0 hits for 22.4/145.2/34.8.
- **Missing AI disclosure (baseline blocker):** #70 (`fc0bafc`) added the full list and review process at `README.md:174-178` (Claude Code + gstack, OpenAI Codex, Google Antigravity/Gemini, OpenCode (GLM), Grok, LangGraph).
- **LICENSE false claim (baseline blocker, reduced to finding 1):** the baseline `README.md:7` badged and linked "License: MIT" with no file; #70 removed the badge and replaced it with the honest TODO (see finding 1).
- **NASA-blue badge (baseline fix item):** `README.md:3` used the badge colour `0B3D91`; #70 removed the badge row entirely. No `logo=nasa` ever existed; no `0B3D91` anywhere on the final tree.
- **Biomass/GOFF advertised (baseline fix items, README side):** #70 restructured the README with an explicit Status table that marks biomass, GOFF/surface-rupture, split-spectrum ionosphere, GEE High-Volume, math-lab and S-band all `dropped` (`README.md:90-95`), states "Biomass is outside the submission scope" (`:108`) and "out of scope / TODO even where imported baseline code still mentions them" (`:147`); the architecture diagram now shows GUNW/GCOV only. The code side remains as finding 2.
- **34° / 145 mm pull-quote and uncited README constants (baseline fix items):** #70 removed the quote and every README constant; the final README has zero unmarked number+unit claims. The new `video/storyboard.md` + `recording-run-sheet.md` (#68/#69) use evidence placeholders (no unmarked numbers, no branding hits).

## Checks 1–8, each with a result

1. **Full-history secret scan:** 15 gitleaks findings in 70 commits (`--all`, final pass), all rule `generic-api-key`, **0 real secrets, 0 blockers**:
   - 12/15 = `.claude/gsd-file-manifest.json` lines 22, 261, 284, 331, 814, 839 in commits `12513b5` (on `origin/main`) and `e5a4ff9` (on `origin/build/gsd-core`; identical file content) — file-checksum entries, **false positive** (proof: 854/854 values equal the sha256 of the tracked file each key references).
   - 2/15 = `.secrets.baseline:137` in commits `a16a47f` (on `origin/main`) and `26e60e1` (on `origin/build/data-setup-lock`) — detect-secrets' own `hashed_secret` (a sha256) for a prose line in `docs/designs/bailasar.md` ("R6 secrets hygiene" table row), **false positive**.
   - 1/15 = `tests/test_landslide.py:209` in commit `e54d99b` — a hand-written AOI-key fixture, **false positive**; that commit exists only on the local branch `feat/data-aburra-insar` and was never pushed to any remote (`git branch -r --contains` empty).
   - Exposure if public today: 14/15 findings sit on commits reachable from remote refs (7 on `origin/main` chains, 7 on origin-only feature branches); 1/15 is local-only.
2. **Current tree:** `detect-secrets` hook Passed (exit 0) on the baseline and final trees, no new entries, `.secrets.baseline` unmodified.
3. **Forbidden paths:** none found. 965 distinct paths in history; the only dotenv-ish path is the allowed `.env.example`; no `*.pem`/`*.p12`/`*.key`, no credentials/service-account JSON (including the `-[0-9a-f]{12}.json` form), no `.netrc`/`.earthdata*`; `secrets/` and `local_cache` never entered history.
4. **Large blobs:** none found. No blob >10 MB; largest are two `uv.lock` versions at ~1.1 MB.
5. **Branding:** no `logo=nasa` anywhere at any point; no NASA meatball/worm images and no `nasa` in image filenames (no image files exist: `static/` holds `index.html`, `mission-control.tailwind.css`, `story-map.js`; `video/` holds two markdown files) — so also **no photos of people, none found**. The `0B3D91` badge from the baseline was removed by #70. Text mentions listed as **ok**: challenge name (`README.md:3`), mission partners and ASF DAAC credits (`README.md:155`, `:170-172`, which also states the no-logos/no-endorsement rule), branding rules and source citations in `docs/designs/bailasar.md`, `docs/kb/*` (2 files cite NASA sources), and `docs/baseline` (`BASELINE_NOTES.md:12` records the `logo=nasa` removal; `makefile_discover_target.mk:1` says "Query NASA ASF" as a data-source credit).
6. **Numbers without evidence:** baseline findings confirmed and tracked; final state: README clean (zero unmarked number claims), `static/story-map.js` and `video/*.md` use placeholders, the remaining items are finding 3 (docs/baseline patch numbers) and finding 5 (illustrative SVG constants). The known claims were confirmed at baseline (145 mm, 34°, 612 tC, 22.4 mm) and are gone from every shipped surface at `fc52bfd`; they survive only in the superseded patches of finding 3. SVG coordinates and Tailwind classes (e.g. `slate-400 mt-`) were excluded as non-claims.
7. **Dropped scope (biomass, S-band, GOFF rupture, math-lab):** final state — biomass: README truthful (dropped), code wiring remains (finding 2); GOFF: README truthful (dropped, `README.md:91`), 0 hits anywhere else in `static/`/`agents/`/`app.py`; S-band: **none found** at any point; math-lab: **none found** (dropped row at `README.md:94`).
8. **Public basics:** LICENSE — no file, README honestly says TODO (finding 1); AI disclosure — present (`README.md:174-178`); personal data — **none found** beyond git author names/emails: the only emails in tracked files are vendored-tool attribution (`rsc@google.com` in `.claude/gsd-core/…/re2js.cjs`, `eemeli@gmail.com` in `tap-parser.cjs.LICENSE.txt`), and the Team table (`README.md:186-193`) lists public GitHub handles only; `.gitignore` — **ok**: covers `.env` + `.env.*` with `!.env.example`, `secrets/`, `local_cache`, plus `*.pem`, `*service-account*.json` and data formats (unchanged by #63–#71).

## Counts with denominators *(measured)*

- gitleaks: 15 findings in 70 commits over all refs (4 passes as refs moved: 44 → 61 → 64 → 70; identical findings each time), all `generic-api-key`, 0 assessed real (12+2+1 classification above; every false positive was established without printing any value).
- Origin exposure: 14/15 findings on remote-reachable commits; 1/15 local-only.
- detect-secrets: 0 new findings against `.secrets.baseline` (Passed, both trees).
- Paths: 0 forbidden in 965 distinct historical paths.
- Blobs: 0 over 10 MB in the full history (largest ~1.1 MB).
- Findings: 0 blockers + 3 fix before public + 3 notes = 6 open at `fc52bfd`; 3 baseline blockers were resolved mid-audit by #70/#71.

## README rows (for the orchestrator to paste)

| Component | State | Issue/PR | Report |
|---|---|---|---|
| Public-readiness audit (secret scan + public basics) | live — audit done: READY, 0 blockers (3 fix before public, 3 notes) | #46 | `reports/public-readiness.md` |

## Open questions for the owner

- License choice (finding 1); the baseline badge said MIT, the current README says TODO.
- Biomass: config-gate or extract from the graph (finding 2).
- Should `.claude/` internal tooling ship in the public repo (finding 6)?
- If CI ever runs gitleaks, an allowlist config for `.claude/gsd-file-manifest.json` and `.secrets.baseline` would silence the proven false positives (owner decision; this audit added none).
- The local-only commit `e54d99b` (branch `feat/data-aburra-insar`) holds one false-positive finding; harmless either way, no action needed.

*Report produced by the opencode GLM-5.3 agent session under `briefs/chore/data-public-readiness-audit.md`; audit only — no lane files, configs or history were changed.*
