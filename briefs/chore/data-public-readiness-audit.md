# Brief: chore/data-public-readiness-audit — secret scan and public-readiness audit (agent: opencode GLM-5.3)

- **Goal:** know, before the repo is made public, everything that would leak a secret or break a project rule if it were public now, with a concrete fix list. **Audit only:** you report, you don't fix.
- **Issue:** #46 (plan 05-04, first step: "secret scan") · **Rules:** `AGENTS.md` § Secrets ("Before the repo is made public …"), § Non-negotiables (branding, numbers as evidence, public data only).
- **Inputs:** this repo's full git history (all branches: `git log --all`), the working tree at `origin/main`, `.secrets.baseline`, `.gitignore`.
- **Outputs:** `reports/public-readiness.md` (format below). Nothing else.
- **Files you may touch:** `reports/public-readiness.md`, this brief. **No other file**, even to fix a finding: list it with the proposed fix and the owning lane (AGENTS.md project map).
- **Out of scope:**
  - rewriting history, deleting files, editing `.secrets.baseline`;
  - changing GitHub settings or making the repo public;
  - creating releases;
  - rotating keys (you report; the owner rotates).

## Steps
1. **Full-history secret scan.** `gitleaks` must be on PATH (the owner installs it with `brew install gitleaks` before you start; if `command -v gitleaks` is empty, write `BLOCKED: gitleaks not installed` and stop).
   - Run: `gitleaks git --log-opts="--all" --redact --report-format json --report-path /tmp/gitleaks-surface-tango.json .`
   - Never pass the report through `cat` or quote values. Summarise only: rule ID, file, commit short SHA, line, and whether the commit is reachable from `origin/main`.
   - For each finding, decide *real secret* vs *placeholder/false positive*, and say why (for example "env-var name only", "allowlisted with pragma", "test fixture on example.test"). If you can't tell without seeing the value, mark it **"needs owner check"**. Don't print the value.
2. **Current tree.** `uv run pre-commit run detect-secrets --all-files` must pass. It checks against `.secrets.baseline` without rewriting it; don't run `detect-secrets scan --baseline`, which rewrites the baseline. Report the exit code and any new entries (file + line + type only). If the hook modified `.secrets.baseline` anyway, run `git restore .secrets.baseline` and note it.
3. **Paths that must never be in history:** check `git log --all --name-only --format= | sort -u` for:
   - any dotenv file other than the example template, the git-ignored secrets folder, the `local_cache` folder;
   - `*.pem`, `*.p12`, `*.key`;
   - service-account JSON (`*credentials*.json`, `*service*account*.json`, `*-[0-9a-f]{12}.json`);
   - `.netrc`, `.earthdata*`.

   List any hit with the commit that added it.
4. **Large blobs** (>10 MB) in history: `git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | awk '$1=="blob" && $3>10000000'`. List them, with path and size.
5. **Branding** (AGENTS.md: no NASA logos, flags or identifiers in generated media, badges or UI headers):
   - Search `README.md`, `static/`, `video/`, `app.py` and `docs/` for `logo=nasa`, NASA meatball/worm image files, `nasa` in image filenames, and "NASA" in UI headers or titles.
   - Search those same paths for the badge colour `0B3D91`.
   - Text mentions of the challenge name or of the NASA ASF DAAC as a data source are fine: list them as "ok". Images of people: list any file under `static/` or `video/` that looks like a photo of a person, for the owner to check (no likeness of anyone under 18).
6. **Numbers without evidence** in public-facing text (`README.md`, `static/**`, `docs/baseline/**`, `video/**`):
   - List every quantitative claim that is not marked *(measured)* with a command and IDs, or *(estimate)*.
   - Known ones to confirm: "145 mm", "34°", "612 tC", "22.4 mm".
   - Give file:line and the fix: remove it, mark it as an estimate with a source, or replace it with a `{placeholder}`.
7. **Dropped scope still shown to the public:**
   - The items: biomass, S-band, GOFF rupture, the math-lab.
   - Where to look: `README.md`, `static/`, `agents/`, `app.py` (UI text and graph nodes).
   - Report file:line for each mention, plus the owning lane.
8. **Public basics:**
   - `README.md` links a `LICENSE` file, but there is none in the repo (verify).
   - The AI disclosure list is in the README (AGENTS.md § AI disclosure).
   - There is no personal data beyond git author names and emails (list any other emails or phone numbers found in tracked files).
   - `.gitignore` covers `.env`, `secrets/` and `local_cache/`.

## Report format (`reports/public-readiness.md`)
- Header:
  - the commit audited (`git rev-parse --short origin/main`) and the time (UTC);
  - the exact commands run, each with its exit code;
  - the gitleaks and detect-secrets versions.
- A **verdict** line: `READY` / `NOT READY: n blockers`.
- A findings table: `# · severity (blocker / fix before public / note) · check (1–8) · location (file:line or commit) · finding (never a secret value) · proposed fix · owner lane`.
  - Any real secret anywhere in history is a **blocker**, with the fix "rotate the key at the provider, then rewrite history (owner decision)".
- Counts with denominators, for example "gitleaks: 3 findings in 182 commits *(measured)*".
- A "README rows" subsection: the Status-table row for this audit (component · state · issue · report) for the orchestrator to paste.

## Acceptance
- `reports/public-readiness.md` exists and covers checks 1–8; each check has a result, including "none found".
- No secret value appears anywhere: `rg -n -i 'AKIA|ghp_|gho_|sk-|xox[bp]-|-----BEGIN|eyJ[A-Za-z0-9_-]{20}' reports/public-readiness.md` is empty.
- `make ci` green.
- One local commit: `docs(release): add public-readiness audit for the repo` with `Refs: #46` and `Co-Authored-By: opencode GLM-5.3`.

