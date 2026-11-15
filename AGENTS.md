# AGENTS.md

Instructions for coding agents (Claude Code, Codex, Antigravity/Gemini, OpenCode, Grok) and the humans on the team working on **BailaSAR**. BailaSAR is a NISAR L-band multi-agent observatory for cascading disasters in Colombia, built for NASA Space Apps 2026 ("Dancing with the SARs", Medellín, Nov 14–15).

This file is the canonical source of repository standards. `CLAUDE.md` imports it.
- The plan and every binding decision (D1–D17) are in [`docs/designs/bailasar.md`](docs/designs/bailasar.md).
- Tasks are the GitHub issues #1–#13.

## Project map

| Path | Lane (owner) | What it is |
|---|---|---|
| `scripts/`, `pyproject.toml`, `Makefile`, `docker-compose.yml`, `Dockerfile`, `.github/` | Data + gate (LEONOB2014) | Discovery, cache build, setup, CI |
| `nisar_colombia_granules_2026.json` | Data + gate (LEONOB2014) | Hour-2 gate output |
| `gee_math/earthquake_dpm_math.py`, `gee_math/landslide_insar_math.py`, `gee_math/flood_polarimetric_math.py` | Hazard modeling (LEONOB2014) | Quake damage proxy, InSAR noise floor, dual-pol flood classes |
| `config/`, `validation/README.md` | Config + pre-registration (Jack4Codes) | `preregistered.yaml` (frozen, hashed), `bailasar.yaml` (operational), power check |
| `validation/scoring.py`, `validation/ALLOWLIST.md` | Scoring (Maru816) | Ranking, precision@k, Wilson, block bootstrap, beats rule |
| `mcp_servers/` (live GEE/ASF tools) | Cloud tools (Jack4Codes) | Tool timing, pair set, ranking/scoring tools |
| `mcp_servers/cache_guard.py`, transport, `agents/`, `validation/event_facts.json` | Agents/MCP (alicealanapineda-byte) | SSE servers, cache_guard, LangGraph, bulletin |
| `tests/fixtures/`, cache release, `README.md`, `docs/kb/` verification | Cloud checks + docs (EstebanOchoaedos) | Real-tile checks, release assets, KB, README |
| `static/`, `app.py`, `video/` | Frontend + video (SaritaRpo) | Mission control, slider, story map, 30 s video |
| `tests/test_<area>.py` | Owner of `<area>` | Each lane owns its own test files |
| `docs/kb/` | Everyone (append) | Living knowledge base (see below) |
| `status/<lane>.md` | Each lane | Short status, updated before every sync |
| `briefs/<branch>.md` | Orchestrator | One brief per branch |
| `local_cache/` | — | Real-data cache. **Never in git** |
| `docs/baseline/` | — | Import notes and patches not yet applied, per lane |

**Cloud rule:** GEE processing and GCP buckets/VMs are run only by LEONOB2014, Jack4Codes and EstebanOchoaedos (they hold the accounts); everyone else works offline from the cache. Work only in your lane's paths. Anything outside them (shared config, CI, this file, contracts) goes through a PR that the orchestrator reviews.

## Non-negotiables (science and evidence)

- **No synthetic or fabricated data**, anywhere: code, cache, tiles, numbers, text, video.
  - A missing pixel or band stays missing (NaN, marked `missing` in provenance, shown as "no data"). Never zero-fill. Never write a fallback that generates values.
  - The only exception: small hand-written arrays with hand-computed expected values, used by pure-logic tests in `tests/` and listed in `validation/ALLOWLIST.md`.
- **Numbers are evidence.** Every number in code comments, reports, PRs, the UI and the video is marked *(measured)* or *(estimate)*, with its denominator and, where it applies, an interval. Every measured number cites the command that produced it and the source granule or scene IDs. When the data shows no signal, say so.
- **Agents never produce numbers.** LLM text uses `{placeholders}` rendered from tool outputs. Event constants come from `validation/event_facts.json`, with primary sources.
- **Frozen parameters live only in `config/preregistered.yaml`**, and its hash is recorded in `validation/README.md`.
  - Do not edit it after pre-registration.
  - Do not view co-event (C-pair) coherence before `validation/README.md` is committed.
  - Operational settings go in `config/bailasar.yaml`.
  - Never hardcode thresholds or AOIs elsewhere.
