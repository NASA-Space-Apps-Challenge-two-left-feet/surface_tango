# mcp_servers/gee_fusion_mcp.py
"""mcp-gee-fusion: the hazard tools, as adapters over serialized evidence artifacts.

Each ``analyze_*`` tool reads ``local_cache/<aoi>/<hazard>_evidence*.json`` (written
by the data lane during the cache build, from the same measured run as
``reports/<hazard>.md``) and returns the #122 evidence envelope via
``mcp_servers.evidence``. The tools never compute or invent numbers: an absent
artifact is ``not cached``, a missing alert threshold is an ``error``, and the
co-event / control statistics stay sealed until the pre-registration freeze.
"""

import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml
from fastmcp import FastMCP

from mcp_servers import evidence
from mcp_servers.cache_guard import run_server, with_offline_zarr_fallback

ROOT = Path(__file__).resolve().parents[1]
CACHE_ROOT = ROOT / "local_cache"
OPS_CONFIG = ROOT / "config" / "bailasar.yaml"
PREREG = ROOT / "config" / "preregistered.yaml"

mcp = FastMCP(name="gee-hazard-fusion-engine")

_AOIS = {"aburra", "eje_cafetero", "mojana"}


def _ops_config() -> dict:
    return yaml.safe_load(OPS_CONFIG.read_text(encoding="utf-8")) or {}


def _prereg_is_frozen() -> bool:
    try:
        data = yaml.safe_load(PREREG.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return False
    return str(data.get("status", "draft")).strip().lower() == "frozen"


def _artifact(aoi: str, name: str) -> Path:
    return CACHE_ROOT / aoi / f"{name}.json"


@mcp.tool
@with_offline_zarr_fallback()
def analyze_flood_inundation(aoi: str = "mojana") -> dict:
    """Serve the measured La Mojana dual-pol flood evidence (open water per date, classes).

    Returns the #122 flood envelope from ``local_cache/<aoi>/flood_evidence.json``.
    Absent artifact -> ``not cached``. No Earth Engine call; reads only the cache.
    """
    if aoi not in _AOIS:
        return evidence.errored("analyze_flood_inundation", "flood", f"unknown aoi {aoi!r}")
    try:
        artifact = evidence.load_artifact(_artifact(aoi, "flood_evidence"))
    except evidence.EvidenceError as exc:
        return evidence.errored("analyze_flood_inundation", "flood", str(exc))
    if artifact is None:
        return evidence.not_cached(
            "analyze_flood_inundation", "flood", f"no flood evidence for {aoi}"
        )
    try:
        return evidence.build_flood_envelope(artifact, _ops_config(), "analyze_flood_inundation")
    except evidence.EvidenceError as exc:
        return evidence.errored("analyze_flood_inundation", "flood", str(exc))


@mcp.tool
@with_offline_zarr_fallback()
def analyze_landslide_kinematics(aoi: str = "aburra") -> dict:
    """Serve the Aburrá landslide noise-floor verdict (the #109 calibrated null, or motion).

    Returns the #122 landslide envelope from ``local_cache/<aoi>/landslide_evidence.json``.
    Absent artifact -> ``not cached``. No Earth Engine call; reads only the cache.
    """
    if aoi not in _AOIS:
        return evidence.errored("analyze_landslide_kinematics", "landslide", f"unknown aoi {aoi!r}")
    try:
        artifact = evidence.load_artifact(_artifact(aoi, "landslide_evidence"))
    except evidence.EvidenceError as exc:
        return evidence.errored("analyze_landslide_kinematics", "landslide", str(exc))
    if artifact is None:
        return evidence.not_cached(
            "analyze_landslide_kinematics", "landslide", f"no landslide evidence for {aoi}"
        )
    try:
        return evidence.build_landslide_envelope(
            artifact, _ops_config(), "analyze_landslide_kinematics"
        )
    except evidence.EvidenceError as exc:
        return evidence.errored("analyze_landslide_kinematics", "landslide", str(exc))


@mcp.tool
@with_offline_zarr_fallback()
def analyze_earthquake_dpm(aoi: str = "eje_cafetero", track: int = 11) -> dict:
    """Serve the quake coherence-loss damage proxy (counts only; C/K sealed until the freeze).

    Returns the #122 earthquake envelope from
    ``local_cache/<aoi>/quake_evidence_track<track>.json``. Absent -> ``not cached``.
    """
    if aoi not in _AOIS:
        return evidence.errored("analyze_earthquake_dpm", "earthquake", f"unknown aoi {aoi!r}")
    try:
        artifact = evidence.load_artifact(_artifact(aoi, f"quake_evidence_track{int(track)}"))
    except (evidence.EvidenceError, ValueError) as exc:
        return evidence.errored("analyze_earthquake_dpm", "earthquake", str(exc))
    if artifact is None:
        return evidence.not_cached(
            "analyze_earthquake_dpm", "earthquake", f"no quake evidence for {aoi} track {track}"
        )
    try:
        return evidence.build_quake_envelope(
            artifact, _ops_config(), "analyze_earthquake_dpm", is_frozen=_prereg_is_frozen()
        )
    except evidence.EvidenceError as exc:
        return evidence.errored("analyze_earthquake_dpm", "earthquake", str(exc))


@mcp.tool
@with_offline_zarr_fallback()
def analyze_biomass_disturbance(aoi: str = "aburra") -> dict:
    """Biomass is out of scope (dropped, audit #2). Always a gate result, never computed."""
    return evidence._envelope(
        "gate result",
        "analyze_biomass_disturbance",
        "biomass",
        reason="biomass is dropped from the submission scope (AGENTS.md, audit finding 2)",
        data={"scope": "dropped"},
        unavailable={"biomass": evidence._unavailable("dropped from scope; not built")},
    )


if __name__ == "__main__":
    run_server(mcp, "mcp-gee-fusion")
