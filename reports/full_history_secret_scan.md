# Full-history secret scan (pre-public gate, #46)

Run before making the repository public, per AGENTS.md ("Before the repo is
made public: run a full-history secret scan"). This supplements the
public-readiness audit (#83, which scanned a commit range); here the whole
history is scanned.

## Commands *(measured 2026-11-15)*
- `gitleaks git --log-opts="--all" --redact --report-format json ...` (gitleaks 8.30.1) — **295 commits, 38.16 MB, 20 findings.**
- `git log --all --name-only` filtered for `.env`, `secrets/`, `local_cache/`, `*.pem`, `*.p12`, service-account JSON — **none in history.**
- Large-blob check (`git rev-list --objects --all | git cat-file --batch-check`, blobs > 10 MB) — **none.**

## Verdict: CLEAN — safe to go public (no real secret in history)

All 20 gitleaks findings are the `generic-api-key` rule firing on non-secrets:

| Count | File | Why it is a false positive |
|---|---|---|
| 12 | `.claude/gsd-file-manifest.json` | Content-hash map (`"<file>.cjs": "<sha>"`) in the **vendored** GSD Core tooling; not project secrets. `.claude/` is linguist-vendored. |
| 6 | `.secrets.baseline` | The detect-secrets baseline stores **hashes** of potential secrets by design (`"hashed_secret": "<hash>"`), not the values. |
| 2 | `tests/test_landslide.py` | The rule matched `assert key == "1_aburra_medellin_bello"` — an assertion on a long AOI **config-key name**, not a credential. |

No `.env`, `secrets/`, `local_cache/`, key file, or service-account JSON ever
entered history; `.gitignore` covers `.env`, `secrets/`, `local_cache`.

## Remaining pre-public steps (owner-gated, #46)
1. Decide the license (#145, held).
2. Flip the repository to public (owner action).
3. Stage/publish the cache release; make the GCS bucket public-read if used.

The secret-leakage gate itself is **green**.
