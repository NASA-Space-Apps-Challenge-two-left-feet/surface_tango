@AGENTS.md

## Claude Code notes
- The design doc and decision ledger are `docs/designs/bailasar.md`. Decisions D1–D17 are binding; never re-litigate one silently.
- gstack: `/plan-eng-review` reviews a plan, `/review` reviews a PR, `/ship` ships. Run `/verify` before commits that touch code.
- Before claiming a number, show the command that produced it and its source granule or scene IDs.
- Search the knowledge base first (`docs/kb/`, or `gbrain search` once synced) before asserting a fact about NISAR, the events or the datasets.
- One task at a time in your own worktree. Never `git switch` the main checkout.
- Run `make sync` at the start of a session and before every commit and push; if the `up-to-date-with-main` hook blocks a commit, run `make sync`, re-run the tests, then commit.
