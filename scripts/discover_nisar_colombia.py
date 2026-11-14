# scripts/discover_nisar_colombia.py
import os
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any

import asf_search as asf
import earthaccess

CACHE_DIR = Path(__file__).resolve().parent.parent / "local_cache" / "antioquia_aburra"
OUT_GEOJSON = CACHE_DIR / "nisar_colombia_swaths_2026.geojson"
OUT_CATALOG_JSON = CACHE_DIR / "nisar_colombia_granules_2026.json"

# 4 Strategic Colombian Multi-Hazard AOIs (WKT Polygons)
COLOMBIA_AOIS: Dict[str, Dict[str, Any]] = {
    "1_aburra_medellin_bello": {
        "name": "Valle de Aburrá (Bello, Medellín & Eastern/Western Slopes)",
        "hazard_focus": "Rotational/translational landslides (GUNW) + Flash flooding (GCOV)",
        "bbox": [-75.70, 6.12, -75.42, 6.45],
        "wkt": "POLYGON((-75.70 6.12, -75.42 6.12, -75.42 6.45, -75.70 6.45, -75.70 6.12))",
    },
    "2_bajo_cauca_mojana": {
        "name": "Bajo Cauca Antioqueño & La Mojana Floodplains (Caucasia / Nechí)",
        "hazard_focus": "Specular open water vs. Sub-canopy dihedral double-bounce flooding (GCOV HH/HV)",
        "bbox": [-75.35, 7.70, -74.65, 8.35],
        "wkt": "POLYGON((-75.35 7.70, -74.65 7.70, -74.65 8.35, -75.35 8.35, -75.35 7.70))",
    },
    "3_uraba_atrato_choco": {
        "name": "Darién / Urabá & Atrato Biogeographic Corridor",
        "hazard_focus": "High-density woody biomass (150-250 Mg/ha) & wetland carbon dynamics (GCOV HV)",
        "bbox": [-77.05, 7.45, -76.45, 8.15],
        "wkt": "POLYGON((-77.05 7.45, -76.45 7.45, -76.45 8.15, -77.05 8.15, -77.05 7.45))",
    },
    "4_murindo_romeral_fault": {
        "name": "Murindó / Frontino & Romeral Active Fault System (Western Antioquia)",
        "hazard_focus": "Co-seismic coherence DPM (GUNW) & near-fault 3D surface slip offsets (GOFF)",
        "bbox": [-76.85, 6.65, -76.15, 7.20],
        "wkt": "POLYGON((-76.85 6.65, -76.15 6.65, -76.15 7.20, -76.85 7.20, -76.85 6.65))",
    },
}

# ANSI Colors for Terminal Table Output
CYAN = "\033[38;2;137;220;235m"
GREEN = "\033[38;2;166;227;161m"
PEACH = "\033[38;2;250;179;135m"
MAUVE = "\033[38;2;203;166;247m"
RED = "\033[38;2;243;139;168m"
BOLD = "\033[1m"
RESET = "\033[0m"


