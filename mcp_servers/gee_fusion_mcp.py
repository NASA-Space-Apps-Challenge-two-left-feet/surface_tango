# mcp_servers/gee_fusion_mcp.py
"""mcp-gee-fusion: the hazard tools, as adapters over serialized evidence artifacts.

Each ``analyze_*`` tool reads ``local_cache/<aoi>/<hazard>_evidence*.json`` (written
by the data lane during the cache build, from the same measured run as
``reports/<hazard>.md``) and returns the #122 evidence envelope via
``mcp_servers.evidence``. The tools never compute or invent numbers: an absent
artifact is ``not cached``, a missing alert threshold is an ``error``, and the
co-event / control statistics stay sealed until the pre-registration freeze.
"""

import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pydantic._internal._typing_extra as _pydantic_typing
import yaml
import zarr

# mcp 1.16 still imports this private name. Pydantic 2.14 removed it and
# left eval_type, which takes the same arguments on Python 3.12.
if not hasattr(_pydantic_typing, "eval_type_backport"):
    _pydantic_typing.eval_type_backport = _pydantic_typing.eval_type

from fastmcp import FastMCP

from gee_math.landslide_geology import classes_present, dominant_unit, structure_summary
from gee_math.landslide_geomorphology import (
    epoch_path_m,
    gully_head_retreat_m_per_yr,
    slope_summary,
    translation_coregistration,
)
from gee_math.landslide_hydrogeology import (
    built_up_surcharge_kpa,
    cu_kpa_stroud,
    culmann_plane_wedge,
    effective_stress_change_kpa,
    green_ampt_wetting_front,
    phi_deg_peck_wolff,
    wetting_front_reaches,
)
from mcp_servers import evidence
from mcp_servers.cache_guard import run_server, with_offline_zarr_fallback

ROOT = Path(__file__).resolve().parents[1]
CACHE_ROOT = ROOT / "local_cache"
OPS_CONFIG = ROOT / "config" / "bailasar.yaml"
PREREG = ROOT / "config" / "preregistered.yaml"

mcp = FastMCP(name="gee-hazard-fusion-engine")

_AOIS = {"aburra", "eje_cafetero", "mojana"}
_LANDSLIDE_AOIS = {"aburra", "la_picacha"}
_ANALYST_COMMAND = (
    'uv run python -c "from mcp_servers.gee_fusion_mcp import '
    "analyze_landslide_geology as g, analyze_landslide_geomorphology as m, "
    "analyze_landslide_hydrogeology as h; "
    "print(g.fn('aburra')['state'], m.fn('aburra')['state'], h.fn('aburra')['state'])\""
)


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


def _finite_or_none(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _json_ready(value: object) -> object:
    """Drop non-finite numbers and arrays so an envelope can be serialized."""
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.ndarray):
        return None
    if isinstance(value, np.floating):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, int):
        return value
    return None


def _source_ids(record: dict | None) -> list[str] | None:
    if not isinstance(record, dict):
        return None
    raw = record.get("source_ids")
    if (
        not isinstance(raw, list)
        or not raw
        or not all(isinstance(item, str) and item.strip() for item in raw)
    ):
        return None
    return raw