## Outward actions needing approval
None allowed. You don't:
- push, merge, switch branches, reset, stash or rebase;
- run `gh`;
- write to GCS or call any paid API.

The orchestrator reviews the report and the owner decides each blocker.

## If blocked
Write `BLOCKED: <reason>` at the end of this file and stop.

## Rules (from AGENTS.md, non-negotiable)
- Never print, log or paste secret values, including in the report, this brief and your chat output.
- No synthetic data. Every count you report is *(measured)* with the command that produced it.
- Run `make sync` before committing. If the `up-to-date-with-main` hook refuses the commit and `make sync` is denied to you, write `BLOCKED: behind main` and stop; the orchestrator syncs the branch.

## Report (append to the end of this file when done)
What you ran, the verdict, the number of findings by severity, anything you couldn't check, open questions for the owner.

### Report — audit completed 2026-11-15T02:12Z (blocked earlier the same session on "gitleaks not installed"; the owner installed gitleaks 8.30.1 and the audit resumed from step 1)

**What ran** (full detail, exact commands and exit codes in `reports/public-readiness.md`):

- Check 1: `gitleaks git --log-opts="--all" --redact … .` — exit 1 ("leaks found"), 15 findings. Run three times as refs moved during the audit (44 → 61 → 64 commits; #63–#66 merged into main mid-audit): identical findings every time. All 15 are `generic-api-key` and all assess as false positives without printing any value: 12 are sha256 file-checksums in `.claude/gsd-file-manifest.json` (proven 854/854 against the tracked files), 2 are detect-secrets `hashed_secret` entries in `.secrets.baseline` (a hash of a prose line in the design doc), 1 is a hand-written AOI-key test fixture in `tests/test_landslide.py` whose commit `e54d99b` was never pushed to any remote. **0 real secrets.**
- Check 2: `uv run pre-commit run detect-secrets --all-files` — exit 0, Passed, no new entries, baseline untouched.
- Check 3: 965 distinct historical paths; 0 forbidden (only the allowed `.env.example` matches a dotenv pattern; no pem/p12/key, no credentials/service-account JSON, no netrc/earthdata, `secrets/` and `local_cache` never in history).
- Check 4: 0 blobs >10 MB (largest: `uv.lock` ~1.1 MB ×2).
- Check 5: 0 `logo=nasa`; no image files at all (`static/` = `index.html` only, `video/` absent) → no NASA imagery, no photos of people to review; 1 badge uses colour `0B3D91` (`README.md:3`); text mentions of the challenge name / NASA ASF as data source: ok.
- Check 6: confirmed the known claims (145 mm, 34°, 612 tC, 22.4 mm) at baseline; at `fc52bfd` they are gone from every shipped surface (README restructured by #70, story map landed with placeholders via #71) and survive only in the superseded `docs/baseline` patches (open finding).
- Check 7: at `fc52bfd` the README marks biomass, GOFF/rupture, split-spectrum, GEE High-Volume, math-lab and S-band all `dropped` (`README.md:90-95`); biomass wiring remains in `agents/orchestrator.py` (open finding); GOFF: 0 hits elsewhere; S-band: none; math-lab: none.
- Check 8: LICENSE: no file, README:182 honestly says TODO (open finding: choose and add before submission); AI disclosure present at README:174-178; personal data: none beyond git authors (only vendored-tool attribution emails); `.gitignore` covers `.env`, `secrets/`, `local_cache`: ok.

**Verdict:** READY: 0 blockers — 3 "fix before public" (license TODO, biomass still wired in code vs README "dropped", fabricated numbers left in the superseded docs/baseline story-map patches) and 3 notes (SI-Assisted bulletin badge pending, illustrative SVG constants, `.claude/` tooling shipped publicly). The verdict changed mid-audit: at baseline `6e2a761` it was NOT READY: 3 blockers, but the team merged #70 (submission-draft README: AI disclosure added, badges and uncited constants removed, every dropped-scope item marked, license made an honest TODO) and #71 (offline rehearsal: the preloaded fabricated UI results removed, panels start "Awaiting measured results", story map uses `{placeholders}`, SI-Assisted badge element added), all re-verified at `fc52bfd` after a user-approved `make sync`.

**Findings by severity:** 0 blockers + 3 fix before public + 3 notes = 6 open findings at `fc52bfd`; 3 baseline blockers resolved mid-audit by #70/#71 *(measured)*.

**Couldn't check:** nothing skipped; the only non-check was image review for photos of people — `static/` and `video/` contain no image files at this commit, so there is nothing to review. One zsh pitfall hit mid-audit (`$c:file` colon-modifier mangling a `git show` loop) was caught by re-verification and corrected; the corrected numbers are the ones reported. Mid-audit, origin/main advanced (#63–#66); the user approved `make sync`, the branch was rebased onto `96268bd` with no conflicts, the delta (gitleaks/paths/blobs plus README/static continuity) was re-verified, and the commit was made on top (`README.md`, `static/`, `video/`, `app.py` were untouched by the new commits, so every line reference in the report stayed valid).

**Open questions for the owner:** LICENSE choice (badge says MIT); biomass: config-gate or cut from the graph; whether `.claude/` internal tooling should ship public (all its manifest values are proven checksums); a gitleaks allowlist config if CI ever runs it; `e54d99b` is a local-only false positive (no action).
