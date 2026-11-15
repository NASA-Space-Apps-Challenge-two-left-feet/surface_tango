"""Draw the Surface Tango architecture and data-flow diagram as an animated SVG.

Boundaries follow the merged tree, not an aspiration: the two FastMCP SSE servers and their
ports exactly as config/bailasar.yaml declares them, the LangGraph graph as agents/orchestrator.py
wires it, the git-ignored local_cache/ with its measured sizes, and the evidence lane that lives
in git. The cache_guard column is the band every tool call passes, with its three outcomes.
Flow dashes animate via CSS keyframes inside the file (GitHub serves the SVG unmodified);
`prefers-reduced-motion` stops them. Grey dashed nodes are not built yet (they match the README
status table); nothing unbuilt is animated.

    uv run python scripts/diagrams/architecture.py   # writes docs/diagrams/architecture.svg

Numbers shown are measured facts; the footer names their sources.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import cast

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "diagrams" / "architecture.svg"
FONT = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"
W, H = 1520, 1025
TOP = 110  # header band height; the body is drawn below it so nothing covers the legend

# Measured. Sources: reports/gate.md (hour-2 gate 2026-11-14, 251 granules), the cache
# manifests built 2026-11-14 (45/36/30 MB, 15/16/16 bands) and `du -sh local_cache/quake`
# (584 MB, tracks 11 and 47, measured 2026-11-15 after #111).
GATE = {"gunw": 107, "gcov": 130, "goff": 14, "crid": "P05023"}
CACHE = [
    ("eje_cafetero", "45 MB · 15 bands · cube + COGs", True),
    ("aburra", "36 MB · 16 bands · + tiles/ S1+S2 curtains", True),
    ("mojana", "30 MB · 16 bands · dual-pol HH/HV", True),
    ("quake", "584 MB · tracks 11 + 47 · C/K stats sealed", True),
]
BUCKET = "bailasar-cache-472605"

FLOW = {
    "fetch": ("#2563EB", "public data · read-only + Bearer streaming"),
    "tool": ("#D97706", "budgeted agent tool calls"),
    "cached": ("#0D9488", "timeout → cached result + provenance"),
    "publish": ("#16A34A", "public cache release"),
    "control": ("#64748B", "evidence · provenance"),
}

INK, MUTED, EDGE = "#0F172A", "#64748B", "#CBD5E1"


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def halo(
    x: float, y: float, text: str, colour: str, size: float = 10.5, anchor: str = "middle"
) -> str:
    return (
        f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" text-anchor="{anchor}" fill="{colour}" '
        f'stroke="#FFFFFF" stroke-width="4" paint-order="stroke" stroke-linejoin="round">'
        f"{esc(text)}</text>"
    )


def glyph(kind: str, x: float, y: float) -> str:
    """Tiny generic glyphs drawn from primitives (no external assets)."""
    if kind == "lock":
        return (
            f'<circle cx="{x + 8}" cy="{y + 6}" r="4" fill="none" stroke="#B45309" stroke-width="2"/>'
            f'<rect x="{x + 2}" y="{y + 8}" width="12" height="9" rx="2" fill="#B45309"/>'
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
    if kind == "cube":
        return (
            f'<rect x="{x + 1}" y="{y + 5}" width="14" height="12" rx="2" fill="#0D9488"/>'
            f'<path d="M{x + 1} {y + 5} l7 -4 7 4 M{x + 8} {y + 1} v4" fill="none" '
            'stroke="#0D9488" stroke-width="1.6"/>'
        )
    if kind == "doc":
        return (
            f'<path d="M{x + 3} {y + 1} h7 l4 4 v13 h-11 z" fill="none" stroke="{MUTED}" '
            f'stroke-width="1.8"/><path d="M{x + 6} {y + 8} h5 M{x + 6} {y + 12} h5" '
            f'stroke="{MUTED}" stroke-width="1.5"/>'
        )
    if kind == "graph":
        return (
            f'<circle cx="{x + 3}" cy="{y + 14}" r="2.4" fill="#7C3AED"/>'
            f'<circle cx="{x + 15}" cy="{y + 14}" r="2.4" fill="#7C3AED"/>'
            f'<circle cx="{x + 9}" cy="{y + 3}" r="2.4" fill="#7C3AED"/>'
            f'<path d="M{x + 4.5} {y + 12.5} L{x + 8} {y + 5} M{x + 14.5} {y + 12.5} '
            f'L{x + 10} {y + 5}" stroke="#7C3AED" stroke-width="1.6"/>'
        )
    if kind == "pins":
        return f'<path d="M{x + 8} {y + 1} a6 6 0 1 1 -0.1 0 z" fill="#DC2626"/>'
    return (
        f'<circle cx="{x + 8}" cy="{y + 8}" r="7" fill="none" stroke="{MUTED}" stroke-width="2"/>'
    )


def zone(x: float, y: float, w: float, h: float, label: str, icon: str | None, style: str) -> str:
    stroke, fill, dash = {
        "public": ("#38BDF8", "#F0F9FF", ""),
        "graph": ("#A78BFA", "#FAF5FF", ""),
        "servers": ("#FBBF24", "#FFFBEB", ""),
        "cache": ("#2DD4BF", "#F0FDFA", ""),
        "band": ("#E2E8F0", "#F8FAFC", ""),
    }[style]
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="1.4"{dash}/>'
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
    pending: bool = False,
) -> str:
    h = 26 + 15 * len(subs)
    x, y = cx - w / 2, cy - h / 2
    stroke, fill, ink = ("#94A3B8", "#FAFBFC", MUTED) if pending else (EDGE, "#FFFFFF", INK)
    dash = ' stroke-dasharray="6 4"' if pending else ""
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
            f'<text x="{tx:.0f}" y="{y + 35 + 15 * i}" font-size="10" fill="{MUTED}">{esc(sub)}</text>'
        )
    return "\n".join(parts)


def flow(points: list[tuple[float, float]], kind: str, pending: bool = False) -> str:
    d = "M" + " L".join(f"{px:.0f},{py:.0f}" for px, py in points)
    if pending:
        return f'<path class="p" d="{d}" marker-end="url(#arrow-{kind})"/>'
    return f'<path class="f {kind}" d="{d}" marker-end="url(#arrow-{kind})"/>'


def build() -> str:
    asf = node(
        170,
        130,
        264,
        "ASF DAAC · asf_search",
        [
            "NISAR L1/L2 · provisionals " + cast(str, GATE["crid"]),
            f"{GATE['gunw']} GUNW · {GATE['gcov']} GCOV · {GATE['goff']} GOFF",
        ],
        "sat",
    )
    gee = node(
        170,
        250,
        264,
        "Google Earth Engine",
        [
            "FABDEM terrain · CHIRPS rain",
            "Sentinel-1/2 curtain tiles (#65)",
        ],
        "layers",
    )
    gcs = node(
        170,
        370,
        264,
        "GCS · " + BUCKET,
        [
            "public cache distribution",
            "make stage-cache · make fetch-cache",
        ],
        "cube",
    )
    pub = node(170, 480, 264, "OSM · hospitals & roads", ["published damage reports"], "pins")

    ingestion = node(
        530,
        130,
        276,
        "nisar_ingestion",
        [
            "gate catalog + validation/event_facts.json",
            "no LLM numbers enter the bulletin",
        ],
        "graph",
    )
    agents = [
        node(530, 250, 276, "landslide_agent", ["Aburrá pairs · FABDEM slope"], "graph"),
        node(530, 330, 276, "earthquake_agent", ["Eje R/C/K triplets · tracks 11 + 47"], "graph"),
        node(530, 410, 276, "flood_agent", ["Mojana dual-pol HH/HV"], "graph"),
    ]
    synth = node(
        530,
        510,
        288,
        "cross_hazard_synthesis",
        [
            "ES/EN bulletin · {placeholders}",
            "interpolated from tool outputs",
        ],
        "doc",
    )
    ui = node(
        530,
        620,
        288,
        "app.py :8000 · mission control",
        [
            "MapLibre + StoryMap panels",
            "live · cached · not cached · never blank",
        ],
        "screen",
        pending=True,
    )

    guard_x, guard_w = 700, 90
    guard = [
        f'<rect x="{guard_x}" y="70" width="{guard_w}" height="420" rx="10" fill="#FFF7ED" '
        'stroke="#F59E0B" stroke-width="1.4"/>',
        glyph("lock", guard_x + 37, 78),
        f'<text x="{guard_x + guard_w / 2:.0f}" y="285" font-size="12.5" font-weight="800" '
        f'fill="#B45309" text-anchor="middle" transform="rotate(-90 {guard_x + guard_w / 2:.0f} 280)">'
        "cache_guard · every tool call passes</text>",
    ]
    guard_labels = [
        halo(guard_x + guard_w / 2 + 150, 560, "mcp_servers/cache_guard.py", MUTED, 9.5),
        halo(
            guard_x + guard_w / 2 + 150,
            575,
            "live ≤ budget · timeout → cached + provenance · miss → not cached",
            "#B45309",
            9.5,
        ),
    ]

    servers = [
        node(
            980,
            160,
            264,
            "mcp-nisar-asf :8001",
            [
                "search_nisar_granules · anonymous",
                "COG streaming via Earthdata Bearer",
            ],
            "sat",
        ),
        node(
            980,
            290,
            264,
            "mcp-gee-fusion :8002",
            [
                "kinematics · dpm · inundation",
                "ranking · scoring · -9999 sentinel → NaN",
            ],
            "layers",
        ),
        node(
            980,
            410,
            200,
            "SSE live · request-bound cache",
            ["#103 · scoring wrappers #110"],
            None,
        ),
    ]

    cache_nodes = [
        node(1340, 70 + 90 * i, 296, name, [sub], "cube" if ok else "doc", pending=not ok)
        for i, (name, sub, ok) in enumerate(CACHE)
    ]
    cache_nodes.append(
        node(
            1340,
            430,
            296,
            "manifest.json · per AOI",
            [
                "per band: granule ID or 'missing'",
                "finite ratios checked at build (#30, #78)",
            ],
            "doc",
        )
    )
    cache_nodes.append(
        node(
            1340,
            550,
            296,
            "never in git",
            [
                "symlinked into every worktree; built 2026-11-14",
            ],
            "lock",
        )
    )

    evidence = [
        node(
            160,
            800,
            250,
            "reports/",
            ["gate · mojana · aburra · quake_dpm", "public-readiness · ground_truth"],
            "doc",
        ),
        node(
            450,
            800,
            250,
            "validation/",
            ["event_facts.json (verified fields)", "pre-registration · freeze pending"],
            "doc",
        ),
        node(
            740,
            800,
            250,
            "config/",
            ["preregistered.yaml (draft)", "bailasar.yaml ports · budgets"],
            "doc",
        ),
        node(
            1030,
            800,
            250,
            "docs/kb/ · designs/",
            ["26 notes · binding decisions", "biomass dropped (audit #2)"],
            "doc",
        ),
        node(
            1330,
            800,
            210,
            "make ci",
            ["pre-commit + offline tests", "Actions minutes conserved"],
            "screen",
        ),
    ]

    flows = [
        flow([(302, 100), (348, 100), (348, 28), (1100, 28), (1100, 128)], "fetch"),
        flow([(302, 250), (362, 250), (362, 44), (1150, 44), (1150, 230), (1112, 230)], "fetch"),
        flow([(668, 250), (guard_x, 250)], "tool"),
        flow([(668, 330), (guard_x, 330)], "tool"),
        flow([(668, 410), (guard_x, 410)], "tool"),
        flow([(guard_x + guard_w, 160), (848, 160)], "tool"),
        flow([(guard_x + guard_w, 290), (848, 290)], "tool"),
        flow([(745, 495), (745, 668), (1340, 668), (1340, 584)], "cached"),
        flow([(1192, 300), (1160, 300), (1160, 696), (30, 696), (30, 370), (38, 370)], "publish"),
        flow([(1340, 640), (1340, 742)], "control"),
        flow([(530, 546), (530, 588)], "control", pending=True),
        flow([(302, 480), (362, 480), (362, 524), (386, 524)], "control"),
    ]
    labels = [
        halo(
            548,
            44,
            f"provisional {GATE['crid']} · Bearer streaming only for COG reads",
            FLOW["fetch"][0],
            9.5,
        ),
        halo(348, 566, "timeout → pre-staged tiles + provenance", FLOW["cached"][0], 9.5),
        halo(760, 688, "make stage-cache → public bucket", FLOW["publish"][0], 9.5),
        halo(1120, 730, "per-band provenance → measured badges", FLOW["control"][0], 9.5),
    ]

    legend = []
    lx = 24
    for kind, (_colour, text) in FLOW.items():
        legend.append(f'<path class="f {kind}" d="M{lx},84 L{lx + 26},84"/>')
        legend.append(
            f'<text x="{lx + 32}" y="88" font-size="11" fill="#334155">{esc(text)}</text>'
        )
        lx += 46 + round(len(text) * 5.6)
    legend.append(
        '<rect x="1150" y="76" width="26" height="14" rx="3" fill="#FAFBFC" '
        'stroke="#94A3B8" stroke-dasharray="5 3"/>'
    )
    legend.append(
        '<text x="1182" y="87" font-size="11" fill="#334155">not built yet · '
        "matches the status table</text>"
    )

    markers = "\n".join(
        f'<marker id="arrow-{kind}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
        f'fill="{colour}"/></marker>'
        for kind, (colour, _) in FLOW.items()
    )
    styles = "\n".join(f".{kind}{{stroke:{colour}}}" for kind, (colour, _) in FLOW.items())

    body = [
        zone(20, 60, 300, 470, "Public data · read-only", "sat", "public"),
        asf,
        gee,
        gcs,
        pub,
        zone(370, 60, 320, 640, "LangGraph · agents/ · make test-dag", "graph", "graph"),
        zone(820, 60, 320, 470, "FastMCP SSE · config/bailasar.yaml", "sat", "servers"),
        zone(1180, 60, 320, 660, "local_cache/ · git-ignored", "cube", "cache"),
        zone(20, 720, 1480, 160, "In git · measured evidence", "doc", "band"),
        *guard,
        ingestion,
        *agents,
        synth,
        ui,
        *servers,
        *cache_nodes,
        *evidence,
        *flows,
        *labels,
        *guard_labels,
    ]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'font-family="{FONT}">',
        "<title>Surface Tango architecture and data flow</title>",
        "<defs>",
        markers,
        "<style>",
        ".f{fill:none;stroke-width:2;stroke-linejoin:round;stroke-dasharray:7 5;"
        "animation:flow 1.1s linear infinite}",
        ".p{fill:none;stroke:#94A3B8;stroke-width:2;stroke-dasharray:4 4}",
        "@keyframes flow{to{stroke-dashoffset:-24}}",
        "@media (prefers-reduced-motion: reduce){.f{animation:none}}",
        styles,
        "</style>",
        "</defs>",
        f'<rect width="{W}" height="{H}" rx="16" fill="#FFFFFF"/>',
        '<text x="24" y="34" font-size="21" font-weight="800" fill="#0F172A">Surface Tango · '
        "architecture as merged</text>",
        '<text x="24" y="56" font-size="13" font-weight="700" fill="#334155">two left feet · '
        "Dancing with the SARs · engine bailasar</text>",
        '<text x="24" y="112" font-size="11.5" fill="#64748B">Boundaries follow the merged tree: '
        "ports from config/bailasar.yaml, the graph from agents/orchestrator.py, cache sizes "
        "measured. Grey dashed = not built yet.</text>",
        *legend,
        f'<g transform="translate(0,{TOP})">',
        *body,
        "</g>",
        f'<text x="24" y="{H - 14}" font-size="10" fill="{MUTED}">generated by '
        "scripts/diagrams/architecture.py · make diagrams · numbers: reports/gate.md "
        f"(251 granules = {GATE['gunw']} GUNW + {GATE['gcov']} GCOV + {GATE['goff']} GOFF · "
        f"{GATE['crid']}) · cache manifests 2026-11-14 · du -sh local_cache/quake 2026-11-15</text>",
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build())
    print(f"wrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
