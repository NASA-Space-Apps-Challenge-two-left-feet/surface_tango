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
