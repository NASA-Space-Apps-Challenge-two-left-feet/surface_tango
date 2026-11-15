"""Audit public Armenia boundaries without repairing geometry or assigning damage labels.

Raw source responses and derived CSV/map artifacts stay in ignored local_cache/.
An optional existing snapshot permits offline reproduction. No frozen parameters
are read or changed; strictly positive intersections are diagnostic flags, not
scientific acceptance thresholds. All records are from the public source.
"""

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pyproj
import shapely
from matplotlib.lines import Line2D
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.strtree import STRtree
from shapely.validation import explain_validity

ROOT = Path(__file__).resolve().parents[1]
SERVICE = "https://pruebassig.igac.gov.co/server/rest/services/SIG_QUINDIO/Ordenamiento_territorial/MapServer"
WHERE = "IDMUNICIPIO='63001'"
SOURCE = "https://www.armenia.gov.co/comenzaron-visitas-y-ensayos-estructurales-en-edificios-afectados-por-el-sismo-en-armenia"


def normalized_name(value):
    """Normalize accents, case, punctuation and spaces only; never remove name tokens."""
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).upper()
    return re.sub(r"[^A-Z0-9]+", " ", text).strip()


def save_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def collect(snapshot):
    snapshot.mkdir(parents=True, exist_ok=False)
    requests = []

    def get(filename, layer, operation="", **params):
        url = f"{SERVICE}/{layer}{operation}?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=60) as response:
            raw = response.read()
        data = json.loads(raw)
        if "error" in data:
            raise RuntimeError(f"Source error for {filename}: {data['error']}")
        (snapshot / filename).write_bytes(raw)
        requests.append({"file": filename, "url": url, "sha256": hashlib.sha256(raw).hexdigest()})
        return data

    get("metadata.json", 1, f="pjson")
    count = get("count-before.json", 1, "/query", f="json", where=WHERE, returnCountOnly="true")[
        "count"
    ]
    ids = sorted(
        get("ids-before.json", 1, "/query", f="json", where=WHERE, returnIdsOnly="true")[
            "objectIds"
        ]
    )
    if len(ids) != count or len(set(ids)) != count:
        raise RuntimeError("Source count/IDs do not reconcile")
    for page, start in enumerate(range(0, len(ids), 100)):
        get(
            f"barrios-{page:03d}.geojson",
            1,
            "/query",
            f="geojson",
            where=WHERE,
            objectIds=",".join(map(str, ids[start : start + 100])),
            outFields="OBJECTID,IDMUNICIPIO,NOMBRE,NOCOMUNA",
            outSR=4326,
            returnGeometry="true",
        )
    get("perimeter-metadata.json", 3, f="pjson")
    get(
        "perimeter.geojson",
        3,
        "/query",
        f="geojson",
        where="1=1",
        outFields="*",
        outSR=4326,
        returnGeometry="true",
    )
    after_ids = sorted(
        get("ids-after.json", 1, "/query", f="json", where=WHERE, returnIdsOnly="true")["objectIds"]
    )
    after_count = get(
        "count-after.json", 1, "/query", f="json", where=WHERE, returnCountOnly="true"
    )["count"]
    if ids != after_ids or count != after_count:
        raise RuntimeError("Source membership changed during retrieval; retry a new snapshot")
    manifest = {
        "accessed_utc": datetime.now(UTC).isoformat(),
        "service": SERVICE,
        "where": WHERE,
        "requests": requests,
        "note": "Membership stable; service does not guarantee an atomic geometry snapshot.",
    }
    (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def audit(snapshot):
    manifest = json.loads((snapshot / "manifest.json").read_text())
    for request in manifest["requests"]:
        if (
            hashlib.sha256((snapshot / request["file"]).read_bytes()).hexdigest()
            != request["sha256"]
        ):
            raise RuntimeError("Snapshot checksum mismatch: " + request["file"])
    features = []
    for file in sorted(snapshot.glob("barrios-*.geojson")):
        data = json.loads(file.read_text())
        if data.get("exceededTransferLimit"):
            raise RuntimeError("Truncated feature page")
        features.extend(data["features"])
    ids = [f["properties"]["OBJECTID"] for f in features]
    expected = json.loads((snapshot / "ids-before.json").read_text())["objectIds"]
    if sorted(ids) != sorted(expected) or len(ids) != len(set(ids)):
        raise RuntimeError("Downloaded features do not reconcile to source IDs")
    if any(f["properties"]["IDMUNICIPIO"] != "63001" for f in features):
        raise RuntimeError("Non-Armenia records in filtered source")
    if not features:
        raise RuntimeError("Empty source cannot establish coverage")
    features.sort(key=lambda f: f["properties"]["OBJECTID"])
    project = Transformer.from_crs(4326, 9377, always_xy=True).transform
    rows, geometries = [], []
    for feature in features:
        props = feature["properties"]
        reason, geom, metric = "missing geometry", None, None
        try:
            if feature.get("geometry"):
                geom = shape(feature["geometry"])
                if not all(
                    math.isfinite(float(v)) for xy in shapely.get_coordinates(geom) for v in xy
                ):
                    reason = "nonfinite coordinates"
                elif geom.is_empty:
                    reason = "empty geometry"
                elif geom.geom_type not in {"Polygon", "MultiPolygon"}:
                    reason = "nonpolygon geometry"
                else:
                    metric = shapely.transform(geom, project, interleaved=False)
                    reason = explain_validity(metric)
                    if metric.area <= 0:
                        reason = "nonpositive area"
        except (ValueError, TypeError, shapely.GEOSException) as error:
            reason = str(error)
        valid = reason == "Valid Geometry"
        rows.append(
            {
                "snapshot_key": f"63001:igac:{props['OBJECTID']}",
                "objectid": props["OBJECTID"],
                "municipality": props["IDMUNICIPIO"],
                "source_name": props.get("NOMBRE") or "",
                "normalized_name": normalized_name(props.get("NOMBRE")),
                "commune": str(props.get("NOCOMUNA") or ""),
                "geometry_valid": valid,
                "geometry_reason": reason,
                "area_m2": metric.area if metric is not None else "",
                "damage_status": "unknown",
                "stable_official_id": "pending",
            }
        )
        geometries.append(metric if valid else None)
    groups = defaultdict(list)
    raw_groups = defaultdict(list)
    for row in rows:
        groups[row["normalized_name"]].append(row)
        raw_groups[row["source_name"]].append(row)
    duplicates = []
    for name, group in sorted(groups.items()):
        if len(group) > 1:
            duplicates.append(
                {
                    "normalized_name": name,
                    "source_names": " | ".join(sorted({r["source_name"] for r in group})),
                    "objectids": " | ".join(str(r["objectid"]) for r in group),
                    "communes": " | ".join(sorted({r["commune"] for r in group})),
                    "record_count": len(group),
                    "resolution": "manual_review_no_merge",
                }
            )
    for row in rows:
        row["normalized_name_record_count"] = len(groups[row["normalized_name"]])
        row["join_status"] = (
            "missing_name"
            if not row["normalized_name"]
            else "unique_name_only"
            if row["normalized_name_record_count"] == 1
            else "ambiguous_duplicate_name"
        )
    valid_indices = [i for i, g in enumerate(geometries) if g is not None]
    valid_geoms = [geometries[i] for i in valid_indices]
    tree = STRtree(valid_geoms)
    overlaps = []
    for a, geom in enumerate(valid_geoms):
        for b_value in tree.query(geom, predicate="intersects"):
            b = int(b_value)
            if b <= a:
                continue
            other = valid_geoms[b]
            intersection = geom.intersection(other)
            if intersection.area > 0:
                ra, rb = rows[valid_indices[a]], rows[valid_indices[b]]
                overlaps.append(
                    {
                        "objectid_a": ra["objectid"],
                        "name_a": ra["source_name"],
                        "objectid_b": rb["objectid"],
                        "name_b": rb["source_name"],
                        "intersection_m2": intersection.area,
                        "topologically_equal": geom.equals(other),
                    }
                )
    overlap_counts = Counter()
    for pair in overlaps:
        overlap_counts[pair["objectid_a"]] += 1
        overlap_counts[pair["objectid_b"]] += 1
    for row in rows:
        row["positive_area_overlap_pair_count"] = overlap_counts[row["objectid"]]
        row["scientific_acceptance"] = "pending_provenance_coverage_and_topology_review"
    perimeter_data = json.loads((snapshot / "perimeter.geojson").read_text())
    perimeter_geoms = [
        shapely.transform(shape(f["geometry"]), project, interleaved=False)
        for f in perimeter_data["features"]
        if f.get("geometry")
    ]
    perimeter_valid = (
        bool(perimeter_geoms)
        and not perimeter_data.get("exceededTransferLimit", False)
        and all(g.is_valid and not g.is_empty for g in perimeter_geoms)
    )
    coverage = {
        "perimeter_feature_count": len(perimeter_data["features"]),
        "perimeter_geometry_valid": perimeter_valid,
        "scope": "Same-service urban perimeter; not event-date legal/AOI acceptance.",
    }
    if perimeter_valid and valid_geoms:
        union = unary_union(valid_geoms)
        perimeter = unary_union(perimeter_geoms)
        coverage.update(
            {
                "valid_polygon_union_m2": union.area,
                "perimeter_m2": perimeter.area,
                "uncovered_perimeter_m2": perimeter.difference(union).area,
                "outside_perimeter_m2": union.difference(perimeter).area,
                "invalid_barrio_records_excluded": len(rows) - len(valid_geoms),
            }
        )
    candidates = []
    for evidence_name, issue in [
        ("Serranías", "named_damaged_dwelling"),
        ("Corbones", "building_between_two_neighborhoods"),
        ("Granada", "building_between_two_neighborhoods"),
    ]:
        matches = groups.get(normalized_name(evidence_name), [])
        candidates.append(
            {
                "reported_name": evidence_name,
                "normalized_name": normalized_name(evidence_name),
                "candidate_objectids": " | ".join(str(r["objectid"]) for r in matches),
                "candidate_source_names": " | ".join(r["source_name"] for r in matches),
                "candidate_communes": " | ".join(r["commune"] for r in matches),
                "match_count": len(matches),
                "candidate_geometry_valid": " | ".join(str(r["geometry_valid"]) for r in matches),
                "candidate_overlap_pair_counts": " | ".join(
                    str(r["positive_area_overlap_pair_count"]) for r in matches
                ),
                "name_match_status": "unique_normalized_name"
                if len(matches) == 1
                else "unresolved",
                "evidence_status": issue,
                "damage_label": "not_assigned",
                "source_date": "2026-11-11",
                "source_url": SOURCE,
                "decision": "review_geometry_and_provenance"
                if issue == "named_damaged_dwelling"
                else "do_not_assign_building_to_either_or_both_without_location",
            }
        )
    artifacts = snapshot / "audit"
    artifacts.mkdir(exist_ok=True)
    save_csv(artifacts / "neighborhood_crosswalk.csv", rows, list(rows[0]))
    save_csv(
        artifacts / "duplicate_names.csv",
        duplicates,
        ["normalized_name", "source_names", "objectids", "communes", "record_count", "resolution"],
    )
    save_csv(
        artifacts / "overlaps.csv",
        overlaps,
        ["objectid_a", "name_a", "objectid_b", "name_b", "intersection_m2", "topologically_equal"],
    )
    save_csv(artifacts / "damage_source_crosswalk.csv", candidates, list(candidates[0]))
    counts = Counter(row["geometry_reason"] for row in rows)
    summary = {
        "snapshot": str(snapshot),
        "accessed_utc": manifest["accessed_utc"],
        "source": SERVICE + "/1",
        "where": WHERE,
        "audit_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "versions": {
            "python": sys.version.split()[0],
            "shapely": shapely.__version__,
            "pyproj": pyproj.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "record_count": len(rows),
        "source_ids_reconciled": True,
        "unique_raw_names": len(raw_groups),
        "unique_normalized_names": len(groups),
        "missing_names": sum(not row["normalized_name"] for row in rows),
        "missing_communes": sum(not row["commune"].strip() for row in rows),
        "duplicate_normalized_name_groups_including_blank": len(duplicates),
        "duplicate_nonblank_name_groups": sum(bool(r["normalized_name"]) for r in duplicates),
        "duplicate_name_records": sum(r["record_count"] for r in duplicates),
        "valid_geometry_records": len(valid_geoms),
        "invalid_geometry_records": len(rows) - len(valid_geoms),
        "geometry_reasons": dict(counts),
        "positive_area_overlap_pairs_among_valid_records": len(overlaps),
        "topologically_equal_pairs": sum(r["topologically_equal"] for r in overlaps),
        "median_overlap_pair_m2": median([r["intersection_m2"] for r in overlaps])
        if overlaps
        else None,
        "largest_overlap_m2": max((r["intersection_m2"] for r in overlaps), default=0),
        "coverage": coverage,
        "candidate_matches": candidates,
        "decision": (
            "NOT_SCIENTIFICALLY_ACCEPTED: municipal adoption/vintage/terms "
            "and damage coverage pending"
        ),
        "no_geometry_repair": True,
        "no_dissolve_or_fuzzy_name_merge": True,
        "note": (
            "Positive-area intersections include floating-point slivers; "
            "no acceptance tolerance applied."
        ),
    }
    (artifacts / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, ax = plt.subplots(figsize=(9, 10))
    for i, feature in enumerate(features):
        if not feature.get("geometry"):
            continue
        try:
            g = shapely.transform(shape(feature["geometry"]), project, interleaved=False)
            parts = list(g.geoms) if g.geom_type == "MultiPolygon" else [g]
            color = "#c73737" if not rows[i]["geometry_valid"] else "#708da0"
            for part in parts:
                if part.geom_type == "Polygon":
                    x, y = part.exterior.xy
                    ax.plot(
                        x, y, color=color, linewidth=0.9 if not rows[i]["geometry_valid"] else 0.45
                    )
                    for interior in part.interiors:
                        x, y = interior.xy
                        ax.plot(x, y, color=color, linewidth=0.35)
            if rows[i]["normalized_name"] in {"SERRANIAS", "CORBONES", "GRANADA"}:
                point = g.representative_point()
                ax.scatter(point.x, point.y, color="#123661", s=14)
                ax.annotate(
                    rows[i]["source_name"],
                    (point.x, point.y),
                    xytext=(5, 5),
                    textcoords="offset points",
                    fontsize=8,
                )
        except (ValueError, TypeError, shapely.GEOSException):
            continue
    for perimeter_geom in perimeter_geoms:
        parts = (
            list(perimeter_geom.geoms)
            if perimeter_geom.geom_type == "MultiPolygon"
            else [perimeter_geom]
        )
        for part in parts:
            if part.geom_type == "Polygon":
                x, y = part.exterior.xy
                ax.plot(x, y, color="#8a68a5", linestyle="--", linewidth=0.9)
    ax.set_aspect("equal")
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.set_xlabel("EPSG:9377 easting (m)")
    ax.set_ylabel("EPSG:9377 northing (m)")
    ax.set_title(
        "Armenia boundary audit — source polygons, no repairs\n"
        "Government test-host candidate; event-date adoption unverified"
    )
    ax.legend(
        handles=[
            Line2D([0], [0], color="#8a68a5", linestyle="--", label="Same-service urban perimeter"),
            Line2D([0], [0], color="#708da0", label="Valid source geometry"),
            Line2D([0], [0], color="#c73737", label="Invalid source geometry"),
            Line2D(
                [0],
                [0],
                marker="o",
                linestyle="none",
                color="#123661",
                label="Damage-report name candidates; no labels assigned",
            ),
        ],
        loc="best",
        fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(artifacts / "boundary_audit.png", dpi=170)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, help="Reuse an existing snapshot offline")
    args = parser.parse_args()
    if args.snapshot:
        snapshot = args.snapshot.resolve()
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        snapshot = ROOT / "local_cache" / "ground_truth" / "armenia_igac" / stamp
        collect(snapshot)
    audit(snapshot)
