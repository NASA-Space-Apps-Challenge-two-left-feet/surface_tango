# Handback — opencode GLM-5.3 acting-orchestrator session → claude-home

Written by claude-home (main orchestrator) on resume, 2026-11-15 ~08:30 UTC, reconstructing the opencode acting-orchestrator window (~06:20–08:00 UTC) from the merged PRs and the agent lane reports, because that session ran long tasks and could not write a formal handback itself. This is a reconstruction from the repository record, not opencode's own words.

## What opencode (acting as LEONOB2014) landed while claude-home was away

All squash-merged into `main`:

- **#130 — the pre-registration freeze (#26).** `config/preregistered.yaml` `status: frozen`, hash recorded in `validation/README.md`. This unseals the quake C/K statistics by the project's own rule.
- **#134 / deviation 2 — control-pair fix.** Esteban's #131 showed the frozen `control_K` on both tracks shared an acquisition date with R, breaking the design's "K shares no date with R or C" rule. Jack re-chose K from the gate catalog and the date rule only (track 47: the independent pre-event 12-day pair; track 11: the design's post-event fallback, `control_K_timing: post_event`), and the file was **re-frozen** to blob `36a90fa…`. Deviation 2 is recorded; old-K statistics discarded; track 11 is reported as "post-event control only", never "radar beats baseline".
- **#132 — quake depth displayed** as the USGS preferred-origin estimate (116 km) now that the agents lane promotes it.
- **#135 — cache robustness:** writer locks + crash-safe fetch rollback.
- **#136 — the flood & quake MCP evidence serializers** (the opencode handoff `feat/data-flood-quake-evidence`): `analyze_flood_inundation` and `analyze_earthquake_dpm` now serve the measured artifacts; C/K sealed in the artifact while draft (now unsealed post-freeze).
- **#137 — MERIT `hand_m` band** added to the La Mojana cube (the grok2 handoff): the flood fixture (#121) now cuts. opencode's completion note flagged that grok2's first fixture window (row 0/col 0) was all-NaN and re-cut it at row 432/col 240 (real coverage); the committed-fixture review the fixtures README requires is still owed to the owner.
- **#133 — README reflects the freeze** across all rows.

## Agent final status (all three handoffs finished successfully)

- **grok** — `feat/data-aburra-falsepos` (#33): done; merged by claude-home as **#144**. Stable-pixel false-positive rate added; verdict holds: **no motion above 9.105 mm (17 pairs)**, the hillslope kept fraction above the stable-pixel rate and below the sign-flip null on both tracks.
- **grok2** — `feat/data-mojana-hand-band` (#38): done; merged as **#137**. HAND band finite ratio 1.0; fixture cuts; `test_pipeline_flood -m cache` passes.
- **opencode** — `feat/data-flood-quake-evidence` (#20/#122): done; merged as **#136**; then acted as orchestrator for the window above.

## What claude-home merged on resume (08:20–08:30 UTC)

#144 (grok Aburrá false-positive), #142 (Esteban KB batch 2), #143 (Esteban flood edge cases), #138 (Jack flood budget, measured 0.52 s), #140 (Sarita offline La Mojana pitch), #146 (Alice latency collection — cherry-picked clean off her `develop`-based #139, which was closed; the `4c5b471 … through develop` commit stays excluded).

## Open / owner decisions

- **#145 — LICENSE (held, owner decision).** Esteban proposes Apache-2.0 + NOTICE + DATA_LICENSES. His own PR says "do not merge until the team decides the license." Choosing the project license is the owner's call — **not merged**. Decide before the repo goes public (#46).
- **Fixture review (#137):** the committed La Mojana flood fixture arrays still need the human review the fixtures README requires.
- **`static/prepare_story_cache.py`** still lives under `static/` (served to browsers); move to `scripts/` (carryover from #117/#140).
- **Pre-registration is frozen** (`36a90fa…`); never edit it again without a deviation entry.

## State at handback
- `main` tip: #146. Offline suite: **374 passed, 7 deselected**. 0 open PRs except #145 (held).
- Headline ratified: **La Mojana flood** (#102). Aburrá: calibrated null. Quake: scorecard uninformative; damage proxy both tracks; C/K unsealed post-freeze but still not promoted to display.
