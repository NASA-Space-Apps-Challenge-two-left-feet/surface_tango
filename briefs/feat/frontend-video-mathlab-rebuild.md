# Handoff: feat/frontend-video-mathlab-rebuild — rebuild the math-lab with the corrections (issue #56)

**Why it matters:** SaritaRpo's #41 is blocked because the Gemini math-lab never reached the repo. Issue #55 tries to import the original; **this task runs in parallel as the fallback** and builds a clean, corrected version. The team keeps whichever is better and deletes the other. To avoid colliding with #55, you build into **`static/mathlab-rebuild/`**, not `static/mathlab/`.

## Task
Build one static page, `static/mathlab-rebuild/index.html`: vanilla JS and `<canvas>`/SVG, optionally one plotting library from cdnjs.cloudflare.com pinned to an exact version. No build step, no framework, no backend. It has 5 modules, each with a title, a 2–4 line plain-language explanation, interactive sliders and a live plot:

1. **Wave penetration:** Rayleigh roughness criterion and Fresnel reflectivity for C (5.6 cm), S (9.4 cm), L (24 cm), with sliders for relative permittivity εr and RMS height. S-band is drawn but labelled **"not available over Colombia"**.
2. **InSAR phase to displacement:** d_LOS = −λΔφ/4π with λ = 0.24 m. Show the raw phase, subtraction of the **provided** ionosphere screen, removal of a stratified troposphere ramp, and projection onto downslope (slope and aspect sliders). A **noise-floor toggle** greys out any rate below the stable-pixel RMS and shows "no motion detected above X mm".
3. **Dual-pol scattering (HH/HV):** change detection. Open water: HH darkens (ΔHH < −5.5 dB). Flooded vegetation: HH brightens (ΔHH > +3 dB) with stable HV/HH (|Δ| < 1.5 dB). Thresholds are labelled "literature-typical, uncalibrated". Quad-pol H/ᾱ appears only as a greyed panel labelled **"quad-pol only, not used: Colombia is dual-pol"**.
4. **Coherence decorrelation:** γ = exp(−8π²σ²/λ²) for C and L band, with a σ slider (0–10 cm). Mark σ ≈ 2.7 cm where L-band γ = 1/e. Explain in one line why cracked masonry can stay coherent while rain or canopy lowers γ. **No GOFF / surface-rupture story** (the Aug 10 quake was 96 km deep).
5. **L+C band allometry:** educational extra; banner "not part of the analysis".

**Every module** shows the banner: *"Educational; illustrative physics, not measured results."* Never show numbers that look like findings (no hectares, no damage counts, no velocities of real places). No NASA logos or flags.

Sources for the formulas: `docs/designs/bailasar.md` (Hazards 1–3), `docs/kb/method-coherence-decorrelation.md`, `docs/kb/nisar-gunw-layers.md`, `config/preregistered.yaml` (flood thresholds: read the numbers there, do not invent others).

## Files you may touch
- `static/mathlab-rebuild/index.html` (new)
- `static/mathlab-rebuild/README.md` (new: what each module shows, its formulas with sources, and how to open it)
- this handoff (report section only)

Do **not** touch `static/mathlab/` (#55), `static/index.html` or `app.py`.

## Acceptance
- `make sync` first, then `make ci` green.
- Open the page in a browser: all 5 modules respond to their sliders, and the console shows no errors.
- The formulas in the code match the sources above (cite the file next to each formula in a code comment).
- `rg -n 'logo=nasa|meatball|@latest' static/mathlab-rebuild/` returns nothing.
- Commit with `feat(mathlab): rebuild the math-lab with dual-pol and decorrelation modules` and `Refs: #56, #41` in the body.

## Forbidden
No `git push`, `merge`, `checkout`, `switch`, `reset`, `rebase` (other than `make sync`), `stash`; no `gh`; no uploads; never print `.env`. No synthetic results. The orchestrator reviews the diff and pushes.

## Report (append below when done)
- Commit hash(es):
- `make ci` tail:
- Modules working (1–5) and a one-line check of each formula:
- Console errors (verbatim) or "none":
- Libraries and pinned versions:
- Open questions:
