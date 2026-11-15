# Living knowledge base

One short note per fact or method the code, the UI or the pitch relies on. Rules: `AGENTS.md` → "Living knowledge base".

- Name: `<topic>-<slug>.md` from `TEMPLATE.md`. Topics: `nisar`, `event`, `data`, `method`, `threshold`, `tooling`.
- `status: unverified` until someone reads the **primary** source and pastes a verbatim quote (≤ 25 words).
  AI summaries and search snippets never count as verification.
- Never edit a verified claim: add a new note with `supersedes:` and mark the old one `superseded`.
- A PR that adds or changes a method, threshold or data source updates its note in the same PR.
- Sync to gbrain after merges (`/sync-gbrain`) so every agent session can search it.

| Note | Status |
|---|---|
| [nisar-public-record](nisar-public-record.md) | superseded |
| [nisar-public-record-v2](nisar-public-record-v2.md) | verified |
| [nisar-gunw-layers](nisar-gunw-layers.md) | verified |
| [nisar-polarization-colombia](nisar-polarization-colombia.md) | unverified |
| [nisar-sband-colombia](nisar-sband-colombia.md) | unverified |
| [event-2026-08-10-earthquake](event-2026-08-10-earthquake.md) | verified (USGS preferred-origin depth estimate 116.13 km; supersedes the depth claim of event-usgs-verified-display-fields) |
| [event-2026-08-10-earthquake-sgc](event-2026-08-10-earthquake-sgc.md) | verified (SGC manual bulletin depth 105 km) |
| [event-2026-08-10-earthquake-v2](event-2026-08-10-earthquake-v2.md) | superseded |
| [event-2025-06-24-granizal](event-2025-06-24-granizal.md) | verified |
| [method-coherence-decorrelation](method-coherence-decorrelation.md) | unverified |

- [USGS verified display fields v2](event-usgs-verified-display-fields-v2.md): displayable event fields including depth 116 km (USGS estimate, rounded from 116.13 km); supersedes [event-usgs-verified-display-fields](event-usgs-verified-display-fields.md) (superseded, depth withheld).
