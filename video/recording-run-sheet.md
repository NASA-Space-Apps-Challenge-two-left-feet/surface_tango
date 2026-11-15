# Mission control recording run sheet

## Capture inputs

| Input | Confirmed handoff |
|---|---|
| Official deadline D and capture start D−6 h in Bogotá | Pending [#29](https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango/issues/29). |
| Headline | La Mojana absolute open water, ratified in the [hour-4 decision](../validation/README.md#power-check-and-headline-plan-02-03-25). |
| Measured outcome and separate Sentinel-1 comparison | [La Mojana report](../reports/mojana.md). Use the dates, denominators, and caveats in the [locked storyboard](storyboard.md). |
| Mission control | Record from `main` with the merged story map and evidence gate. The rehearsal used `1d1d2a4`. |
| Cache and display | Draft release `cache-2026-11-15`. Assemble the cache, then follow the [story cache setup](../status/frontend-video.md) with the downloaded release manifest. |
| Offline walkthrough | The frontend rehearsal ran with external browser requests blocked. The full `make pitch` walkthrough is tracked in [#40](https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango/issues/40). |
| Voice-over | English, AI-generated (no human voice; challenge requirement). Script = the storyboard's English VO column; audio muxed in #44. The English SRT cue file remains a timing reference. |

## Local review cut

- Playwright captured the localhost browser page at 1920×1080. FFmpeg encoded the clip at 30 fps. These are capture settings.
- The local review export is `dist/recording-qa/la-mojana-review-cut.mp4`. It contains the six locked storyboard cues and the timed English subtitle track. FFprobe verified the 30-second export. The AI-generated English voice-over remains the #44 editor handoff.
- The source curtain sweep remains at `dist/recording-qa/la-mojana-rehearsal.mp4`.
- The browser loaded the La Mojana Sentinel panels and NISAR open-water mask from the verified cache with external requests blocked. Keep **PROVISIONAL** visible beside the measured water result.

## Final capture

Deadline in Bogotá: [#29 pending]. Full offline walkthrough: [#40 pending].

1. Once the deadline and offline walkthrough are confirmed, start mission control with the shared cache in pitch mode. Select **La Mojana floods** and capture the browser page without desktop notifications or browser chrome.
2. Set the recorder to 1920×1080 at 30 fps. Sweep the synchronized curtain across the same area. Keep the two Sentinel acquisition dates and the NISAR measurement date visible.
3. Capture the June open-water mask, the separate July threshold-comparison card, and the outcome and credits cards as directed in the storyboard. Keep the denominators and the uncalibrated-threshold caveat visible where specified.
4. Review the exported takes for alignment, readability, and correct evidence. Hand the takes to the editor for the AI-generated English voice-over mux and final cut.

| Shot | Final take |
|---|---|
| Title | [Pending final capture] |
| Bulletin panel (NEW) | The left bulletin box now opens on the recorded live-run ES/EN bulletin with the serving-model tag and the SI-Assisted badge — no scan needed. Hold 3 s. |
| Curtain slider | [Pending final capture] |
| June open-water map | [Pending final capture] |
| Flood timeline scrub (NEW) | Click through 3–4 measured dates on the timeline rail at the bottom of the flood chapter; the mask and pixel denominators update on each click. |
| July Sentinel-1 comparison | [Pending final capture] |
| Outcome | [Pending final capture] |
| Credits | [Pending final capture] |

## Capture inputs updated for the merged UI (2026-11-15, #166)

- The deadline D is 2026-11-15 23:59 COT (record at D−6 h = 17:59).
- Two new must-shots: the bulletin panel with its serving-model tag, and the
  flood timeline scrub. The quake panel no longer claims "sealed" — the state
  derives from the cache manifest (frozen pre-registration).
- Everything serves offline from the cache; verify with the #40 walkthrough
  (network blocked) before recording.