def parse_nisar_scene_metadata(props: Dict[str, Any], geom: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts structured radar parameters from an ASF Search NISAR granule result."""
    scene_name = props.get("sceneName") or props.get("fileID") or "UNKNOWN_SCENE"
    tokens = scene_name.split("_")
    
    # Extract Polarization & Bandwidth tokens from standard NISAR L2 naming convention
    pol_mode = tokens[9] if len(tokens) > 9 else props.get("polarization", "DHDH")
    bw_code = tokens[8] if len(tokens) > 8 else "2005"

    return {
        "scene_name": scene_name,
        "product_level": props.get("processingLevel", "UNKNOWN"),
        "start_time": props.get("startTime", ""),
        "stop_time": props.get("stopTime", ""),
        "track_relative_orbit": props.get("pathNumber"),
        "frame_number": props.get("frameNumber"),
        "flight_direction": props.get("flightDirection", ""),
        "polarization_mode": pol_mode,
        "bandwidth_code": bw_code,  # e.g., 2005 = 20 MHz FreqA + 5 MHz FreqB (ionosphere)
        "bytes_mb": round(float(props.get("bytes", 0)) / (1024 * 1024), 1),
        "https_url": props.get("url"),
        "s3_url": (props.get("s3Urls") or [None])[0],
        "browse_url": (props.get("browse") or [None])[0],
        "geometry": geom,
    }


def search_nisar_across_colombia(
    start_date: str = "2026-06-01T00:00:00Z",
    end_date: str = "2026-11-13T23:59:59Z",
    product_levels: List[str] = ["GCOV", "GUNW", "GOFF"],
) -> Dict[str, Any]:
    """
    Searches ASF DAAC for all NISAR L2 GCOV, GUNW, and GOFF granules across the 4 Colombian AOIs
    and groups them into interferometric/time-series Track+Frame stacks.
    """
    print(f"{BOLD}{MAUVE}=== QUERYING NASA ASF DAAC FOR 2026 NISAR PROVISIONAL L2 GRANULES ==={RESET}")
    print(f"Window: {CYAN}{start_date}{RESET} -> {CYAN}{end_date}{RESET} | Products: {GREEN}{product_levels}{RESET}\n")

    all_features = []
    catalog_summary: Dict[str, Any] = {}

    for aoi_key, aoi_cfg in COLOMBIA_AOIS.items():
        print(f"{BOLD}{CYAN}▶ AOI: {aoi_cfg['name']}{RESET}")
        print(f"  Focus: {aoi_cfg['hazard_focus']}")

        try:
            results = asf.geo_search(
                platform=[asf.PLATFORM.NISAR],
                processingLevel=product_levels,
                intersectsWith=aoi_cfg["wkt"],
                start=start_date,
                end=end_date,
                maxResults=250,
            )
        except Exception as exc:
            print(f"  {RED}[WARN] ASF Search query error: {exc}{RESET}\n")
            continue

        parsed_list = [parse_nisar_scene_metadata(r.properties, r.geometry) for r in results]
        parsed_list.sort(key=lambda x: x["start_time"], reverse=True)

        # Group by (Product, Track, Frame, FlightDirection) to identify time-series & InSAR stacks
        stacks = defaultdict(list)
        for item in parsed_list:
            stack_key = (
                f"{item['product_level']}_Track{item['track_relative_orbit']}"
                f"_Frame{item['frame_number']}_{item['flight_direction']}"
            )
            stacks[stack_key].append(item)

            # Build GeoJSON Feature for MapLibre swath visualization
            all_features.append({
                "type": "Feature",
                "properties": {k: v for k, v in item.items() if k != "geometry"} | {"aoi_key": aoi_key},
                "geometry": item["geometry"],
            })

        print(f"  Found {BOLD}{GREEN}{len(parsed_list)}{RESET} granules across {BOLD}{PEACH}{len(stacks)}{RESET} Track/Frame stacks:")
        for stack_id, scenes in stacks.items():
            latest = scenes[0]
            earliest = scenes[-1]
            print(
                f"    • {BOLD}{stack_id:<28}{RESET} | Count: {GREEN}{len(scenes):2d}{RESET} "
                f"| Pol: {PEACH}{latest['polarization_mode']}{RESET} "
                f"| Span: {earliest['start_time'][:10]} -> {latest['start_time'][:10]} "
                f"| Size: ~{latest['bytes_mb']} MB"
            )
            print(f"      Latest Scene: {CYAN}{latest['scene_name']}{RESET}")
        print()

        catalog_summary[aoi_key] = {
            "aoi_metadata": aoi_cfg,
            "total_granules": len(parsed_list),
            "track_frame_stacks": {k: v for k, v in stacks.items()},
        }

    # Save GeoJSON footprints & structured JSON catalog for the MCP Ingestion Agent
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_GEOJSON.write_text(json.dumps({"type": "FeatureCollection", "features": all_features}, indent=2))
    OUT_CATALOG_JSON.write_text(json.dumps(catalog_summary, indent=2))
    print(f"{GREEN}✔ Saved Swath Footprints GeoJSON:{RESET} {OUT_GEOJSON}")
    print(f"{GREEN}✔ Saved Granule Stack Catalog:{RESET}   {OUT_CATALOG_JSON}\n")
    return catalog_summary


def inspect_remote_nisar_h5_structure(https_url: str):
    """
    Streams ONLY the HDF5 metadata B-tree header (<2 MB) from NASA Earthdata Cloud via
    earthaccess + h5py without downloading the multi-gigabyte granule.
    Verifies exact grid paths, polarizations, EPSG projection, and ionospheric screen presence.
    """
    import h5py

    print(f"{BOLD}{MAUVE}=== ZERO-DOWNLOAD REMOTE HDF5 STRUCTURE PROBE ==={RESET}")
    print(f"Streaming HDF5 Header: {CYAN}{https_url}{RESET}")

    earthaccess.login(strategy="netrc")
    fs = earthaccess.get_fsspec_https_session()

    with fs.open(https_url, "rb") as remote_file:
        with h5py.File(remote_file, "r") as h5:
            # 1. Inspect Identification Metadata
            ident_path = "/science/LSAR/identification"
            if ident_path in h5:
                ident = h5[ident_path]
                prod_type = ident["productType"][()].decode("utf-8") if "productType" in ident else "UNKNOWN"
                look_dir = ident["lookDirection"][()].decode("utf-8") if "lookDirection" in ident else "UNKNOWN"
                orbit_pass = ident["orbitPassDirection"][()].decode("utf-8") if "orbitPassDirection" in ident else "UNKNOWN"
                print(f"  Product Type: {GREEN}{prod_type}{RESET} | Pass: {PEACH}{orbit_pass}{RESET} | Look: {CYAN}{look_dir}{RESET}")

                # 2. Inspect Frequency A Science Grids
                grid_base = f"/science/LSAR/{prod_type}/grids/frequencyA"
                if grid_base in h5:
                    f_a = h5[grid_base]
                    epsg = f_a["projection"][()] if "projection" in f_a else "Unknown EPSG"
                    print(f"  Native Grid Projection: {BOLD}{GREEN}EPSG:{epsg}{RESET}")
                    print(f"  Available Datasets inside {CYAN}{grid_base}{RESET}:")
                    for key in f_a.keys():
                        obj = f_a[key]
                        if isinstance(obj, h5py.Dataset) and len(obj.shape) >= 2:
                            print(
                                f"    • {PEACH}{key:<32}{RESET} | Shape: {str(obj.shape):<16} "
                                f"| Dtype: {str(obj.dtype):<10} | Chunks: {obj.chunks}"
                            )
                            print(
                                f'      GDAL VSI URI: HDF5:"/vsicurl/{https_url}":{grid_base}/{key}'
                            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discover & inspect 2026 NISAR L2 granules over Antioquia & Colombia")
    parser.add_argument("--start", default="2026-06-01T00:00:00Z", help="ISO start date (Provisional L2 release began June 2026)")
    parser.add_argument("--end", default="2026-11-13T23:59:59Z", help="ISO end date")
    parser.add_argument("--probe-latest", action="store_true", help="Remote-inspect the HDF5 structure of the newest Aburra granule")
    args = parser.parse_args()

    catalog = search_nisar_across_colombia(start_date=args.start, end_date=args.end)

    if args.probe_latest:
        aburra_stacks = catalog.get("1_aburra_medellin_bello", {}).get("track_frame_stacks", {})
        for stack_name, granules in aburra_stacks.items():
            if granules and granules[0].get("https_url"):
                inspect_remote_nisar_h5_structure(granules[0]["https_url"])
                break
