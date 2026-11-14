"""Hour-2 data gate: discover the NISAR L2 granules that exist over the three BailaSAR AOIs.

    uv run python scripts/discover_nisar_colombia.py                # writes the gate catalog
    uv run python scripts/discover_nisar_colombia.py --start 2026-06-17 --end 2026-11-14

Read-only (ASF search is public; no downloads). Writes `nisar_colombia_granules_2026.json` at
the repo root (committed: it is the gate evidence) and prints the quake R/C/K selection.
AOIs come from `config/bailasar.yaml` (`aois:`), never from constants here.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

import asf_search as asf
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "bailasar.yaml"
OUT_CATALOG = ROOT / "nisar_colombia_granules_2026.json"
PRODUCTS = ["GCOV", "GUNW", "GOFF"]
EVENT_DATE = date(2026, 8, 10)  # Aug 10 2026 quake (validation/event_facts.json)

# NISAR_L2_<PR|UR>_<PRODUCT>_..._<POL: SH or DHDH>[_A]_<t1>_<t1stop>[_<t2>_<t2stop>]_...
NAME_RE = re.compile(
    r"NISAR_L2_(?P<stream>[A-Z]{2})_(?P<product>[A-Z]{4})_.*?_(?P<pol>[A-Z]{2,4})_(?:[A-Z]_)?"
    r"(?P<t1>\d{8})T\d{6}_\d{8}T\d{6}(?:_(?P<t2>\d{8})T\d{6}_\d{8}T\d{6})?"
)


def load_aois() -> dict[str, list[float]]:
    aois = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["aois"]
    missing = [k for k, v in aois.items() if not v]
    if missing:
        raise SystemExit(f"AOI bbox not set in config/bailasar.yaml: {missing}")
    return aois


def _iso(s: str | None) -> str | None:
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if s else None


def parse_name(scene: str) -> dict:
    """Stream (PR provisional, UR urgent response, ...), product, polarization and dates."""
    m = NAME_RE.search(scene)
    if not m:
        return {
            "stream": None,
            "product": None,
            "polarization": None,
            "date_1": None,
            "date_2": None,
        }
    d = m.groupdict()
    return {
        "stream": d["stream"],
        "product": d["product"],
        "polarization": d["pol"],
        "date_1": _iso(d["t1"]),
        "date_2": _iso(d["t2"]),
    }


def granule_record(result) -> dict:
    p = result.properties
    rec = {
        "scene_name": p.get("sceneName"),
        "processing_level": p.get("processingLevel"),
        "crid": p.get("crid"),
        "track": p.get("pathNumber"),
        "frame": p.get("frameNumber"),
        "flight_direction": p.get("flightDirection"),
        "start_time": p.get("startTime"),
        "stop_time": p.get("stopTime"),
        "url": p.get("url"),
    }
    rec.update(parse_name(rec["scene_name"] or ""))
    return rec


def search_aoi(bbox: list[float], start: str, end: str) -> list[dict]:
    w, s, e, n = bbox
    wkt = f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"
    results = asf.geo_search(
        dataset="NISAR",
        processingLevel=PRODUCTS,
        intersectsWith=wkt,
        start=start,
        end=end,
        maxResults=5000,
    )
    return sorted((granule_record(r) for r in results), key=lambda r: r["start_time"] or "")


def select_quake_triplet(gunw: list[dict], track: int) -> dict:
    """R = last pre-event pair, C = pair spanning the event, K = pre-event pair before R.

    Uses the provisional stream (PR) and records baselines so a mismatch is never hidden.
    """
    pairs = [
        g
        for g in gunw
        if g["track"] == track and g["date_1"] and g["date_2"] and g["stream"] == "PR"
    ]
    dated = [(date.fromisoformat(g["date_1"]), date.fromisoformat(g["date_2"]), g) for g in pairs]
    co = [x for x in dated if x[0] < EVENT_DATE <= x[1]]
    pre = sorted([x for x in dated if x[1] < EVENT_DATE], key=lambda x: x[1])
    out = {"track": track, "R": None, "C": None, "K": None, "baseline_days": {}}
    if co:
        out["C"] = co[0][2]["scene_name"]
        out["baseline_days"]["C"] = (co[0][1] - co[0][0]).days
    if pre:
        r = pre[-1]
        out["R"] = r[2]["scene_name"]
        out["baseline_days"]["R"] = (r[1] - r[0]).days
        older = [x for x in pre if x[1] <= r[0]]
        if older:
            k = older[-1]
            out["K"] = k[2]["scene_name"]
            out["baseline_days"]["K"] = (k[1] - k[0]).days
    out["baseline_mismatch"] = len(set(out["baseline_days"].values())) > 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", default="2026-06-17")
    ap.add_argument("--end", default="2026-11-14T23:59:59Z")
    args = ap.parse_args()

    catalog: dict = {"window": [args.start, args.end], "products": PRODUCTS, "aois": {}}
    for key, bbox in load_aois().items():
        granules = search_aoi(bbox, args.start, args.end)
        counts = Counter(g["processing_level"] for g in granules)
        streams = Counter(g["stream"] for g in granules)
        catalog["aois"][key] = {
            "bbox": bbox,
            "counts": dict(counts),
            "streams": dict(streams),
            "granules": granules,
        }
        print(f"{key}: {len(granules)} granules {dict(counts)} streams {dict(streams)}")

    quake = [
        g
        for g in catalog["aois"]["2_eje_cafetero_quake"]["granules"]
        if g["processing_level"] == "GUNW"
    ]
    tracks = sorted({g["track"] for g in quake if g["track"] is not None})
    catalog["quake_triplets"] = [select_quake_triplet(quake, t) for t in tracks]
    for t in catalog["quake_triplets"]:
        print(
            f"quake track {t['track']}: R={t['R']}\n  C={t['C']}\n  K={t['K']}\n"
            f"  baselines(days)={t['baseline_days']} mismatch={t['baseline_mismatch']}"
        )

    OUT_CATALOG.write_text(json.dumps(catalog, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT_CATALOG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