- **Public data only:** NISAR (ASF DAAC), Sentinel-1/2, GEE public catalogs, WorldPop, OSM, published damage reports. No personal data.
- **Private reference material** (books, outside reports, competitors' work) informs the work. It is never committed, copied into docs or quoted verbatim.
- **Branding:**
  - No NASA logos, flags or identifiers in generated media, badges (`logo=nasa`) or UI headers.
  - No likeness of anyone under 18.
  - Put the "SI-Assisted Analytics" badge on AI-written bulletins.

## Architecture (decided; see the decision ledger)

- Two FastMCP servers as separate processes, **SSE transport**: `mcp-nisar-asf` on :8001 and `mcp-gee-fusion` on :8002.
- `mcp_servers/cache_guard.py` wraps every tool, with a per-tool budget measured at the hour-2 gate.
  - On a timeout it serves only real pre-staged tiles, with provenance (`source`, granule IDs, cache build time).
  - An uncached request returns an explicit "not cached" error.
- LangGraph: `nisar_ingestion` → landslide / earthquake / flood agents → `cross_hazard_synthesis`. Biomass is a TODO.
- Every UI panel renders exactly one of: live · cached · not cached · gate result · error. Never blank.

## Commands

```bash
make setup                               # uv env + pre-commit (and commit-msg) hooks + .env from template
make sync                                # rebase your branch onto the latest origin/main (do this before every commit)
make worktree BRANCH=feat/quake-dpm      # new worktree from the latest origin/main
make check                               # every pre-commit hook on every file (identical to CI)
make test                                # tests that need no network or cache (what CI runs)
make ci                                  # local CI: check + test; run before opening or updating a PR
make prewarm / make fetch-cache          # build or download the real-data cache
make up (live) · make pitch (offline from cache) · make test-dag
```

Run the relevant tests and the hooks before every commit. A failing hook is a real failure: fix the cause, never bypass it. `--no-verify` is forbidden.

## Trunk-based development

- **`main` is the trunk and is always demo-able.** There is no `develop`, no `release/*` and no long-lived branch.
- **Branches are short-lived:** hours, never past the next sync. They are named `<type>/<lane>-<short-description>`, with a Conventional Commits type and a kebab-case description:
  - `feat/quake-dpm`
  - `fix/mcp-sse-transport`
  - `docs/kb-gunw-layers`
- Branches start from the **latest `origin/main`**. Before a PR, rebase your own branch onto `origin/main` (never rebase a shared branch).
- **Always build on the latest trunk.** Run `make sync` (fetch + rebase your branch onto `origin/main`; fast-forward on `main`) **when you start a work session, before every commit and before every push**. A pre-commit hook (`up-to-date-with-main`) refuses a commit on a branch that is behind `origin/main` and tells you to run `make sync`; offline it warns and lets the commit through. If the rebase conflicts, resolve only files your lane owns and ask the owner about the rest; never `--no-verify` past the check.
- **Never commit on `main`, locally or remotely.** The `no-commit-to-branch` hook refuses it. On a private free-plan repo GitHub cannot enforce branch protection, so the hook and the review rule are the guard.
- Unfinished work merges hidden behind the panel states or a config flag in `config/bailasar.yaml`, never by keeping a branch open.
- Integrate small and often: one task (issue) per branch, one PR per branch, merge the same hour if the gate is green.

## Worktrees: one per branch

Several people and agents work at once, so every branch lives in its own git worktree.

```bash
make worktree BRANCH=feat/quake-dpm      # -> ../surface_tango-worktrees/feat-quake-dpm, cache and .env linked
```

- The main checkout (`surface_tango/`) stays on `main`, is **read-only**, and is only fast-forwarded (`git pull --ff-only`). It hosts the shared `local_cache/` and the local `.env`; worktrees symlink both.
- Never `git switch` in a tree while a test, cache build or server runs from it. Open another worktree instead.
- Remove a worktree after its PR merges (`git worktree remove <path>`). Keep the branch.

## Commits

[Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/), enforced by commitizen at the `commit-msg` hook.

```
<type>(<optional scope>)<optional !>: <description>

<optional body: why, wrapped at 72 characters>

<optional footers: BREAKING CHANGE: ..., Refs: #12, Co-Authored-By: ...>
```

- **Types:** `feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `build`, `ci`, `chore`, `style`, `revert`.
- **Scopes:** `gate`, `cache`, `config`, `quake`, `scoring`, `landslide`, `flood`, `mcp`, `agents`, `bulletin`, `web`, `video`, `kb`, `ci`, `deps`, `release`. Omit the scope when a change spans the repository.
- **Description:** imperative, lowercase, no trailing period, at most 72 characters.
- **Breaking changes** (a change to a frozen parameter, tool schema or output contract is one): put `!` before the colon and add a `BREAKING CHANGE:` footer.
- One logical change per commit. Never mix a refactor with a behaviour change.
- Credit agent-written code in the body (e.g. `Co-Authored-By:`), and reference the issue (`Refs: #7`).
- Pass multi-line messages with `git commit -F <file>`.

```
feat(scoring): add barrio-block bootstrap for the built-up excess
fix(cache): keep missing bands as NaN instead of zero-filling
feat(config)!: freeze k and ranking weights in preregistered.yaml

BREAKING CHANGE: scoring reads k from config/preregistered.yaml only.
```

## Pull requests

- Title: a Conventional Commit header. Body: [the template](.github/pull_request_template.md): what and why, issue, how it was tested, numbers (measured/estimate), data or secret impact.
- Base is always `main`. Open as a **draft**; mark it ready once, when `make ci` passes locally.
- The orchestrator (LEONOB2014's lead session) reviews against the brief and merges with **squash**. Never delete branches after merging.

## CI/CD and the Actions-minutes budget

GitHub Actions minutes are scarce: a private repo bills every job rounded up to a whole minute.

- **The merge gate is local CI.** `make ci` (pre-commit on the changed files plus the offline tests) must pass before a PR is opened, marked ready or updated. CI is the last check, not the place to find failures.
- **One Actions job** (`.github/workflows/ci.yml`):
  - It runs only on **pull requests into `main` that are ready for review**, and only when code changed. Pushes, drafts and docs-only PRs (`*.md`, `docs/**`, `status/**`, `briefs/**`, `video/**`) run nothing.
  - `concurrency` cancels a superseded run.
  - It is gated by the repository variable `BAILASAR_ACTIONS_CI` (`on`/`off`), so the owner can switch Actions off when minutes run low.
  - It uses `ubuntu-latest`, a cached `uv` and `timeout-minutes: 10`.
- **Batch fixes into one push** to a ready PR: every push costs a run.
- Heavy work never runs in Actions: cache builds, GEE/ASF calls, `make pitch` E2E and video rendering run locally.
- There is no deploy pipeline. Releases are manual (below).

## Versioning and releases

[SemVer 2.0.0](https://semver.org/), **0.x until the submission**.
- Cut a release with commitizen (`cz bump`) on a `chore/release-vX.Y.Z` branch, then PR into `main` and tag `vX.Y.Z` on `main`. `cz bump --files-only` and `cz changelog --incremental` exit 16 even when they work: verify the files, not the exit code.
- The submission release also carries the cache asset (`make fetch-cache`) and is published only on the owner's go-ahead.

## Secrets

- Secrets live only in the git-ignored `.env` (from `.env.example`): Earthdata Login, GEE service account, GCS, LLM provider keys.
- Never commit, print, log or paste secret values, including in PR bodies, status files, issues and chat.
- New configuration keys go into `.env.example` with an empty value.
- `detect-secrets` and `detect-private-key` run on every commit. A finding is never silenced on an agent's own authority: confirm it is a placeholder, then ask the owner before changing `.secrets.baseline`.
- Before the repo is made public: run a full-history secret scan (gitleaks or `gstack-redact`), and make sure `.env`, `secrets/` and `local_cache/` are not in history.

## Living knowledge base (`docs/kb/`)

Every fact the code or the pitch relies on lives as a short note, not in someone's head or a chat.
- **One note per fact or method:** `docs/kb/<topic>-<slug>.md`, from [`docs/kb/TEMPLATE.md`](docs/kb/TEMPLATE.md).
- **Front matter:**
  - `status`: `verified` | `unverified` | `superseded`
  - `source`: URL or DOI
  - `accessed`: date
  - `quote`: a short verbatim quote, at most 25 words
  - `used_in`: the files or decisions that depend on it
  - `verified_by`
- A claim pasted from an AI summary is `unverified` until someone reads the primary source.
- Never edit a verified note's claim in place: add a new note that `supersedes` it, and mark the old one `superseded`.
- When a branch adds or changes a method, threshold or data source, it adds or updates the KB note **in the same PR**.
- Measured results go in `reports/` (with the command and IDs), not in the KB.
- Sync the KB to gbrain after merges (`/sync-gbrain`), so every agent session can search it.

## Orchestrator and executors

- **One Claude session is the orchestrator.**
  - It owns this file, `config/preregistered.yaml` after freeze, CI and the plan.
  - It writes `briefs/<branch>.md` for each branch (Goal · Issue · Files you may touch · Out of scope · Steps · Acceptance · Outward actions needing approval · If blocked).
  - It reviews each PR against its brief, and merges.
- **Executors** (teammates' agents, Codex, Antigravity, OpenCode, Grok):
  - They read only `AGENTS.md` and their brief, touch only the listed files, and run the acceptance commands.
  - They update `status/<lane>.md` and open the PR.
  - When something outside the brief is needed, they write `BLOCKED: <reason>` in their status file and stop. They never improvise.
- **Second opinions** (`grok -p`, `opencode run`) get a structured summary, never secrets. Their answers are advice, checked against data before they change anything.

## Agent conduct

- Ask before destructive or outward-facing actions: pushes, merges into `main`, making the repo public, publishing releases, deleting data, paid runs, editing GitHub settings. Approval of one step never extends to the next.
- Prefer the smallest change that fully solves the task, and follow existing patterns.
- Report outcomes faithfully: say what was tested, what failed and what was skipped.
- Review every rendered map, chart or frame as an image before accepting it.
- Shell (zsh): never name a variable `path`.
- Times shown to the team are in Bogotá time (UTC−5); logs stay UTC.
- Keep this file current: when a rule changes, change it here in the same PR.

## AI disclosure

This project is built with Claude Code + gstack, OpenAI Codex, Google Antigravity/Gemini, OpenCode (GLM), Grok and LangGraph. Keep this list current in the README and the submission.
