"""Read the pitch numbers from the merged reports, never from hand-copied text.

The mission control panels, the story chapters and the draft video all show
numbers through ``load_pitch_facts``. Each fact keeps the report file, the
section anchor and the exact report line it was parsed from. A report that no
longer contains the expected line raises ``ReportFactError``: the caller shows
an error state instead of an old number.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOJANA = "reports/mojana.md"
ABURRA = "reports/aburra.md"
VALIDATION = "validation/README.md"

# The headline date and the separate Sentinel-1 comparison date are named by
# the locked storyboard (video/storyboard.md, #119); the values come from the report.
HEADLINE_DATE = "2026-06-17"
COMPARISON_DATE = "2026-07-11"


class ReportFactError(ValueError):
    """A report does not contain a line the pitch depends on."""


def _section(text: str, heading: str, source: str) -> str:
    match = re.search(rf"^(#+) {re.escape(heading)}\s*$", text, re.MULTILINE)
    if not match:
        raise ReportFactError(f"{source}: section '{heading}' not found")
    level = len(match.group(1))
    rest = text[match.end() :]
    end = re.search(rf"^#{{1,{level}}} ", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def _line(section: str, pattern: str, source: str) -> re.Match[str]:
    for line in section.splitlines():
        match = re.search(pattern, line)
        if match:
            return match
    raise ReportFactError(f"{source}: no line matches {pattern!r}")


def _thousands(value: str | int) -> str:
    return f"{int(value):,}"


def _rounded_ha(value: str) -> str:
    # Display rounding only; the exact value stays in the fact.
    return f"{round(float(value)):,}"


def _fact(value, text: str, source: str, anchor: str, line: re.Match[str]) -> dict:
    return {
        "value": value,
        "text": text,
        "source": f"{source}#{anchor}",
        "report_line": line.string.strip(),
        "kind": "measured",
    }


def mojana_facts(root: Path = ROOT) -> dict:
    text = (root / MOJANA).read_text(encoding="utf-8")
    reproduce = _section(text, "Reproduce", MOJANA)
    command = _line(reproduce, r"Command: `([^`]+)`", MOJANA).group(1)
    aoi = _line(reproduce, r"AOI source: (.+)$", MOJANA).group(1).strip()

    fractions = _section(text, "Open-water fraction by date", MOJANA)
    row = _line(
        fractions,
        rf"^\| {HEADLINE_DATE} \| (\S+) \| (\d+) \| (\d+) \| .*?(\d+) pixels, ([\d.]+) ha",
        MOJANA,
    )
    granule, water, valid, _, hectares = row.groups()
    comparison_row = _line(fractions, rf"^\| {COMPARISON_DATE} \| (\S+) \|", MOJANA)

    sensitivity = _section(text, HEADLINE_DATE, MOJANA)
    span = _line(
        sensitivity,
        r"Absolute water range: ([\d.]+) to ([\d.]+) ha \(pixel counts (\d+) at \S+ to (\d+) at",
        MOJANA,
    )
    low_ha, high_ha, low_px, high_px = span.groups()

    s1 = _section(text, f"{COMPARISON_DATE} — absolute_water", MOJANA)
    scenes = _line(s1, r"S1 scenes in the window: (\d+)", MOJANA)
    missed = _line(
        s1, r"Missed by the S1 mask: (\d+) pixels, denominator (\d+) positive pixels", MOJANA
    )

    return {
        "date": HEADLINE_DATE,
        "granule": granule,
        "command": command,
        "aoi": aoi,
        "water_pixels": _fact(
            int(water),
            f"{_thousands(water)} of {_thousands(valid)} valid pixels",
            MOJANA,
            "open-water-fraction-by-date",
            row,
        ),
        "valid_pixels": int(valid),
        "open_water_ha": _fact(
            float(hectares),
            f"{_rounded_ha(hectares)} ha",
            MOJANA,
            "open-water-fraction-by-date",
            row,
        ),
        "sensitivity_ha": _fact(
            [float(low_ha), float(high_ha)],
            f"{_rounded_ha(low_ha)}–{_rounded_ha(high_ha)} ha",
            MOJANA,
            HEADLINE_DATE,
            span,
        ),
        "sensitivity_pixels": [int(low_px), int(high_px)],
        "s1_comparison": _fact(
            [int(missed.group(1)), int(missed.group(2))],
            f"{_thousands(missed.group(1))} of {_thousands(missed.group(2))} NISAR open-water "
            "pixels with valid Sentinel-1 data missed by the Sentinel-1 cut",
            MOJANA,
            "sentinel-1-comparison",
            missed,
        ),
        "s1_comparison_date": COMPARISON_DATE,
        "s1_comparison_granule": comparison_row.group(1),
        "s1_scenes": int(scenes.group(1)),
        "provisional": "PROVISIONAL" in text,
        "uncalibrated": "uncalibrated" in text,
    }


def aburra_facts(root: Path = ROOT) -> dict:
    text = (root / ABURRA).read_text(encoding="utf-8")
    verdict = _section(text, "Verdict", ABURRA)
    line = _line(verdict, r"No motion detected above ([\d.]+) mm \((\d+) pairs\)", ABURRA)
    command = _line(verdict, r"Command: `([^`]+)`", ABURRA).group(1)
    table = verdict.splitlines()
    header = next((row for row in table if row.startswith("| Stack |")), None)
    if header is None:
        raise ReportFactError(f"{ABURRA}: per-track null table is missing")
    columns = [cell.strip() for cell in header.split("|")[1:-1]]
    try:
        null_column = columns.index("Exceeds sign-flip null")
    except ValueError as error:
        raise ReportFactError(f"{ABURRA}: sign-flip null column is missing") from error
    exceeds = []
    for row in table:
        if not row.lower().startswith("| track "):
            continue
        cells = [cell.strip() for cell in row.split("|")[1:-1]]
        if len(cells) != len(columns) or cells[null_column] not in {"yes", "no"}:
            raise ReportFactError(f"{ABURRA}: invalid per-track null row")
        exceeds.append(cells[null_column])
    if not exceeds:
        raise ReportFactError(f"{ABURRA}: no per-track null rows found")
    return {
        "noise_floor_mm": _fact(
            float(line.group(1)),
            f"{line.group(1)} mm",
            ABURRA,
            "verdict",
            line,
        ),
        "pairs": int(line.group(2)),
        "exceeds_null": any(value == "yes" for value in exceeds),
        "command": command,
        "provisional": "PROVISIONAL" in text,
    }


def quake_facts(root: Path = ROOT) -> dict:
    text = (root / VALIDATION).read_text(encoding="utf-8")
    power = _section(text, "Power check and headline (plan 02-03, #25)", VALIDATION)
    line = _line(power, r"there are (\d+) evaluable units", VALIDATION)
    return {
        "scorecard": "uninformative" if "uninformative" in power else "pending",
        "evaluable_units": _fact(
            int(line.group(1)),
            f"{line.group(1)} evaluable units",
            VALIDATION,
            "power-check-and-headline-plan-02-03-25",
            line,
        ),
        "headline_is_flood": "Headline decision → La Mojana flood" in power,
    }


def load_pitch_facts(root: Path = ROOT) -> dict:
    """All on-screen numbers for the pitch, parsed from the merged reports."""
    return {
        "flood": mojana_facts(root),
        "landslide": aburra_facts(root),
        "earthquake": quake_facts(root),
    }


def render(template: str, facts: dict) -> str:
    """Fill ``{chapter.key}`` placeholders with each fact's display text."""

    def value(match: re.Match[str]) -> str:
        node = facts
        for key in match.group(1).split("."):
            if not isinstance(node, dict) or key not in node:
                raise ReportFactError(f"unknown placeholder {match.group(0)}")
            node = node[key]
        return node["text"] if isinstance(node, dict) else str(node)

    return re.sub(r"\{([a-z_]+(?:\.[a-z0-9_]+)+)\}", value, template)
