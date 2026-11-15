# Surface Tango submission storyboard

## Locked cut for #39

**La Mojana, Colombia. NISAR mapped provisional absolute open water.** The hour-4 power check selected this headline and LEONOB2014 ratified it. The earthquake scorecard was uninformative because verified barrio damage labels were unavailable. See the [headline decision](../validation/README.md#power-check-and-headline-plan-02-03-25).

Use the **La Mojana floods** chapter in mission control. Keep **PROVISIONAL** visible over the radar evidence and outcome card. The headline uses 17 June. The staged Sentinel context is from 28 June, and the separate Sentinel-1 comparison is from 11 July. Keep those dates visible so each shot has a clear evidence source.

## Recording copy

Shot times are editing targets. The voice-over is **English, AI-generated** (no human voice; challenge requirement). Bracketed items are the frames to capture in #43.

| Time | Frame | Exact on-screen copy (English) | English AI voice-over |
|---|---|---|---|
| 0–4 s | [Record title and English bulletin] | La Mojana, Colombia · Open water mapped with NISAR | In La Mojana, we mapped open water with radar. |
| 4–10 s | [Record the synchronized curtain slider] | Sentinel-2 optical and Sentinel-1 C-band · 28 Jun 2026. NISAR L-band · 17 Jun 2026 · PROVISIONAL. | The Sentinel scenes give context. NISAR shows the open water. |
| 10–15 s | [Record the timeline scrub and June NISAR water mask] | 17 Jun 2026 · 4,487 ha (measured, rounded) · 5,539 of 197,758 valid pixels · PROVISIONAL. | NISAR mapped June open water. |
| 15–21 s | [Record a separate July comparison card] | 11 Jul 2026 · 3,351 of 4,946 NISAR open-water pixels with valid Sentinel-1, missed by the Sentinel-1 threshold (measured, uncalibrated threshold) · PROVISIONAL. | In July, the Sentinel-1 threshold missed some of the open water. |
| 21–27 s | [Record the outcome card] | Absolute open water · 2,799–6,726 ha (threshold sensitivity, measured, rounded) · Uncalibrated thresholds · No validated flood change · PROVISIONAL. | The range depends on the threshold. The dry reference cannot support a change estimate. |
| 27–30 s | [Record credits card] | Surface Tango · Two Left Feet · NISAR / ASF DAAC · Copernicus Sentinel-1/2 · SI-Assisted Analytics | — |

### In-app shot directions

- **Opening cue.** Keep the La Mojana title visible over the recorded bulletin for the last three seconds of the opening. Select the English tab before capture. Keep the ES/EN controls in frame to show bilingual support. Use English narration and overlays throughout. Frame the serving-model tag and **SI-Assisted Analytics** badge. Use the recorded panel from `/api/bulletin` and label it as recorded. Keep the La Mojana narration from the table.
- **June map cue.** Use the real timeline rail instead of a static hold. Use cuts between settled timeline states. Show 29 June at 10–11.5 s, 11 July at 11.5–13 s, and hold the 17 June headline mask at 13–15 s. Frame the date and measured pixel denominator on each cut. Apply the June headline overlay only on 17 June. The separate July comparison card still follows this cue.
- **Timeline evidence.** `/api/flood-series` reported 2,887 of 176,936 valid pixels on 29 June, 4,946 of 153,948 on 11 July, and 5,539 of 197,758 on 17 June (measured; [La Mojana report and granules](../reports/mojana.md#open-water-fraction-by-date)). The 153,948 July timeline pixels are the NISAR coverage denominator. The separate comparison card uses the 4,946 NISAR open-water pixels with finite Sentinel-1 VV.
- **Headline check.** `/api/pitch-facts` matches the locked June extent and sensitivity range and the separate July threshold comparison. The command and source granules are below.

The current still-frame assembler checks the timing but does not include the bulletin or timeline transitions. Both remain capture placeholders for #43.

The nominal value and sensitivity range are rounded on screen. The range describes how the measured extent varies with the uncalibrated thresholds. Use plain text credits and the SI disclosure card. Do not show logos or identifiable people.

## Evidence for the capture

| Claim or shot | Source and provenance |
|---|---|
| 17 June NISAR absolute open water | [La Mojana report, Absolute open water and Sensitivity](../reports/mojana.md). `uv run python -m gee_math.flood_polarimetric_math`, AOI `3_la_mojana_caregato`. GCOV granule `NISAR_L2_PR_GCOV_023_047_A_005_4005_DHDH_A_20260617T103906_20260617T103941_P05023_F_F_J_001`. Nominal 5,539 of 197,758 valid pixels. Sensitivity endpoints 3,455 and 8,304 positive pixels on the same date. |
| 11 July comparison card | [La Mojana report, Sentinel-1 comparison](../reports/mojana.md#sentinel-1-comparison), same command. GCOV granule `NISAR_L2_PR_GCOV_025_047_A_005_4005_DHDH_A_20260711T103905_20260711T103939_P05023_N_F_J_001`. Sentinel-1 IW GRD composite from 14 scenes within ±6 days, as documented in the report. Denominator 4,946 NISAR open-water pixels with finite Sentinel-1 VV. The miss count uses the report's uncalibrated comparison cut. |
| 28 June Sentinel curtain | `local_cache/mojana/tiles/manifest.json`, generated by `scripts/prestage_tiles.py --aoi mojana`. Use the manifest-selected least-cloudy Sentinel-2 mosaic and nearest-date Sentinel-1 IW GRD VV mosaic. Their scene IDs and selection rules are in the manifest. The curtain frames are context imagery, distinct from the July composite used to measure misses. |

## Capture handoff for #43

1. The [confirmed schedule](https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango/issues/29#issuecomment-6892769378) sets the deadline at 23:59 COT on 15 November 2026 and capture at 17:59 COT.
2. Follow the [story cache setup](../status/frontend-video.md) with the downloaded release manifest. Check that the flood timeline and recorded bulletin both load in the [offline walkthrough](https://github.com/NASA-Space-Apps-Challenge-two-left-feet/surface_tango/issues/40).
3. Record the title and bulletin, the curtain, and the measured timeline ending on the June water mask. Show the dated July comparison as its own card after the June map. Keep the valid Sentinel-1 denominator visible in the card or its evidence caption.
4. Record the outcome and credits, then check the 30-second cut for readable dates, units, denominators, caveats, and matching subtitles. Use this locked cut for the headline and evidence. Log the chosen takes in the [recording run sheet](recording-run-sheet.md#final-capture).
