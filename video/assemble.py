"""Render the silent 30-second draft cut from the locked storyboard.

Shot timings come from the "Recording copy" table in ``video/storyboard.md``.
Every number on a card is parsed from the merged reports by
``video/report_facts.py`` and shown with its report source. Map shots use
staged screenshots from ``video/raw/`` (git-ignored); a missing screenshot
renders a plain "frame not staged" slate, never a stand-in image. Each shot
carries a voice-over placeholder tag; the voice-over is added at recording (#43).

    uv run python video/assemble.py            # -> video/draft_cut.mp4 (git-ignored)
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from video.report_facts import load_pitch_facts  # noqa: E402

STORYBOARD = ROOT / "video" / "storyboard.md"
RAW = ROOT / "video" / "raw"
OUTPUT = ROOT / "video" / "draft_cut.mp4"
WIDTH, HEIGHT, FPS = 1920, 1080, 30
BACKGROUND = "0x090d16"
FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
]


@dataclass(frozen=True)
class Shot:
    start: float
    end: float
    frame: str
    copy: str

    @property
    def seconds(self) -> float:
        return self.end - self.start


def read_shots(storyboard: Path = STORYBOARD) -> list[Shot]:
    """Parse the storyboard's recording table into timed shots."""
    text = storyboard.read_text(encoding="utf-8")
    start = text.index("## Recording copy")
    end = text.find("\n## ", start + 1)
    shots = []
    for line in text[start : end if end != -1 else None].splitlines():
        match = re.match(r"^\| (\d+)[–-](\d+) s \| \[([^\]]+)\] \| ([^|]+) \|", line)
        if match:
            shots.append(
                Shot(
                    float(match.group(1)),
                    float(match.group(2)),
                    match.group(3).strip(),
                    match.group(4).strip(),
                )
            )
    if not shots:
        raise ValueError(f"{storyboard}: no timed shots in 'Recording copy'")
    for previous, current in zip(shots, shots[1:], strict=False):
        if previous.end != current.start:
            raise ValueError(f"{storyboard}: gap or overlap at {previous.end} s")
    return shots


def shot_cards(shots: list[Shot], facts: dict) -> list[dict]:
    """Pair each storyboard shot with its staged frame and its report-sourced text."""
    flood = facts["flood"]
    provisional = (
        "PROVISIONAL · uncalibrated thresholds" if flood["uncalibrated"] else "PROVISIONAL"
    )
    plans = [
        {"title": shots[0].copy, "lines": [], "sources": []},
        {
            "frame": "curtain.png",
            "title": "Sentinel-2 / Sentinel-1 context · NISAR L-band",
            "lines": [f"NISAR {flood['date']} · {provisional}"],
            "sources": [f"local_cache/mojana/tiles/manifest.json · {flood['granule']}"],
        },
        {
            "frame": "water_mask.png",
            "title": f"NISAR open water · {flood['date']}",
            "lines": [
                f"{flood['open_water_ha']['text']} (measured, rounded)",
                f"{flood['water_pixels']['text']}",
                provisional,
            ],
            "sources": [flood["open_water_ha"]["source"], flood["granule"]],
        },
        {
            "title": f"Sentinel-1 comparison · {flood['s1_comparison_date']}",
            "lines": [
                f"{flood['s1_comparison']['text']} (measured, uncalibrated cut)",
                f"{flood['s1_scenes']} Sentinel-1 scenes in the window",
                provisional,
            ],
            "sources": [flood["s1_comparison"]["source"], flood["s1_comparison_granule"]],
        },
        {
            "title": "Absolute open water · threshold sensitivity",
            "lines": [
                f"{flood['sensitivity_ha']['text']} on {flood['date']} (measured, rounded)",
                "No validated flood-change estimate (degenerate dry reference)",
                provisional,
            ],
            "sources": [flood["sensitivity_ha"]["source"]],
        },
        {"title": shots[-1].copy, "lines": [], "sources": []},
    ]
    if len(plans) != len(shots):
        raise ValueError(f"storyboard has {len(shots)} shots; the draft maps {len(plans)}")
    for index, (shot, plan) in enumerate(zip(shots, plans, strict=True), 1):
        plan["shot"] = shot
        plan["vo"] = f"VO placeholder · shot {index} · {shot.start:g}–{shot.end:g} s"
    return plans


