"""Draw the Surface Tango data zones as an animated SVG: a three-zone lakehouse on a laptop.

Bronze is the per-AOI manifest.json (per-band granule IDs or an honest 'missing', built
2026-11-14 and never rewritten after); silver is the curated cache (Zarr cube, COGs, tiles,
pairs) with its measured sizes; gold is the measured reports and the UI panels. The freeze
lane (hour-2 gate, pre-registration, event constants) sits between the sources and the
manifests. Red dashed marks are recorded gaps that were deliberately left missing;
grey dashed lanes are results still under review on their branches. Pipeline dashes animate
via CSS keyframes inside the file; `prefers-reduced-motion` stops them.

    uv run python scripts/diagrams/lakehouse.py   # writes docs/diagrams/lakehouse.svg
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import cast

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "diagrams" / "lakehouse.svg"
FONT = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"
W, H = 1520, 980

# Measured. Sources: reports/gate.md (hour-2 gate, 251 granules), cache manifests 2026-11-14
# (eje 45 MB/15 bands, aburra 36/16, mojana 30/16), `du -sh local_cache` (quake 291 MB),
# reports/aburra.md on its branch (noise floor 9.105 mm, 17 pairs, provisional).
GATE = {"gunw": 107, "gcov": 130, "goff": 14, "crid": "P05023", "total": 251}
AOIS = [
    ("eje_cafetero", "45 MB · 15 bands · cube + COGs", True),
    ("aburra", "36 MB · 16 bands · + tiles/ S1+S2", True),
    ("mojana", "30 MB · 16 bands · dual-pol HH/HV", True),
    ("quake", "291 MB on disk · track 11 triplets", False),
]
BUCKET = "bailasar-cache-472605"

FLOW = {
    "pipeline": ("#2563EB", "build pipeline · measured 2026-11-14"),
    "publish": ("#16A34A", "public release lane"),
    "control": ("#64748B", "provenance → evidence"),
}

INK, MUTED, EDGE = "#0F172A", "#64748B", "#CBD5E1"


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def halo(
    x: float, y: float, text: str, colour: str, size: float = 10, anchor: str = "middle"
) -> str:
    return (
        f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" text-anchor="{anchor}" fill="{colour}" '
        f'stroke="#FFFFFF" stroke-width="4" paint-order="stroke" stroke-linejoin="round">'
        f"{esc(text)}</text>"
    )


def glyph(kind: str, x: float, y: float) -> str:
    if kind == "doc":
        return (
            f'<path d="M{x + 3} {y + 1} h7 l4 4 v13 h-11 z" fill="none" stroke="{MUTED}" '
            f'stroke-width="1.8"/><path d="M{x + 6} {y + 8} h5 M{x + 6} {y + 12} h5" '
            f'stroke="{MUTED}" stroke-width="1.5"/>'
        )
    if kind == "sat":
        return (
            f'<rect x="{x + 3}" y="{y + 8}" width="10" height="10" rx="2" fill="#2563EB"/>'
            f'<path d="M{x + 8} {y + 7} a6 6 0 0 1 6 -6" fill="none" stroke="#2563EB" '
            'stroke-width="2"/>'
        )
    if kind == "layers":
        return (
            f'<rect x="{x}" y="{y + 2}" width="16" height="5" rx="2" fill="#059669"/>'
            f'<rect x="{x + 2}" y="{y + 9}" width="12" height="5" rx="2" fill="#34D399"/>'
            f'<rect x="{x + 4}" y="{y + 16}" width="8" height="5" rx="2" fill="#A7F3D0"/>'
        )
    if kind == "cyl":
        return (
            f'<ellipse cx="{x + 8}" cy="{y + 4}" rx="6" ry="2.5" fill="none" stroke="#B45309" '
            f'stroke-width="1.6"/><path d="M{x + 2} {y + 4} v10 a6 2.5 0 0 0 12 0 v-10" '
            'fill="none" stroke="#B45309" stroke-width="1.6"/>'
        )
    if kind == "star":
        return (
            f'<path d="M{x + 8} {y + 1} l2 4.5 5 .7 -3.6 3.5 .9 5 -4.3 -2.3 -4.3 2.3 '
            '.9 -5 -3.6 -3.5 5 -.7 z" fill="#CA8A04"/>'
        )
    if kind == "flag":
        return (
            f'<path d="M{x + 4} {y + 1} v16 M{x + 4} {y + 2} h10 l-3 3 3 3 h-10" '
            'fill="none" stroke="#DC2626" stroke-width="1.8"/>'
        )
    return f'<path d="M{x + 2} {y + 14} a6 6 0 1 1 -0.1 0 z" fill="{MUTED}"/>'


def zone(x: float, y: float, w: float, h: float, label: str, icon: str | None, style: str) -> str:
    stroke, fill = {
        "sources": ("#38BDF8", "#F0F9FF"),
        "freeze": ("#94A3B8", "#F8FAFC"),
        "bronze": ("#D6A26B", "#FBF3E8"),
        "silver": ("#94A3B8", "#F1F5F9"),
        "gold": ("#EAB308", "#FEFCE8"),
        "release": ("#86EFAC", "#F7FEF9"),
    }[style]
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="1.4"/>'
    ]
    tx = x + 12
    if icon:
        parts.append(glyph(icon, x + 10, y + 8))
        tx += 24
    parts.append(
        f'<text x="{tx}" y="{y + 20}" font-size="12" font-weight="700" fill="#334155">'
        f"{esc(label)}</text>"
    )
    return "\n".join(parts)


def node(
    cx: float,
    cy: float,
    w: float,
    title: str,
    subs: list[str],
    icon: str | None,
    look: str = "solid",
) -> str:
    """look: solid (built), pending (grey dashed, branch awaiting review), gap (red dashed)."""
    h = 26 + 15 * len(subs)
    x, y = cx - w / 2, cy - h / 2
    stroke, fill, ink = {
        "solid": (EDGE, "#FFFFFF", INK),
        "pending": ("#94A3B8", "#FAFBFC", MUTED),
        "gap": ("#DC2626", "#FEF2F2", "#B91C1C"),
    }[look]
    dash = ' stroke-dasharray="6 4"' if look != "solid" else ""
    parts = [
        f'<rect x="{x:.0f}" y="{y:.0f}" width="{w}" height="{h}" rx="8" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="1.2"{dash}/>'
    ]
    tx = x + 12
    if icon:
        parts.append(glyph(icon, x + 10, y + 8))
        tx += 26
    parts.append(
        f'<text x="{tx:.0f}" y="{y + 20}" font-size="12" font-weight="700" fill="{ink}">{esc(title)}</text>'
    )
    for i, sub in enumerate(subs):
        parts.append(
            f'<text x="{tx:.0f}" y="{y + 35 + 15 * i}" font-size="10" fill="{MUTED if look != "gap" else "#B91C1C"}">{esc(sub)}</text>'
        )
    return "\n".join(parts)


def flow(points: list[tuple[float, float]], kind: str) -> str:
    d = "M" + " L".join(f"{px:.0f},{py:.0f}" for px, py in points)
    return f'<path class="f {kind}" d="{d}" marker-end="url(#arrow-{kind})"/>'


def build() -> str:
    sources = [
        node(
            140,
            150,
            220,
            "ASF DAAC",
            [
                "NISAR L1/L2 provisionals " + cast(str, GATE["crid"]),
                f"{GATE['gunw']} GUNW · {GATE['gcov']} GCOV · {GATE['goff']} GOFF",
                f"hour-2 gate 2026-11-14 · {GATE['total']} granules",
            ],
            "sat",
        ),
        node(
            140,
            330,
            220,
            "Google Earth Engine",
            [
                "FABDEM slope · CHIRPS rain",
                "Sentinel-1/2 curtains (#65)",
            ],
            "layers",
        ),
    ]
    gaps = [
        node(
            140,
            470,
            220,
            "CHIRPS late-2026 → 0 images",
            [
                "recorded 'missing' · never fabricated",
            ],
            "flag",
            look="gap",
        ),
    ]

    freeze = [
        node(380, 150, 170, "reports/gate.md", ["freeze window", "2026-06-17 → 11-14"], "doc"),
        node(
            380, 270, 170, "preregistered.yaml", ["thresholds frozen", "before any scoring"], "doc"
        ),
        node(380, 390, 170, "event_facts.json", ["sourced constants", "no LLM numbers"], "doc"),
    ]

    bronze = [
        node(
            615,
            150,
            190,
            "manifest.json × AOI",
            [
                "per band: granule ID",
                "or 'missing'",
            ],
            "doc",
        ),
        node(615, 290, 190, "cogs/*.tif", ["EPSG:4326 512×512", "-9999 sentinel → NaN"], "doc"),
        node(615, 430, 190, "finite ratios", ["checked at build", "(#30 · #78 fixes)"], "doc"),
    ]
    bronze_note = halo(615, 560, "written once 2026-11-14 · never rewritten after", MUTED, 10)

    silver = [
        node(
            890,
            70 + 90 * i,
            260,
            name,
            [sub],
            "cyl" if ok else "doc",
            look="solid" if ok else "pending",
        )
        for i, (name, sub, ok) in enumerate(AOIS)
    ]
    silver.append(
        node(
            890,
            430,
            260,
            "tiles/ + pairs/",
            ["S1+S2 curtains, triplets", "provenance per file"],
            "cyl",
        )
    )
    silver.append(
        node(
            890,
            550,
            260,
            "eje gcov_hvhv_post missing",
            ["post-event GCOV single-pol SHSH"],
            "flag",
            look="gap",
        )
    )

    gold = [
        node(1290, 120, 360, "reports/gate.md + public-readiness.md", ["merged · measured"], "doc"),
        node(
            1290,
            210,
            360,
            "landslide noise floor · branch under review",
            [
                "9.105 mm · 17 pairs · provisional · provenance per pixel",
            ],
            "doc",
            look="pending",
        ),
        node(
            1290,
            300,
            360,
            "flood open-water extents · branch under review",
            [
                "dual-pol classes · bounded reads",
            ],
            "doc",
            look="pending",
        ),
        node(
            1290,
            390,
            360,
            "mission-control panels",
            ["awaiting first merged report"],
            "screen",
            look="pending",
        ),
        node(
            1290,
            500,
            360,
            "C-pair 24-day mismatch",
            ["stated beside every quake number"],
            "flag",
            look="gap",
        ),
    ]

    release = [
        node(
            170,
            740,
            260,
            "GCS · " + BUCKET,
            ["make stage-cache → upload", "make fetch-cache → verify"],
            "star",
        ),
        node(
            620,
            740,
            280,
            "README measured stickers",
            ["link the reports above · no unmeasured claims"],
            "doc",
        ),
        node(1090, 740, 240, "video/ 30-second spot", ["every number sourced"], "doc"),
    ]

    flows = [
        flow([(250, 150), (295, 150)], "pipeline"),
        flow([(250, 330), (280, 330), (280, 70), (560, 70), (560, 108)], "pipeline"),
        flow([(500, 150), (520, 150)], "pipeline"),
        flow([(470, 150), (490, 150)], "pipeline"),
        flow([(710, 150), (760, 150)], "pipeline"),
        flow([(710, 290), (740, 290), (740, 210), (760, 210)], "pipeline"),
        flow([(710, 430), (740, 430), (740, 300), (760, 300)], "pipeline"),
        flow([(1020, 150), (1110, 150)], "pipeline"),
        flow([(1020, 240), (1110, 240)], "pipeline"),
        flow([(1020, 330), (1110, 330)], "pipeline"),
        flow([(1020, 420), (1110, 420)], "pipeline"),
        flow([(890, 640), (890, 666), (170, 666), (170, 696)], "publish"),
        flow([(300, 740), (480, 740)], "publish"),
        flow([(760, 740), (970, 740)], "publish"),
        flow([(1290, 155), (1290, 660), (620, 660), (620, 684)], "control"),
    ]
    labels = [
        halo(180, 108, "catalog the window · read-only", FLOW["pipeline"][0], 9.5),
        halo(615, 520, "bronze: byte-honest references", "#B45309", 9.5),
        halo(890, 620, "silver: curated per AOI · 47 bands total", "#475569", 9.5),
        halo(1290, 560, "gold: measured or honestly pending", "#CA8A04", 9.5),
        halo(560, 660, "manifest provenance → badges cite reports", FLOW["control"][0], 9.5),
    ]

    legend = []
    lx = 24
    for kind, (_colour, text) in FLOW.items():
        legend.append(f'<path class="f {kind}" d="M{lx},84 L{lx + 26},84"/>')
        legend.append(
            f'<text x="{lx + 32}" y="88" font-size="11" fill="#334155">{esc(text)}</text>'
        )
        lx += 46 + round(len(text) * 5.6)
    for text, colour in [
        ("branch under review · not merged", "#94A3B8"),
        (" recorded gap · never fabricated", "#DC2626"),
    ]:
        legend.append(
            f'<rect x="{lx}" y="76" width="26" height="14" rx="3" fill="#FFFFFF" '
            f'stroke="{colour}" stroke-dasharray="5 3"/>'
        )
        legend.append(
            f'<text x="{lx + 32}" y="87" font-size="11" fill="#334155">{esc(text)}</text>'
        )
        lx += 46 + round(len(text) * 5.6)

    markers = "\n".join(
        f'<marker id="arrow-{kind}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
        f'fill="{colour}"/></marker>'
        for kind, (colour, _) in FLOW.items()
    )
    styles = "\n".join(f".{kind}{{stroke:{colour}}}" for kind, (colour, _) in FLOW.items())

    body = [
        zone(20, 60, 240, 600, "Public sources", "sat", "sources"),
        zone(285, 60, 220, 600, "Freeze · in git", "doc", "freeze"),
        zone(525, 60, 200, 600, "Landing · bronze", "doc", "bronze"),
        zone(745, 60, 300, 600, "Curated · silver", "cyl", "silver"),
        zone(1065, 60, 440, 600, "Serving · gold", "star", "gold"),
        zone(20, 700, 1480, 130, "Public release lane", "star", "release"),
        *sources,
        *gaps,
        *freeze,
        *bronze,
        bronze_note,
        *silver,
        *gold,
        *release,
        *flows,
        *labels,
    ]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'font-family="{FONT}">',
        "<title>Surface Tango lakehouse zones</title>",
        "<defs>",
        markers,
        "<style>",
        ".f{fill:none;stroke-width:2;stroke-linejoin:round;stroke-dasharray:7 5;"
        "animation:flow 1.1s linear infinite}",
        "@keyframes flow{to{stroke-dashoffset:-24}}",
        "@media (prefers-reduced-motion: reduce){.f{animation:none}}",
        styles,
        "</style>",
        "</defs>",
        f'<rect width="{W}" height="{H}" rx="16" fill="#FFFFFF"/>',
        '<text x="24" y="34" font-size="21" font-weight="800" fill="#0F172A">Surface Tango · '
        "a three-zone lakehouse on a laptop</text>",
        '<text x="24" y="56" font-size="13" font-weight="700" fill="#334155">two left feet · '
        "Dancing with the SARs · engine bailasar</text>",
        '<text x="24" y="112" font-size="11.5" fill="#64748B">Public SAR granules and public '
        "analyses, frozen and pre-registered, land once as manifests, get curated per AOI, and "
        "serve measured verdicts. What is missing is recorded, never fabricated.</text>",
        *legend,
        *body,
        f'<text x="24" y="{H - 14}" font-size="10" fill="{MUTED}">generated by '
        "scripts/diagrams/lakehouse.py · make diagrams · numbers: reports/gate.md "
        f"({GATE['total']} granules · {GATE['crid']}) · cache manifests 2026-11-14 "
        "(45 · 36 · 30 MB / 15 · 16 · 16 bands) · du -sh local_cache (quake 291 MB) · "
        "reports/aburra.md on its branch</text>",
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build())
    print(f"wrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
