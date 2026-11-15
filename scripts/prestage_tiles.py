"""Pre-stage the curtain slider's optical (Sentinel-2) and C-band (Sentinel-1) panels for offline use.

    uv run python scripts/prestage_tiles.py --aoi eje_cafetero
    uv run python scripts/prestage_tiles.py --aoi aburra --zoom-min 9 --zoom-max 13
    uv run python scripts/prestage_tiles.py --aoi mojana --dry-run      # select and print, no tiles

Scenes are chosen by a stated rule (written into the manifest), never by eye:

* Eje Cafetero (quake): the least-cloudy S2 acquisition within 30 days after the event date, and the
  S1 acquisition nearest after the event on the orbit direction of the NISAR co-event pair.
* Aburrá, La Mojana: the least-cloudy S2 acquisition in the NISAR window, and the S1 acquisition
  nearest in time to that S2 acquisition, also in the NISAR window.

An "acquisition" is every granule of one satellite pass on one UTC day that intersects the AOI
(S2: same day, spacecraft and relative orbit; S1: same day, platform, relative orbit and pass),
mosaicked. "Least cloudy" is measured over the AOI from the S2 Scene Classification band: the
percentage of AOI pixels that are cloud (SCL 8, 9, 10) or not imaged by the pass. Counting
not-imaged pixels stops a pass that clips a corner of the AOI from winning with 0 % cloud.
Ties go to the earliest date. If a collection has no acquisition in the window the layer is
written as ``missing`` with the reason; there is no fallback scene and no generated pixels.

Writes XYZ PNG tiles under ``local_cache/<aoi>/tiles/{s2,s1}/{z}/{x}/{y}.png`` and
``local_cache/<aoi>/tiles/manifest.json``. The AOI bbox comes from ``config/bailasar.yaml``
(``aois:``), the event date from ``validation/event_facts.json`` and the NISAR window and
co-event pair from ``nisar_colombia_granules_2026.json``. Read-only on Earth Engine; local
writes only.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "bailasar.yaml"
EVENT_FACTS = ROOT / "validation" / "event_facts.json"
GATE_CATALOG = ROOT / "nisar_colombia_granules_2026.json"
CACHE_DIR = ROOT / "local_cache"

S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
S1_COLLECTION = "COPERNICUS/S1_GRD"
# CLI name -> substring of the key under `aois:` in config/bailasar.yaml (the bbox lives only there).
AOI_KEYS = {"aburra": "aburra", "eje_cafetero": "eje_cafetero", "mojana": "mojana"}
QUAKE_AOI = "eje_cafetero"
QUAKE_FACT = "quake_2026_08_10"
QUAKE_S2_WINDOW_DAYS = 30  # brief feat/data-prestage-tiles, step 1
SCL_CLOUD_CLASSES = [
    8,
    9,
    10,
]  # Sentinel-2 L2A SCL: cloud medium prob., cloud high prob., thin cirrus
STATS_SCALE_M = 100  # reduceRegion scale for the AOI cloud/coverage fractions (selection only)
NISAR_DIR_RE = re.compile(r"NISAR_L2_[A-Z]{2}_GUNW_\d{3}_(?P<track>\d{3})_(?P<dir>[AD])_")


# ---------------------------------------------------------------------------
# Inputs (config, facts, gate catalog)
# ---------------------------------------------------------------------------
def load_env(env_path: Path) -> None:
    """Load KEY=VALUE lines from .env without overriding existing values (never printed)."""
    import os

    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def load_aoi(aoi: str, config_path: Path = CONFIG) -> tuple[str, list[float]]:
    """Return (config key, [W, S, E, N]) for a CLI AOI name, read from config/bailasar.yaml."""
    aois = yaml.safe_load(config_path.read_text(encoding="utf-8"))["aois"]
    keys = [k for k in aois if AOI_KEYS[aoi] in k]
    if len(keys) != 1:
        raise SystemExit(
            f"expected one aois: key matching {AOI_KEYS[aoi]!r} in {config_path}, found {keys}"
        )
    bbox = aois[keys[0]]
    if not bbox or len(bbox) != 4:
        raise SystemExit(f"AOI bbox not set in {config_path}: {keys[0]}")
    return keys[0], [float(v) for v in bbox]


def load_event_date(facts_path: Path = EVENT_FACTS) -> date:
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    return date.fromisoformat(facts[QUAKE_FACT]["date"])


def load_gate(catalog_path: Path = GATE_CATALOG) -> dict:
    return json.loads(catalog_path.read_text(encoding="utf-8"))


def nisar_window(gate: dict) -> tuple[date, date]:
    """NISAR window [start, end] (inclusive dates) from the hour-2 gate catalog."""
    start, end = gate["window"]
    return date.fromisoformat(start[:10]), date.fromisoformat(end[:10])


def coevent_orbit(gate: dict) -> dict:
    """Orbit direction of the first NISAR co-event (C) pair in the gate catalog."""
    triplet = gate["quake_triplets"][0]
    m = NISAR_DIR_RE.search(triplet["C"])
    if not m:
        raise SystemExit(f"cannot parse orbit direction from {triplet['C']}")
    return {
        "nisar_pair": triplet["C"],
        "nisar_track": int(m["track"]),
        "pass": "ASCENDING" if m["dir"] == "A" else "DESCENDING",
    }


# ---------------------------------------------------------------------------
# Selection rules (pure: operate on acquisition dicts, tested without Earth Engine)
# ---------------------------------------------------------------------------
def group_acquisitions(granules: Iterable[dict], keys: tuple[str, ...]) -> list[dict]:
    """Group granule dicts (id, date, *keys) into acquisitions: one pass on one UTC day."""
    groups: dict[tuple, dict] = {}
    for g in granules:
        k = (g["date"], *(g.get(key) for key in keys))
        acq = groups.setdefault(
            k, {"date": g["date"], **{key: g.get(key) for key in keys}, "ids": []}
        )
        acq["ids"].append(g["id"])
    for acq in groups.values():
        acq["ids"].sort()
    return sorted(groups.values(), key=lambda a: (a["date"], a["ids"][0]))


def in_window(acqs: Iterable[dict], start: date, end: date) -> list[dict]:
    """Acquisitions with start <= date <= end (dates as ISO strings)."""
    return [a for a in acqs if start <= date.fromisoformat(a["date"]) <= end]


def least_cloudy(acqs: list[dict]) -> dict | None:
    """Lowest obscured % (cloud or not imaged, over the AOI); ties -> earliest date, then id."""
    scored = [a for a in acqs if a.get("obscured_pct") is not None]
    if not scored:
        return None
    return min(scored, key=lambda a: (a["obscured_pct"], a["date"], a["ids"][0]))


def nearest_after(acqs: list[dict], after: date, orbit_pass: str | None = None) -> dict | None:
    """Earliest acquisition strictly after `after`, optionally on one orbit direction."""
    cands = [
        a
        for a in acqs
        if date.fromisoformat(a["date"]) > after
        and (orbit_pass is None or a.get("pass") == orbit_pass)
    ]
    return min(cands, key=lambda a: (a["date"], a["ids"][0])) if cands else None


def nearest_to(acqs: list[dict], target: date) -> dict | None:
    """Acquisition with the smallest |date - target|; ties -> earlier date, then id."""
    if not acqs:
        return None
    return min(
        acqs,
        key=lambda a: (abs((date.fromisoformat(a["date"]) - target).days), a["date"], a["ids"][0]),
    )


def s2_rule(aoi: str, event: date, window: tuple[date, date]) -> dict:
    if aoi == QUAKE_AOI:
        start, end = event + timedelta(days=1), event + timedelta(days=QUAKE_S2_WINDOW_DAYS)
        text = f"Least-cloudy {S2_COLLECTION} acquisition within {QUAKE_S2_WINDOW_DAYS} days after the event ({event.isoformat()}): dates {start.isoformat()}..{end.isoformat()} inclusive."
    else:
        start, end = window
        text = f"Least-cloudy {S2_COLLECTION} acquisition in the NISAR window {start.isoformat()}..{end.isoformat()} inclusive."
    text += f" Acquisition = all granules of one spacecraft/relative orbit on one UTC day intersecting the AOI, mosaicked. Least cloudy = lowest % of AOI pixels that are cloud (SCL {SCL_CLOUD_CLASSES}) or not imaged, at {STATS_SCALE_M} m; ties -> earliest date. Clouds are not masked in the tiles."
    return {"start": start, "end": end, "text": text}


def s1_rule(
    aoi: str, event: date, window: tuple[date, date], orbit: dict | None, s2_date: date | None
) -> dict:
    base = " Acquisition = all IW GRD slices with VV of one platform/relative orbit/pass on one UTC day intersecting the AOI, mosaicked; ties -> earliest date. Tiles show VV backscatter (dB)."
    if aoi == QUAKE_AOI:
        start, end = window
        text = f"{S1_COLLECTION} acquisition nearest after the event ({event.isoformat()}, i.e. first UTC day > event) on the {orbit['pass']} pass, the orbit direction of the NISAR co-event pair {orbit['nisar_pair']} (track {orbit['nisar_track']}), within the NISAR window {start.isoformat()}..{end.isoformat()}."
    else:
        start, end = window
        ref = s2_date.isoformat() if s2_date else "none (S2 missing)"
        text = f"{S1_COLLECTION} acquisition nearest in time to the selected S2 acquisition (date {ref}), any orbit direction, within the NISAR window {start.isoformat()}..{end.isoformat()}."
    return {"start": start, "end": end, "text": text + base}


# ---------------------------------------------------------------------------
# Earth Engine access (mocked in tests)
# ---------------------------------------------------------------------------
def aoi_geometry(ee, bbox: list[float]):
    return ee.Geometry.Rectangle(bbox, "EPSG:4326", False)


def _granules(ee, collection, props: list[str]) -> list[dict]:
    """One getInfo: id, UTC date and properties of every image in an (already filtered) collection."""
    cols = {
        "id": collection.aggregate_array("system:index"),
        "t": collection.aggregate_array("system:time_start"),
    }
    for p in props:
        cols[p] = collection.aggregate_array(p)
    info = ee.Dictionary(cols).getInfo()
    out = []
    for i, gid in enumerate(info["id"]):
        g = {"id": gid, "date": datetime.fromtimestamp(info["t"][i] / 1000, UTC).date().isoformat()}
        g.update({p: info[p][i] for p in props})
        out.append(g)
    return out


def s2_collection(ee, geom, start: date, end: date):
    return (
        ee.ImageCollection(S2_COLLECTION)
        .filterBounds(geom)
        .filterDate(start.isoformat(), (end + timedelta(days=1)).isoformat())
    )


def s1_collection(ee, geom, start: date, end: date):
    return (
        ee.ImageCollection(S1_COLLECTION)
        .filterBounds(geom)
        .filterDate(start.isoformat(), (end + timedelta(days=1)).isoformat())
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
    )


def fetch_s2_acquisitions(ee, geom, start: date, end: date) -> list[dict]:
    col = s2_collection(ee, geom, start, end)
    granules = _granules(
        ee, col, ["SPACECRAFT_NAME", "SENSING_ORBIT_NUMBER", "CLOUDY_PIXEL_PERCENTAGE"]
    )
    acqs = group_acquisitions(granules, ("SPACECRAFT_NAME", "SENSING_ORBIT_NUMBER"))
    tile_cloud = {g["id"]: g["CLOUDY_PIXEL_PERCENTAGE"] for g in granules}
    for a in acqs:
        a["granule_cloudy_pixel_pct"] = {i: tile_cloud[i] for i in a["ids"]}
        a.update(s2_aoi_stats(ee, geom, a["ids"]))
    return acqs


def s2_aoi_stats(ee, geom, ids: list[str]) -> dict:
    """AOI coverage %, cloud % of imaged pixels and obscured % (cloud or not imaged) from SCL."""
    scl = ee.ImageCollection([ee.Image(f"{S2_COLLECTION}/{i}") for i in ids]).mosaic().select("SCL")
    imaged = scl.gte(0).unmask(0).rename("imaged")
    cloud = scl.remap(SCL_CLOUD_CLASSES, [1] * len(SCL_CLOUD_CLASSES), 0).unmask(0).rename("cloud")
    stats = (
        imaged.addBands(cloud)
        .reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=STATS_SCALE_M, maxPixels=1e9)
        .getInfo()
    )
    return aoi_fractions(stats.get("imaged"), stats.get("cloud"))


def aoi_fractions(imaged: float | None, cloud: float | None) -> dict:
    """Turn AOI-mean fractions into percentages; None stays None (reported, never zero-filled)."""
    if imaged is None or cloud is None:
        return {"coverage_pct": None, "cloud_pct": None, "obscured_pct": None}
    cloud_pct = 100.0 * cloud / imaged if imaged > 0 else None
    return {
        "coverage_pct": round(100.0 * imaged, 2),
        "cloud_pct": round(cloud_pct, 2) if cloud_pct is not None else None,
        "obscured_pct": round(100.0 * (1.0 - (imaged - cloud)), 2),
    }


def fetch_s1_acquisitions(ee, geom, start: date, end: date) -> list[dict]:
    col = s1_collection(ee, geom, start, end)
    granules = _granules(
        ee, col, ["platform_number", "relativeOrbitNumber_start", "orbitProperties_pass"]
    )
    for g in granules:
        g["pass"] = g.pop("orbitProperties_pass")
    return group_acquisitions(granules, ("platform_number", "relativeOrbitNumber_start", "pass"))


def s1_coverage(ee, geom, ids: list[str]) -> float | None:
    vv = ee.ImageCollection([ee.Image(f"{S1_COLLECTION}/{i}") for i in ids]).mosaic().select("VV")
    stats = (
        vv.mask()
        .gt(0)
        .unmask(0)
        .rename("imaged")
        .reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=STATS_SCALE_M, maxPixels=1e9)
        .getInfo()
    )
    v = stats.get("imaged")
    return round(100.0 * v, 2) if v is not None else None


def layer_image(ee, layer: str, ids: list[str], geom, vis: dict):
    coll = S2_COLLECTION if layer == "s2" else S1_COLLECTION
    img = ee.ImageCollection([ee.Image(f"{coll}/{i}") for i in ids]).mosaic().clip(geom)
    return img.visualize(**vis)


# ---------------------------------------------------------------------------
# XYZ tiles
# ---------------------------------------------------------------------------
def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def tile_range(bbox: list[float], zmin: int, zmax: int) -> list[tuple[int, int, int]]:
    """All (z, x, y) XYZ tiles intersecting the bbox [W, S, E, N]."""
    w, s, e, n = bbox
    tiles = []
    for z in range(zmin, zmax + 1):
        x0, y0 = lonlat_to_tile(w, n, z)
        x1, y1 = lonlat_to_tile(e, s, z)
        tiles += [(z, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
    return tiles


def write_tiles(
    fetcher, tiles: list[tuple[int, int, int]], out_dir: Path, workers: int = 8
) -> dict:
    """Fetch PNG tiles with an EE TileFetcher; failures are counted, never replaced."""

    def one(t):
        z, x, y = t
        try:
            data = fetcher.fetch_tile(x=x, y=y, z=z)
        except Exception as exc:  # noqa: BLE001 - recorded per tile, not hidden
            return t, str(exc)[:200]
        dest = out_dir / str(z) / str(x) / f"{y}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return t, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, tiles))
    failed = [{"z": t[0], "x": t[1], "y": t[2], "error": err} for t, err in results if err]
    return {"requested": len(tiles), "written": len(tiles) - len(failed), "failed": failed}


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
def layer_entry(
    layer: str, rule: dict, acq: dict | None, n_candidates: int, vis: dict, aoi: str
) -> dict:
    """Manifest entry for one panel. No acquisition -> status 'missing' with the reason."""
    entry = {
        "collection": S2_COLLECTION if layer == "s2" else S1_COLLECTION,
        "selection_rule": rule["text"],
        "window": {"start": rule["start"].isoformat(), "end": rule["end"].isoformat()},
        "candidates_considered": n_candidates,
        "vis": vis,
    }
    if acq is None:
        entry.update(
            status="missing",
            reason=f"no acquisition in {entry['collection']} met the rule ({n_candidates} candidate acquisitions in the window)",
            scene_ids=[],
            date=None,
            cloud_pct=None,
            tile_template=None,
        )
        return entry
    entry.update(
        status="cached",
        scene_ids=acq["ids"],
        date=acq["date"],
        tile_template=f"local_cache/{aoi}/tiles/{layer}/{{z}}/{{x}}/{{y}}.png",
    )
    if layer == "s2":
        entry.update(
            spacecraft=acq.get("SPACECRAFT_NAME"),
            relative_orbit=acq.get("SENSING_ORBIT_NUMBER"),
            cloud_pct=acq.get("cloud_pct"),
            coverage_pct=acq.get("coverage_pct"),
            obscured_pct=acq.get("obscured_pct"),
            granule_cloudy_pixel_pct=acq.get("granule_cloudy_pixel_pct"),
        )
    else:
        entry.update(
            platform=acq.get("platform_number"),
            relative_orbit=acq.get("relativeOrbitNumber_start"),
            orbit_pass=acq.get("pass"),
            cloud_pct=None,  # C-band SAR images through cloud
            coverage_pct=acq.get("coverage_pct"),
        )
    return entry


def select(
    aoi: str,
    s2_acqs: list[dict],
    s1_acqs: list[dict],
    event: date,
    window: tuple[date, date],
    orbit: dict | None,
) -> dict:
    """Apply the stated rules to already-fetched acquisitions (pure)."""
    r2 = s2_rule(aoi, event, window)
    s2_cands = in_window(s2_acqs, r2["start"], r2["end"])
    s2 = least_cloudy(s2_cands)
    s2_date = date.fromisoformat(s2["date"]) if s2 else None
    r1 = s1_rule(aoi, event, window, orbit, s2_date)
    s1_cands = in_window(s1_acqs, r1["start"], r1["end"])
    if aoi == QUAKE_AOI:
        s1 = nearest_after(s1_cands, event, orbit["pass"])
    else:
        s1 = nearest_to(s1_cands, s2_date) if s2_date else None
    return {"s2": (r2, s2, len(s2_cands)), "s1": (r1, s1, len(s1_cands))}


def build_manifest(
    aoi: str,
    config_key: str,
    bbox: list[float],
    event: date,
    window,
    orbit,
    picks: dict,
    zoom: tuple[int, int],
    vis: dict,
    tiles: dict,
) -> dict:
    layers = {}
    for layer, name in (("s2", "optical_s2"), ("s1", "cband_s1")):
        rule, acq, n = picks[layer]
        entry = layer_entry(layer, rule, acq, n, vis[layer], aoi)
        if layer in tiles:
            entry["tiles"] = tiles[layer]
        layers[name] = entry
    return {
        "aoi": aoi,
        "config_key": config_key,
        "bbox_wsen": bbox,
        "bbox_source": f"config/bailasar.yaml aois.{config_key}",
        "event_date": event.isoformat(),
        "nisar_window": [window[0].isoformat(), window[1].isoformat()],
        "nisar_coevent_orbit": orbit if aoi == QUAKE_AOI else None,
        "zoom": {"min": zoom[0], "max": zoom[1]},
        "tile_scheme": "XYZ (Web Mercator, y from the north), PNG, transparent outside the AOI and where no data",
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "scripts/prestage_tiles.py",
        "layers": layers,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--aoi", required=True, choices=sorted(AOI_KEYS))
    p.add_argument("--zoom-min", type=int, default=9)
    p.add_argument("--zoom-max", type=int, default=13)
    p.add_argument(
        "--s2-max",
        type=float,
        default=3000.0,
        help="display stretch: S2 SR reflectance x1e4 mapped to white",
    )
    p.add_argument(
        "--s1-min-db", type=float, default=-25.0, help="display stretch: VV dB mapped to black"
    )
    p.add_argument(
        "--s1-max-db", type=float, default=0.0, help="display stretch: VV dB mapped to white"
    )
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--dry-run", action="store_true", help="select and print only; write nothing")
    return p.parse_args(argv)


def _print_pick(name: str, entry: dict) -> None:
    if entry["status"] == "missing":
        print(f"{name}: MISSING - {entry['reason']}")
        return
    extra = ""
    if "obscured_pct" in entry:
        extra = f" cloud%={entry['cloud_pct']} (of imaged AOI) coverage%={entry['coverage_pct']} obscured%={entry['obscured_pct']}"
    else:
        extra = f" pass={entry['orbit_pass']} rel_orbit={entry['relative_orbit']} coverage%={entry['coverage_pct']}"
    print(
        f"{name}: date={entry['date']}{extra} (measured; {entry['candidates_considered']} candidate acquisitions)"
    )
    for sid in entry["scene_ids"]:
        print(f"  {sid}")


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.zoom_min > args.zoom_max:
        raise SystemExit("--zoom-min must be <= --zoom-max")
    sys.path.insert(0, str(ROOT))
    load_env(ROOT / ".env")
    import ee

    from gee_math.ee_session import init_ee

    init_ee()
    config_key, bbox = load_aoi(args.aoi)
    event = load_event_date()
    gate = load_gate()
    window = nisar_window(gate)
    orbit = coevent_orbit(gate) if args.aoi == QUAKE_AOI else None
    geom = aoi_geometry(ee, bbox)

    q_start = min(window[0], event + timedelta(days=1))
    q_end = max(window[1], event + timedelta(days=QUAKE_S2_WINDOW_DAYS))
    s2_acqs = (
        fetch_s2_acquisitions(ee, geom, q_start, q_end)
        if args.aoi != QUAKE_AOI
        else fetch_s2_acquisitions(
            ee, geom, event + timedelta(days=1), event + timedelta(days=QUAKE_S2_WINDOW_DAYS)
        )
    )
    s1_acqs = fetch_s1_acquisitions(ee, geom, window[0], window[1])
    picks = select(args.aoi, s2_acqs, s1_acqs, event, window, orbit)
    if picks["s1"][1] is not None:
        picks["s1"][1]["coverage_pct"] = s1_coverage(ee, geom, picks["s1"][1]["ids"])

    vis = {
        "s2": {"bands": ["B4", "B3", "B2"], "min": 0, "max": args.s2_max},
        "s1": {"bands": ["VV"], "min": args.s1_min_db, "max": args.s1_max_db},
    }
    zoom = (args.zoom_min, args.zoom_max)
    tiles: dict = {}
    out_root = CACHE_DIR / args.aoi / "tiles"
    if not args.dry_run:
        tile_list = tile_range(bbox, *zoom)
        for layer in ("s2", "s1"):
            acq = picks[layer][1]
            if acq is None:
                continue
            mapid = layer_image(ee, layer, acq["ids"], geom, vis[layer]).getMapId()
            print(f"{layer}: fetching {len(tile_list)} tiles z{zoom[0]}-{zoom[1]} ...", flush=True)
            tiles[layer] = write_tiles(
                mapid["tile_fetcher"], tile_list, out_root / layer, args.workers
            )
            t = tiles[layer]
            print(
                f"{layer}: wrote {t['written']}/{t['requested']} tiles, {len(t['failed'])} failed"
            )

    manifest = build_manifest(
        args.aoi, config_key, bbox, event, window, orbit, picks, zoom, vis, tiles
    )
    for name, entry in manifest["layers"].items():
        _print_pick(name, entry)
    if args.dry_run:
        print("dry run: nothing written")
        return 0
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"manifest: {(out_root / 'manifest.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
