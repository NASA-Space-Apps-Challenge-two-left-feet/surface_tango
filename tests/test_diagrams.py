"""Offline checks for the generated README diagrams.

The SVGs are generated files, but their content makes public claims, so the same
honesty rules apply: measured numbers present, no unbuilt component drawn as
built, no secret-looking strings, animation that stops on prefers-reduced-motion.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from scripts.diagrams.architecture import build as build_architecture
from scripts.diagrams.lakehouse import build as build_lakehouse


def test_both_svgs_are_well_formed_xml() -> None:
    # Guards the silent-truncation class: an unparenthesized multi-line string return drops
    # its continuation literal, so the SVG ships truncated and still passes substring checks.
    ET.fromstring(build_architecture())
    ET.fromstring(build_lakehouse())


def test_architecture_shows_the_merged_system() -> None:
    svg = build_architecture()
    assert svg.startswith("<svg")
    for expected in (
        "cache_guard",
        ":8001",
        ":8002",
        "mcp_servers/cache_guard.py",
        "nisar_ingestion",
        "cross_hazard_synthesis",
        "107 GUNW",
        "130 GCOV",
        "14 GOFF",
        "P05023",
        "45 MB",
        "36 MB",
        "30 MB",
        "bailasar-cache-472605",
        "never in git",
    ):
        assert expected in svg, expected


def test_architecture_animates_and_respects_reduced_motion() -> None:
    svg = build_architecture()
    assert "@keyframes flow" in svg
    assert "animation:flow" in svg
    assert "prefers-reduced-motion" in svg


def test_architecture_never_depicts_dropped_scope_as_built() -> None:
    svg = build_architecture()
    assert "biomass" not in svg.lower() or "dropped" in svg.lower()
    pending = svg.count('stroke-dasharray="6 4"')
    assert pending >= 1  # something is honestly marked not-built


def test_lakehouse_zones_and_honest_gaps() -> None:
    svg = build_lakehouse()
    for expected in (
        "bronze",
        "silver",
        "gold",
        "251",
        "9.105 mm",
        "branch under review",
        "gcov_hvhv_post",
        "CHIRPS",
        "never fabricated",
        "2026-06-17",
    ):
        assert expected in svg, expected


def test_diagrams_carry_no_secret_shapes() -> None:
    for svg in (build_architecture(), build_lakehouse()):
        low = svg.lower()
        for banned in ("password", "api_key", "sk-", "token=", "aws_secret"):
            assert banned not in low, banned
