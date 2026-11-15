# Video draft cut

`video/assemble.py` renders a **silent** 30-second draft (1920×1080, 30 fps, H.264 with a silent AAC track) of the locked La Mojana storyboard. The English voice-over is AI-generated (no human voice; challenge requirement) and muxed in #44. Every voice-over slot shows a `VO placeholder` tag.

## Run

```bash
uv run python video/assemble.py            # writes video/draft_cut.mp4 (git-ignored)
uv run python video/assemble.py --font /path/to/font.ttf   # if no system font is found
```

Needs `ffmpeg` on `PATH`. No network.

## Inputs

- **Timings:** the "Recording copy" table in [`storyboard.md`](storyboard.md). The script stops if the shots leave a gap or don't add up to 30 s.
- **Numbers:** [`report_facts.py`](report_facts.py) parses them from `reports/mojana.md`, `reports/aburra.md` and `validation/README.md`. Each card shows the report section and granule it came from. Nothing is copied by hand. If a report line changes shape, the script stops instead of showing an old number.
- **Map frames** (git-ignored, in `video/raw/`): `curtain.png` and `water_mask.png`, 1920×1080 screenshots of the offline La Mojana chapter. If a frame is missing, that shot renders a plain "Frame not staged" slate, not a stand-in image.

Capture the frames from the offline app (`OFFLINE_DEMO_MODE=1 uv run uvicorn app:app --port 8000`):

- `http://localhost:8000/?chapter=flood&split=32,66` → `curtain.png` (three-panel curtain)
- `http://localhost:8000/?chapter=flood&split=4,8` → `water_mask.png` (NISAR mask across the frame)

`?split=a,b` sets the curtain positions in percent; `?chapter=` opens a story chapter (`live` keeps mission control).

## Rules

- Only `.py` and `.md` files here are committed. Renders (`*.mp4`, `*.mov`) and `video/raw/` are ignored.
- Keep **PROVISIONAL** and "uncalibrated" visible on every number card.
- No logos, flags or agency identifiers in any frame. No identifiable people. Credits stay plain text with the SI-Assisted Analytics card.