def _font(explicit: Path | None) -> Path:
    for candidate in [explicit, *FONT_CANDIDATES]:
        if candidate and candidate.is_file():
            return candidate
    raise FileNotFoundError("No font found; pass --font <path to a .ttf>")


def _wrap(lines: list[str], width: int) -> str:
    return "\n".join(textwrap.fill(line, width) for line in lines if line)


def _segment(card: dict, index: int, work: Path, ffmpeg: str) -> Path:
    shot = card["shot"]
    texts = {
        "title": _wrap([card["title"]], 60),
        "body": _wrap(card["lines"], 70),
        "source": _wrap([f"Source: {s}" for s in card["sources"]], 120),
        "vo": card["vo"],
        "slate": " ",
    }
    frame = RAW / card["frame"] if card.get("frame") else None
    if frame is not None and not frame.is_file():
        # A plain slate, never a stand-in image: the shot is recorded at #43.
        texts["slate"] = f"Frame not staged: video/raw/{card['frame']}"
        frame = None
    for name, value in texts.items():
        # newline="\n": drawtext renders a Windows "\r" as an extra blank line.
        (work / f"{index}_{name}.txt").write_text(value or " ", encoding="utf-8", newline="\n")

    title_lines = texts["title"].count("\n") + 1
    body_lines = texts["body"].count("\n") + 1 if texts["body"] else 0
    source_lines = texts["source"].count("\n") + 1 if texts["source"] else 0
    # Rendered line heights: title 54 px + 12, body 38 px + 18, source 22 px + 12.
    block = title_lines * 66 + 24 + body_lines * 56
    source_top = HEIGHT - 40 - source_lines * 34
    if frame is not None:
        inputs = ["-loop", "1", "-framerate", str(FPS), "-i", str(frame)]
        band = block + source_lines * 34 + 100
        base = (
            f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color={BACKGROUND},setsar=1,"
            f"drawbox=x=0:y=ih-{band}:w=iw:h={band}:color=black@0.72:t=fill"
        )
        top = HEIGHT - band + 20
    else:
        inputs = ["-f", "lavfi", "-i", f"color=c={BACKGROUND}:s={WIDTH}x{HEIGHT}:r={FPS}"]
        base = "[0:v]setsar=1"
        top = (HEIGHT - block) // 2 - 60

    draw = "drawtext=fontfile=font.ttf:textfile={file}:fontcolor={color}:fontsize={size}:x={x}:y={y}:line_spacing=10"
    chain = ",".join(
        [
            base,
            draw.format(file=f"{index}_title.txt", color="0x38bdf8", size=54, x="80", y=str(top)),
            draw.format(
                file=f"{index}_body.txt",
                color="white",
                size=38,
                x="80",
                y=str(top + title_lines * 66 + 24),
            ),
            draw.format(file=f"{index}_slate.txt", color="0xfbbf24", size=30, x="80", y="40"),
            draw.format(
                file=f"{index}_source.txt", color="0x94a3b8", size=22, x="80", y=str(source_top)
            ),
            draw.format(file=f"{index}_vo.txt", color="0xfbbf24", size=24, x="w-tw-40", y="80")
            + ":box=1:boxcolor=black@0.8:boxborderw=10",
        ]
    )
    segment = work / f"segment_{index}.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            *inputs,
            "-filter_complex",
            f"{chain}[v]",
            "-map",
            "[v]",
            "-t",
            f"{shot.seconds:g}",
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            segment.name,
        ],
        cwd=work,
        check=True,
    )
    return segment


def assemble(output: Path = OUTPUT, font: Path | None = None) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FileNotFoundError("ffmpeg is not on PATH")
    shots = read_shots()
    total = shots[-1].end - shots[0].start
    if total != 30:
        raise ValueError(f"storyboard runs {total:g} s, expected 30 s")
    cards = shot_cards(shots, load_pitch_facts())
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copyfile(_font(font), work / "font.ttf")
        segments = [_segment(card, index, work, ffmpeg) for index, card in enumerate(cards)]
        (work / "segments.txt").write_text(
            "".join(f"file '{segment.name}'\n" for segment in segments), encoding="utf-8"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        # Concat recipe; a silent stereo track keeps the VO mux at #43 a plain stream copy.
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                "segments.txt",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=48000:cl=stereo",
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-t",
                f"{total:g}",
                str(output.resolve()),
            ],
            cwd=work,
            check=True,
        )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--font", type=Path, default=None)
    args = parser.parse_args()
    print(assemble(args.output, args.font))
