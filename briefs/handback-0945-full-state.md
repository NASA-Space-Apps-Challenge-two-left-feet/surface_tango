# Handback / full state — claude-home orchestration, 2026-11-15 ~09:45 UTC

Written so orchestration can continue seamlessly. Deadline **D = 2026-11-15 23:59 COT (today)**. `main` is green (435 offline tests), **0 open PRs**, 129 PRs merged.

## The four handoffs — all finished and merged
- **#160 grok2 — La Mojana L-band vs C-band** per date (`reports/mojana_lvsc.md`): NISAR open water vs Sentinel-1, with denominators and S1 scene IDs; honest `no S1 within window`, the 2026-08-28 double-scene case disclosed.
- **#161 grok — quake E_C − E_K** (`reports/quake_dpm_interpretation.md`): now the pre-registration is frozen and C/K unsealed. grok **re-streamed the frozen K granule** (not the stale old-K passes), so it is unaffected by #141. Track 11 (post-event control) E_C−E_K = 0.371, CI [−0.042, 0.809] **includes zero**; "proxy contrast, PROVISIONAL"; never "beats baseline"; scorecard stays uninformative.
- **#162 opencode GLM — live bilingual bulletin** (`reports/bulletin_demo.md`): the LangGraph graph ran end to end (3 live searches → hazard agents → synthesis), ES/EN, every number traced to a tool evidence field, SI-Assisted badge, withheld fields render "not available" (contract-tested).
- **#163 opencode Kimi — hand_m on all AOIs + v2 release** (`reports/cache_release_v2.md`): `cache-2026-11-15-v2` staged under `dist/` (137 MB, verified, **not published**); the MCP tools verified serving the measured numbers (flood 4486.59 ha, landslide null, quake with `coherence_statistics` present post-freeze).

Jack's **#158** (measured flood-tool budget 0.5 s, latency runner) also merged.

## Science state (all PROVISIONAL)
- **La Mojana (headline):** open water measured per date; L-vs-C comparison quantifies what C-band misses; change classes degenerate (frozen-rule, #26).
- **Aburrá:** no motion above 9.105 mm (17 pairs) — double-calibrated (sign-flip null #109 + stable-pixel FP #155).
- **Quake:** damage proxy both tracks; scorecard uninformative; E_C−E_K reported with frozen K; C/K unsealed, depth 116 km displayed.

## Infrastructure / blockers
- **Hyperbolic endpoint is DOWN:** `api.hyperbolic.ai/inference/v1/models` → **HTTP 403 Forbidden** (key present, rejected; likely plan/decommission). Hyperbolic's documented host is usually `api.hyperbolic.xyz/v1` — the config may have the wrong domain. Use **featherless/zai-org/GLM-5.3** (known-good) or **nebius/moonshotai/Kimi-K3** for opencode until resolved. opencode configs are intact (`~/.config/opencode/opencode.json`): featherless, nebius, hyperbolic.
- **#141 (open):** the quake DPM **pipeline** still reads K from the gate catalog, not frozen `quake.pairs`. grok's interpretation (#161) sidestepped it by re-streaming frozen K, but the pipeline fix is still owed. Collision note: fix it when no quake agent is running.
- Disk was cleaned (12 GB free): 33 merged worktrees removed, uv cache pruned, dangling Docker layers gone. Demo image `sars-dance-medellin:2026` kept.
- Unmerged branch `feat/data-cache-release-restage` (opencode's parallel cache effort, uncommitted config/.env.example edits) — superseded by #163; reconcile or discard.

## Go-public gate (#46) — nearly clear
- ✅ Full-history secret scan green (#156): 20 findings, all false positives; no `.env`/secrets/keys in history.
- ✅ License set: **Apache-2.0** (#145), NOTICE, DATA_LICENSES.
- 🔴 Owner actions remaining: flip repo to **public**, publish the cache release (and make the GCS bucket public-read if used). Repo is **private** until then.

## Remaining critical path (Phase 5, tonight)
1. Record the video (#43) at D−6h from the locked storyboard (La Mojana headline); Spanish VO + English subtitles (#44, SRT done #125).
2. Finalize README/project page (#45) + AI disclosure.
3. Owner go-public: visibility flip + release publish (#46).
4. Optional: fix #141 (pipeline frozen-K); the demo image / `make pitch` dry-run (#40).

## Board hygiene (safe to close, work done)
#18, #29, #30–#37, #47, #60 are done-but-open — close with their PRs.
