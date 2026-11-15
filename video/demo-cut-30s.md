# Opinionated 30-second demo cut

Proposed narration and navigation for the Space Apps "Dancing with the SARs" demo.
This file does not replace the locked La Mojana storyboard in `video/storyboard.md`.
Every number below is already in a report. The voice-over does not add people, dollars, or lives saved.

Pace: about 74 spoken words, one ElevenLabs take, English, no human voice.
Picture is a capture of mission control, not a drawn interface. A generated GIF of a fake screen would invent the evidence.

## What this cut is for

Judges have 30 seconds. The ratified headline stays La Mojana open water. The other two hazards exist so the demo can show three different products from one observatory: a landslide warning light, a flood extent plus a help list, and an earthquake window that refuses a fatality color. The social-good claim is the refusal. A card that will not size aid is the thing a responder can trust.

## ElevenLabs script

Paste as one take. The slash marks are breaths, not words.

```
Colombia. Three disasters. The clouds close the optical map. /
Sentinel sets the scene. NISAR L-band sees through it. /
La Mojana, seventeen June. Four thousand, four hundred eighty-seven hectares of open water. Provisional. Not people flooded. /
The flood card measures that water, and it will not invent the aid. /
Aburrá's light says monitor. No motion above the noise floor. Not a clearance. /
The quake gets no fatality color. We dispatch only what we measured.
```

Word count, breaths excluded: 9 + 9 + 17 + 13 + 13 + 12 = 73. At a clear ElevenLabs pace that is about 30 seconds, with the breaths taking the rest.

## Picture, locked to the words

Capture at 1920×1080, 30 fps, from the pitch-mode app with the network blocked. One camera. Chapter changes use the existing two-feet walk. Zooms are `fitBounds` on the data footprint, so the frame never jumps to an empty AOI box. Highlights are a ring on the live card, drawn in the page, not burned in as a fake number.

| Seconds | Words landing | Navigation | What must be readable |
|---|---|---|---|
| 0.0–3.5 | Three disasters. Clouds close the optical map. | Hold the story panel. Zoom out enough to see the AOI list. Ring the three chips: Open water, Monitor, Analyzed window. | No death toll. No dollar figure. |
| 3.5–8.0 | Sentinel sets the scene. NISAR L-band sees through it. | Sweep the curtain from the optical panel through C-band to L-band. End with the L-band panel dominant. | Dates stay distinct. Sentinel context is 28 June 2026. NISAR headline is 17 June 2026. The word PROVISIONAL stays on the L-band label. |
| 8.0–15.0 | 4,487 hectares. 17 June. Provisional. Not people flooded. | Select La Mojana. Fit the footprint. Scrub the flood timeline and hold 17 June. Ring the extent line. | 5,539 of 197,758 valid pixels. Granule `NISAR_L2_PR_GCOV_023_047_A_005_4005_DHDH_A_20260617T103906_20260617T103941_P05023_F_F_J_001`. Source: `reports/mojana.md`, command `uv run python -m gee_math.flood_polarimetric_math`. |
| 15.0–20.0 | The flood card will not invent the aid. | Same AOI. Scroll the story panel just enough to open Help to check. Ring Drinking water, Access, Shelter, Search. | Each line says the quantity is unavailable. Damage level stays "not classified". |
| 20.0–25.5 | Aburrá. Monitor. Not a clearance. | Two-feet transition into the landslide chapter. Fit Aburrá. The only traffic light in the film. The Monitor lamp is on. The other three lamps are dim. | "Not a safety clearance." No hectare claim. |
| 25.5–28.5 | No fatality color. | Transition to the earthquake chapter. Fit Eje Cafetero. Ring "Analyzed window, not affected area." | No red/orange/yellow/green PAGER paint. Pixel counts stay pixels. |
| 28.5–30.0 | We dispatch only what we measured. | Cut to the credits card already specified in the locked storyboard. | Surface Tango. Two Left Feet. NISAR / ASF DAAC. Copernicus Sentinel-1/2. SI-Assisted Analytics. No agency logo. |

## What we do not say

Population, buildings, dollars, tons of aid, and lives saved are not on the envelopes. The demo says they are unavailable. Sentinel-1's separate July comparison (3,351 of 4,946 NISAR open-water pixels missed on an uncalibrated cut, median miss fraction 0.64 across ten dates, measured) stays in the locked storyboard. It does not fit this 30-second spoken cut without dropping a hazard. If the recording runs long, drop the quake sentence before dropping the Mojana denominator.

## GIF

Assemble the captured frames, not a model drawing.

```bash
# After the 1920x1080 capture exists as video/raw/demo-30s.mp4
# Homebrew ffmpeg has no drawtext. Use the Anaconda build.
PATH="/opt/anaconda3/bin:$PATH" ffmpeg -y -i video/raw/demo-30s.mp4 \
  -vf "fps=12,scale=960:-1:flags=lanczos" -loop 0 video/demo-30s.gif
```

The GIF is a playback of that capture at 12 fps so it stays small enough to attach. It is in sync only if the ElevenLabs take is muxed first and the GIF is exported from the muxed file. Do not generate a second animation that redraws the maps.

## Beneficiaries, said without a fake count

La Mojana / Caregato, the Aburrá Valley, and the Eje Cafetero and Chocó communities are the places on the map. The platform does not currently know how many people live there. The benefit it can quantify today is the measured open-water extent, with its denominator, and the explicit empty cells for aid.
