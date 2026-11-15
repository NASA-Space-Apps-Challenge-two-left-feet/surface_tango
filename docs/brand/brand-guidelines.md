# two left feet — brand guidelines (digest)

Source: `two-left-feet-brand-guidelines.pdf` (approved 2026-11-12; the original
lives in the team drive — it exceeds the repo's 1 MB large-file guard, so this
digest carries the operative rules verbatim in structure).

## Name

Always lowercase, three words: **two left feet**. The joke: NISAR carries two
radars ("two"), both look left of the satellite path ("left"), and the ground
a radar lights up is its footprint ("feet").

## Symbol

Two identical **left** footprints (oval 76×140 tilted 8° clockwise + 48-diameter
heel, heel centre 106 below and 12 right of the oval's centre); the second is
an exact copy moved 114 right and 40 up — a step. Both feet are left feet (heel
toward the right edge); the second foot is always a step ahead; the feet never
touch or mirror.

## Palette

| Colour | Hex | Role |
|---|---|---|
| Blue | `#1B3FD6` | The first pass. Primary buttons, links, the "before" in any comparison. |
| Vermilion | `#F04A23` | The second pass. Highlights, detected change, the "after". |
| Ink | `#121212` | Text, wordmark, dark backgrounds. |
| Paper | `#FFFFFF` | Default background. |
| Grey | `#5A5A5A` | Captions and secondary text only. |

Approved combinations: Paper/Blue/Vermilion/Ink · Ink/White/Vermilion/White ·
Blue/White/White · Vermilion/Ink/Ink. Mostly paper or mostly ink; blue and
vermilion are accents and vermilion is the rarer. Flat colours only — no tints,
gradients or transparency. **Never blue on ink.** Vermilion is not small text
on white (contrast 3.7:1). **Scientific colour scales stay scientific** — brand
colours go on frames, labels and annotations, never on the data.

## Typography

- **Jost** 600 (wordmark, headings, titles, buttons) / 500 (labels, interface).
- **Libre Caslon Text** regular/italic for prose.
- Fallbacks: Poppins, then system sans-serif; Georgia for Caslon.
- Small labels: Jost medium, uppercase, letter-spaced 0.14 em, grey.
- Code and data values: system monospace. No third brand typeface.
- Body ≥16 px, line height ~1.5; slide text ≥28 px at 1080p.

## Voice

Plain, short sentences, one dry joke at most — always about our dancing,
never the work. State the result first, then how it was measured. Numbers with
units and dates. Taglines: "can't dance. can measure." · "Two left feet, and
never out of step." · "Two radars. Both look left. We call that a footprint."

## Motion motif (platform)

The loading/transition animation dances the **authentic tango basic** — the
five-step figure counted **slow-slow-quick-quick-slow** (T-A-N-G-O), eight
beats: *1 forward (slow, long) · 2 forward (slow, long) · 3 forward (quick,
smaller) · 4 side (quick) · 5 close (slow)*. What makes it read as tango is the
**amplitude**: the first two forward steps are long strides along the line of
dance, then the figure tightens into a small side-step and a close — the steps
shrink. It is not an even march, and it is not a pair marking time in place.

One foot per colour so each foot leaves **its own trace**: vermilion dances
steps 1, 3, 5 and blue dances steps 2, 4 (the two radars / passes). Each print
plants bright with a heel-lead roll, then decays to a faint trace as the figure
moves on, so the whole basic stays legible in the footfalls. The prints are
always left feet, never mirrored, never leveled, a clear step apart, never
touching and **never cut** (generous stage, `overflow: visible`, checked at the
step-1 and step-5 extremes). Phrase ~3.2 s. Use it for the homepage intro,
loading states and chapter transitions; respect `prefers-reduced-motion` (feet
rest, no animation).

One shared glyph (`#lfoot`), placed and angled per step by a static
`<g transform>` (step 4 toes out, the side step); CSS animates only the plant
(`trail-step` keyframes, class `trail-foot`, slot classes `s1`–`s5` carrying
the S-S-Q-Q-S delays) in `static/index.html`. On the vermilion run button the
figure goes white (class `mono`). The chapter-transition curtain reuses the
same figure (`playFeetTransition` in `static/story-map.js`). "Two left feet,
one coordinated surface tango."