def _load_record(path: Path) -> dict | None:
    """Read a staged JSON record. None when the file is absent."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise evidence.EvidenceError(f"unreadable staged record {path.name}: {exc}") from None
    if not isinstance(data, dict):
        raise evidence.EvidenceError(f"staged record {path.name} is not an object")
    return data


def _manifest(aoi: str) -> dict | None:
    path = CACHE_ROOT / aoi / "manifest.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _band_meta(aoi: str, band: str) -> dict | None:
    manifest = _manifest(aoi)
    if not isinstance(manifest, dict):
        return None
    bands = manifest.get("bands")
    if not isinstance(bands, dict):
        return None
    meta = bands.get(band)
    return meta if isinstance(meta, dict) else None


def _mtime_utc(path: Path) -> str | None:
    try:
        stamp = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except OSError:
        return None
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_zarr(aoi: str, band: str) -> np.ndarray | None:
    path = CACHE_ROOT / aoi / f"{aoi}_sar_cube.zarr" / band
    if not (path / "zarr.json").is_file():
        return None
    try:
        array = zarr.open_array(path, mode="r")
        values = np.asarray(array[...], dtype=np.float64)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if values.ndim == 0 or values.size == 0:
        return None
    return values


def _zarr_pixel_count(aoi: str, band: str) -> int | None:
    path = CACHE_ROOT / aoi / f"{aoi}_sar_cube.zarr" / band / "zarr.json"
    if not path.is_file():
        return None
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    shape = meta.get("shape") if isinstance(meta, dict) else None
    if not isinstance(shape, list) or not shape:
        return None
    count = 1
    for item in shape:
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            return None
        count *= item
    return count


def _summary_block(summary: dict, source_ids: list[str], command: str) -> dict:
    return {
        "n_pixels": summary["n_pixels"],
        "n_finite": summary["n_finite"],
        "median_deg": summary["median_deg"],
        "p05_deg": summary["p05_deg"],
        "p95_deg": summary["p95_deg"],
        "source_ids": source_ids,
        "measurement": "measured",
        "command": command,
        "denominator": "finite pixels over cells in the staged grid",
    }


def _hand_block(values: np.ndarray, source_ids: list[str]) -> dict:
    summary = slope_summary(values)
    return {
        "n_pixels": summary["n_pixels"],
        "n_finite": summary["n_finite"],
        "median_m": summary["median_deg"],
        "p05_m": summary["p05_deg"],
        "p95_m": summary["p95_deg"],
        "source_ids": source_ids,
        "measurement": "measured",
        "command": _ANALYST_COMMAND,
        "denominator": "finite HAND pixels over cells in the staged grid",
        "quantity": "height above nearest drainage",
    }


def _insar_tie(aoi: str) -> dict | None:
    try:
        artifact = evidence.load_artifact(CACHE_ROOT / aoi / "landslide_evidence.json")
    except evidence.EvidenceError:
        return None
    if not isinstance(artifact, dict):
        return None
    verdict = artifact.get("noise_floor_verdict")
    provenance = artifact.get("provenance")
    if not isinstance(verdict, dict) or not isinstance(provenance, dict):
        return None
    ids = provenance.get("granule_ids")
    if not isinstance(ids, list) or not ids:
        return None
    return {
        "outcome": verdict.get("outcome"),
        "noise_floor_mm": _finite_or_none(verdict.get("noise_floor_mm")),
        "n_pairs": verdict.get("n_pairs") if isinstance(verdict.get("n_pairs"), int) else None,
        "text": verdict.get("text") if isinstance(verdict.get("text"), str) else None,
        "source_ids": ids,
        "command": provenance.get("command"),
        "measurement": "measured",
        "denominator": "GUNW pairs with a finite residual RMS",
    }


def _analyst_envelope(
    tool: str,
    state: str,
    reason: str,
    data: dict | None,
    provenance: dict | None,
    unavailable: dict,
) -> dict:
    error = "not cached" if state == "not cached" else None
    return evidence._envelope(
        state,
        tool,
        "landslide",
        reason=reason,
        data=_json_ready(data),
        provenance=_json_ready(provenance),
        unavailable=unavailable,
        error=error,
    )


def _unknown_aoi(tool: str, aoi: str) -> dict | None:
    if aoi not in _LANDSLIDE_AOIS:
        return evidence.errored(tool, "landslide", f"unknown aoi {aoi!r}")
    return None


@mcp.tool
@with_offline_zarr_fallback()
def analyze_landslide_geology(aoi: str = "aburra") -> dict:
    """Conditioning geology for one landslide AOI, from a staged public unit layer.

    Reads ``local_cache/<aoi>/geology.json`` only. An absent file is ``not cached``.
    Engineering class comes from the staged lithology label. Unrecognized labels
    stay unclassified. No Earth Engine call.
    """
    tool = "analyze_landslide_geology"
    rejected = _unknown_aoi(tool, aoi)
    if rejected is not None:
        return rejected
    path = CACHE_ROOT / aoi / "geology.json"
    try:
        record = _load_record(path)
    except evidence.EvidenceError as exc:
        return evidence.errored(tool, "landslide", str(exc))
    if record is None:
        return evidence.not_cached(
            tool,
            "landslide",
            f"no staged public geology layer for {aoi} "
            f"(expected local_cache/{aoi}/geology.json; SGC units are not inferred)",
        )
    source_ids = _source_ids(record)
    if source_ids is None:
        return evidence.errored(tool, "landslide", "geology record missing source_ids")
    units = record.get("units")
    structures = record.get("structures", [])
    if not isinstance(units, list) or not isinstance(structures, list):
        return evidence.errored(
            tool, "landslide", "geology record units or structures are not lists"
        )
    dominant = dominant_unit(units)
    data = {
        "aoi": aoi,
        "method": "SGC factores condicionantes: geologia para ingenieria",
        "dominant_unit": dominant,
        "classes_present": classes_present(units),
        "structures": structure_summary(structures),
        "n_units": len(units),
        "asset_id": record.get("asset_id") if isinstance(record.get("asset_id"), str) else None,
        "dates": record.get("dates") if isinstance(record.get("dates"), list) else None,
        "measurement": "measured",
        "command": record.get("command")
        if isinstance(record.get("command"), str)
        else _ANALYST_COMMAND,
        "source_ids": source_ids,
    }
    unavailable = {}
    if dominant is None:
        unavailable["dominant_unit"] = evidence._unavailable(
            "no unit has a finite pixel count; no dominant unit is chosen"
        )
    if data["dates"] is None:
        unavailable["dates"] = evidence._unavailable("geology record has no date list")
    state = "cached" if dominant is not None else "gate result"
    reason = (
        "dominant staged geologic unit"
        if dominant is not None
        else "staged geology layer has no countable unit"
    )
    return _analyst_envelope(
        tool,
        state,
        reason,
        data,
        {
            "source": "cache",
            "granule_ids": source_ids,
            "cache_build_time": _mtime_utc(path),
            "cache_time_meaning": "mtime of the staged geology record, not an acquisition date",
            "command": data["command"],
            "aoi": aoi,
        },
        unavailable,
    )


@mcp.tool
@with_offline_zarr_fallback()
def analyze_landslide_geomorphology(aoi: str = "aburra") -> dict:
    """Terrain, photogrammetry, and the existing NISAR InSAR tie for one AOI.

    Slope and HAND are reduced from the staged cube when those arrays read.
    Aspect, curvature, relative relief, and gully retreat stay unavailable
    unless their own staged inputs exist. The Aburrá grid is not reused for
    another AOI. No Earth Engine call.
    """
    tool = "analyze_landslide_geomorphology"
    rejected = _unknown_aoi(tool, aoi)
    if rejected is not None:
        return rejected
    slope_values = _read_zarr(aoi, "slope_deg")
    hand_values = _read_zarr(aoi, "hand_m")
    slope_meta = _band_meta(aoi, "slope_deg")
    hand_meta = _band_meta(aoi, "hand_m")
    insar = _insar_tie(aoi)
    photo_path = CACHE_ROOT / aoi / "photogrammetry.json"
    try:
        photo = _load_record(photo_path)
    except evidence.EvidenceError as exc:
        return evidence.errored(tool, "landslide", str(exc))

    unavailable: dict = {}
    slope_block = None
    if slope_values is not None:
        slope_ids = []
        if isinstance(slope_meta, dict) and isinstance(slope_meta.get("source_id"), str):
            slope_ids = [slope_meta["source_id"]]
        if not slope_ids:
            slope_ids = [f"local_cache/{aoi}/{aoi}_sar_cube.zarr/slope_deg"]
        slope_block = _summary_block(slope_summary(slope_values), slope_ids, _ANALYST_COMMAND)
        if slope_block["n_finite"] == 0:
            slope_block["median_deg"] = None
            slope_block["p05_deg"] = None
            slope_block["p95_deg"] = None
    else:
        unavailable["slope"] = evidence._unavailable(
            "FABDEM slope array is not readable in the staged cube"
        )

    hand_block = None
    if hand_values is not None:
        hand_ids = []
        if isinstance(hand_meta, dict) and isinstance(hand_meta.get("source_id"), str):
            hand_ids = [hand_meta["source_id"]]
        if not hand_ids:
            hand_ids = [f"local_cache/{aoi}/{aoi}_sar_cube.zarr/hand_m"]
        hand_block = _hand_block(hand_values, hand_ids)
        if hand_block["n_finite"] == 0:
            hand_block["median_m"] = None
            hand_block["p05_m"] = None
            hand_block["p95_m"] = None
    else:
        unavailable["hand_m"] = evidence._unavailable(
            "MERIT HAND array is not readable in the staged cube"
        )

    unavailable["aspect_curvature_relief"] = evidence._unavailable(
        "no elevation grid is staged; aspect, curvature, and relative relief "
        "are not derived, and HAND is not used as a substitute"
    )
    unavailable["geomorphological_units"] = evidence._unavailable(
        "no geomorphological-unit layer is staged; slope is not binned "
        "(no unit threshold is pre-registered)"
    )

    photo_block = {
        "coregistration": None,
        "epoch_path": None,
        "gully_head_retreat_m_per_yr": None,
        "downslope_m": None,
        "source_ids": None,
    }
    if photo is None:
        unavailable["photogrammetry"] = evidence._unavailable(
            f"no staged orthophoto history (expected local_cache/{aoi}/photogrammetry.json)"
        )
    else:
        photo_ids = _source_ids(photo)
        if photo_ids is None:
            return evidence.errored(tool, "landslide", "photogrammetry record missing source_ids")
        photo_block["source_ids"] = photo_ids
        photo_block["command"] = (
            photo.get("command") if isinstance(photo.get("command"), str) else _ANALYST_COMMAND
        )
        source_xy = photo.get("control_source_xy_m")
        target_xy = photo.get("control_target_xy_m")
        if isinstance(source_xy, list) and isinstance(target_xy, list):
            photo_block["coregistration"] = translation_coregistration(source_xy, target_xy)
        else:
            unavailable["photogrammetry.coregistration"] = evidence._unavailable(
                "control points are not staged"
            )
        epochs = photo.get("epoch_xy_m")
        if isinstance(epochs, list):
            photo_block["epoch_path"] = epoch_path_m(epochs)
        else:
            unavailable["photogrammetry.epoch_path"] = evidence._unavailable(
                "epoch coordinates are not staged"
            )
        retreat = gully_head_retreat_m_per_yr(
            photo.get("gully_head_distance_m"), photo.get("gully_head_delta_days")
        )
        photo_block["gully_head_retreat_m_per_yr"] = retreat
        if retreat is None:
            unavailable["photogrammetry.gully_head_retreat_m_per_yr"] = evidence._unavailable(
                "gully-head distance or interval is missing"
            )
        downslope = _finite_or_none(photo.get("downslope_m"))
        photo_block["downslope_m"] = downslope
        if downslope is None:
            unavailable["photogrammetry.downslope_m"] = evidence._unavailable(
                "signed photogrammetric downslope displacement is not staged"
            )

    agreement = None
    if photo_block.get("downslope_m") is not None and insar is not None:
        # The staged InSAR artifact stores an unsigned noise-floor magnitude.
        # Comparing that magnitude with a signed photo displacement would invent agreement.
        unavailable["photo_insar_sign_agreement"] = evidence._unavailable(
            "staged InSAR artifact stores a noise-floor magnitude, not a signed "
            "downslope displacement, so agreement is not evaluated"
        )
    elif insar is None:
        unavailable["insar"] = evidence._unavailable("no staged landslide InSAR evidence")
        unavailable["photo_insar_sign_agreement"] = evidence._unavailable(
            "photogrammetry and InSAR are not both signed displacements"
        )
    else:
        unavailable["photo_insar_sign_agreement"] = evidence._unavailable(
            "photogrammetric signed displacement is missing; InSAR is reported alone"
        )

    measured = (
        any(
            block is not None and block.get("n_finite", 0) > 0
            for block in (slope_block, hand_block)
        )
        or insar is not None
        or photo is not None
    )
    if slope_block is None and hand_block is None and insar is None and photo is None:
        return evidence.not_cached(
            tool,
            "landslide",
            f"no staged DEM, HAND, orthophoto history, or InSAR evidence for {aoi}",
        )
    source_ids: list[str] = []
    for block in (slope_block, hand_block, insar):
        if isinstance(block, dict) and isinstance(block.get("source_ids"), list):
            source_ids.extend(item for item in block["source_ids"] if item not in source_ids)
    if isinstance(photo_block.get("source_ids"), list):
        source_ids.extend(item for item in photo_block["source_ids"] if item not in source_ids)
    state = "cached" if measured else "gate result"
    return _analyst_envelope(
        tool,
        state,
        "staged terrain and the InSAR tie; photogrammetry only where a record exists",
        {
            "aoi": aoi,
            "method": "SGC geomorfologia e inventario de movimientos en masa",
            "slope": slope_block,
            "hand_m": hand_block,
            "derivatives": None,
            "geomorphological_units": None,
            "photogrammetry": photo_block,
            "insar": insar,
            "photo_insar_sign_agreement": agreement,
            "measurement": "measured",
            "command": _ANALYST_COMMAND,
        },
        {
            "source": "cache",
            "granule_ids": source_ids or [f"local_cache/{aoi}"],
            "cache_build_time": _mtime_utc(CACHE_ROOT / aoi / "manifest.json"),
            "cache_time_meaning": "mtime of the AOI manifest when present, not an acquisition date",
            "command": _ANALYST_COMMAND,
            "aoi": aoi,
        },
        unavailable,
    )


def _profile_number(profile: dict, key: str) -> float | None:
    return _finite_or_none(profile.get(key))


@mcp.tool
@with_offline_zarr_fallback()
def analyze_landslide_hydrogeology(aoi: str = "aburra") -> dict:
    """Rain trigger, water-table stress, SPT-N strength, and Culmann stability.

    Green-Ampt, effective stress, and Culmann run only on finite staged inputs.
    A missing rainfall depth, SPT blow count, or strength profile stays null.
    The rainfall band is summarized when the cube or the manifest records it.
    No Earth Engine call and no default soil parameters.
    """
    tool = "analyze_landslide_hydrogeology"
    rejected = _unknown_aoi(tool, aoi)
    if rejected is not None:
        return rejected
    rain_values = _read_zarr(aoi, "rain_15d_mm")
    rain_meta = _band_meta(aoi, "rain_15d_mm")
    profile_path = CACHE_ROOT / aoi / "hydro_profile.json"
    cover_path = CACHE_ROOT / aoi / "worldcover.json"
    try:
        profile = _load_record(profile_path)
        cover = _load_record(cover_path)
    except evidence.EvidenceError as exc:
        return evidence.errored(tool, "landslide", str(exc))

    if rain_values is None and rain_meta is None and profile is None and cover is None:
        return evidence.not_cached(
            tool,
            "landslide",
            f"no staged rainfall, strength profile, or WorldCover record for {aoi}",
        )

    unavailable: dict = {}
    rainfall = None
    if rain_values is not None:
        summary = slope_summary(rain_values)
        source = "missing"
        if isinstance(rain_meta, dict) and isinstance(rain_meta.get("source_id"), str):
            source = rain_meta["source_id"]
        rainfall = {
            "n_pixels": summary["n_pixels"],
            "n_finite": summary["n_finite"],
            "median_mm": summary["median_deg"] if summary["n_finite"] else None,
            "source_ids": [source],
            "values_read": True,
            "measurement": "measured",
            "command": _ANALYST_COMMAND,
            "denominator": "finite rainfall pixels over cells in the staged grid",
        }
    elif isinstance(rain_meta, dict):
        finite = rain_meta.get("finite_pixel_count")
        n_finite = finite if isinstance(finite, int) and not isinstance(finite, bool) else None
        n_pixels = _zarr_pixel_count(aoi, "rain_15d_mm")
        source = (
            rain_meta.get("source_id") if isinstance(rain_meta.get("source_id"), str) else "missing"
        )
        rainfall = {
            "n_pixels": n_pixels,
            "n_finite": n_finite,
            "median_mm": None,
            "source_ids": [source],
            "values_read": False,
            "status": rain_meta.get("status"),
            "measurement": "measured",
            "command": _ANALYST_COMMAND,
            "denominator": "finite_pixel_count in the AOI manifest; pixel values were not re-read",
        }
    if rainfall is None or not rainfall.get("n_finite"):
        unavailable["wetting_front_m"] = evidence._unavailable(
            "staged rainfall has no finite depth, so Green-Ampt is not run"
        )

    front = None
    reaches = None
    if isinstance(profile, dict):
        if _source_ids(profile) is None:
            return evidence.errored(tool, "landslide", "hydro profile missing source_ids")
        ampt = profile.get("green_ampt") if isinstance(profile.get("green_ampt"), dict) else {}
        rainfall_m = _profile_number(profile, "rainfall_m")
        if rainfall_m is None and rainfall is not None and rainfall.get("median_mm") is not None:
            rainfall_m = float(rainfall["median_mm"]) / 1000.0
        computed = green_ampt_wetting_front(
            ampt.get("duration_s"),
            ampt.get("k_m_s"),
            ampt.get("psi_m"),
            ampt.get("delta_theta"),
            rainfall_m,
        )
        if computed["reason"] is None:
            unavailable.pop("wetting_front_m", None)
            front_ids = list(_source_ids(profile) or [])
            if isinstance(rainfall, dict):
                front_ids.extend(item for item in rainfall["source_ids"] if item not in front_ids)
            front = {
                **computed,
                "source_ids": front_ids,
                "measurement": "estimate",
                "command": profile.get("command")
                if isinstance(profile.get("command"), str)
                else _ANALYST_COMMAND,
                "denominator": "one staged profile; rainfall depth only when a finite median exists",
            }
            reaches = wetting_front_reaches(
                computed["wetting_front_m"], profile.get("failure_depth_m")
            )
            if reaches is None:
                unavailable["wetting_front_reaches_failure"] = evidence._unavailable(
                    "failure depth is not staged"
                )
        else:
            unavailable["wetting_front_m"] = evidence._unavailable(
                "Green-Ampt inputs are incomplete or invalid in the staged profile"
            )
    else:
        unavailable["hydro_profile"] = evidence._unavailable(
            "no staged strength or Green-Ampt profile "
            f"(expected local_cache/{aoi}/hydro_profile.json)"
        )

    stress = None
    phi = None
    cohesion_spt = None
    culmann = None
    if isinstance(profile, dict):
        stress = effective_stress_change_kpa(profile.get("water_table_rise_m"))
        if stress is None:
            unavailable["effective_stress_change_kpa"] = evidence._unavailable(
                "no staged water-table rise; effective-stress change is not computed"
            )
        phi = phi_deg_peck_wolff(profile.get("spt_n"))
        cohesion_spt = cu_kpa_stroud(profile.get("spt_n"), profile.get("stroud_factor"))
        if phi is None:
            unavailable["phi_deg_spt"] = evidence._unavailable("SPT-N is not staged")
        if cohesion_spt is None:
            unavailable["cu_kpa_spt"] = evidence._unavailable(
                "SPT-N or the Stroud factor is not staged"
            )
        cohesion = _profile_number(profile, "cohesion_kpa")
        if cohesion is None:
            cohesion = cohesion_spt
        friction = _profile_number(profile, "friction_deg")
        if friction is None:
            friction = phi
        weight = _profile_number(profile, "unit_weight_kn_m3")
        height = _profile_number(profile, "height_m")
        slope = _profile_number(profile, "slope_deg")
        if slope is None and profile.get("slope_deg_from") == "cached_slope_median":
            slope_values = _read_zarr(aoi, "slope_deg")
            if slope_values is not None:
                slope = slope_summary(slope_values)["median_deg"]
        surcharge = _profile_number(profile, "surcharge_kpa")
        if None not in (cohesion, friction, weight, slope):
            culmann = culmann_plane_wedge(cohesion, friction, slope, weight, height, surcharge)
            culmann["source_ids"] = _source_ids(profile)
            culmann["measurement"] = "estimate"
            culmann["command"] = (
                profile.get("command")
                if isinstance(profile.get("command"), str)
                else _ANALYST_COMMAND
            )
            culmann["denominator"] = "one staged profile; not a pixel count"
        else:
            unavailable["culmann"] = evidence._unavailable(
                "cohesion, friction, unit weight, or slope is missing; "
                "Culmann critical height is not computed"
            )
    else:
        unavailable["effective_stress_change_kpa"] = evidence._unavailable(
            "no staged water-table series"
        )
        unavailable["phi_deg_spt"] = evidence._unavailable("SPT-N is not staged")
        unavailable["cu_kpa_spt"] = evidence._unavailable("SPT-N is not staged")
        unavailable["culmann"] = evidence._unavailable(
            "no staged geologic strength profile for the Culmann wedge"
        )

    load = None
    if cover is None:
        unavailable["built_up_surcharge_kpa"] = evidence._unavailable(
            f"no staged WorldCover built-up fraction (expected local_cache/{aoi}/worldcover.json)"
        )
    else:
        cover_ids = _source_ids(cover)
        if cover_ids is None:
            return evidence.errored(tool, "landslide", "worldcover record missing source_ids")
        load = built_up_surcharge_kpa(
            cover.get("built_fraction"), cover.get("surcharge_on_built_kpa")
        )
        if load is None:
            unavailable["built_up_surcharge_kpa"] = evidence._unavailable(
                "built fraction or unit surcharge is missing or out of range"
            )
        else:
            load = {
                "surcharge_kpa": load,
                "source_ids": cover_ids,
                "measurement": "measured",
                "command": cover.get("command")
                if isinstance(cover.get("command"), str)
                else _ANALYST_COMMAND,
                "denominator": "built fraction times the staged unit surcharge",
            }

    science = any(item is not None for item in (front, stress, culmann, load, phi, cohesion_spt))
    state = "cached" if science else "gate result"
    reason = (
        "staged hydrogeology inputs reduced with Green-Ampt, effective stress, or Culmann"
        if science
        else "rainfall or strength inputs inspected; wetting front and Culmann withheld"
    )
    provenance_ids: list[str] = []
    if isinstance(rainfall, dict):
        provenance_ids.extend(rainfall["source_ids"])
    if isinstance(profile, dict) and _source_ids(profile):
        provenance_ids.extend(
            item for item in _source_ids(profile) or [] if item not in provenance_ids
        )
    return _analyst_envelope(
        tool,
        state,
        reason,
        {
            "aoi": aoi,
            "method": "Green-Ampt; effective stress; Culmann plane wedge; SPT-N",
            "rainfall": rainfall,
            "wetting_front": front,
            "wetting_front_reaches_failure": reaches,
            "effective_stress_change_kpa": stress,
            "phi_deg_spt": phi,
            "cu_kpa_spt": cohesion_spt,
            "culmann": culmann,
            "built_up_load": load,
            "command": _ANALYST_COMMAND,
        },
        {
            "source": "cache",
            "granule_ids": provenance_ids or [f"local_cache/{aoi}"],
            "cache_build_time": _mtime_utc(CACHE_ROOT / aoi / "manifest.json"),
            "cache_time_meaning": "mtime of the AOI manifest when present, not an acquisition date",
            "command": _ANALYST_COMMAND,
            "aoi": aoi,
        },
        unavailable,
    )


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
    run_server(mcp, "gee_fusion")
