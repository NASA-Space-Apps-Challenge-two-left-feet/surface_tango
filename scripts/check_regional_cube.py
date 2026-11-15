"""Evaluate every packaged layer without starting a server or contacting the VM.

uv run python scripts/check_regional_cube.py --output reports/regional-cube-local.json
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import rasterio  # noqa: E402
import xarray as xr  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app as web  # noqa: E402


def evaluate():
    report = {
        "measurement": "measured",
        "environment": "local in-process; not a VM or network benchmark",
        "command": "uv run python scripts/check_regional_cube.py --output reports/regional-cube-local.json",
        "created_at": datetime.now(UTC).isoformat(),
        "regions": [],
        "errors": [],
    }
    with TestClient(web.app) as client:
        for region in web.cube_catalog()["regions"]:
            result = {"aoi": region["aoi"], "state": region["state"], "layers": []}
            for layer in region["layers"]:
                start = perf_counter()
                store, _ = web.cube_layer(region["aoi"], layer["id"])
                source_path = web.CACHE_ROOT / layer["source_file"]
                with rasterio.open(source_path) as src:
                    source = src.read(1, masked=True).astype("float32").filled(np.nan)
                with xr.open_zarr(store, group=layer["id"], consolidated=False, chunks=None) as ds:
                    equal = np.array_equal(source, ds.value.values, equal_nan=True)
                response = client.get(f"/api/cube/{region['aoi']}/{layer['id']}/preview.png")
                ok = (
                    equal
                    and response.status_code == 200
                    and response.content.startswith(b"\x89PNG")
                )
                if not ok:
                    report["errors"].append(f"{region['aoi']}/{layer['id']}")
                result["layers"].append(
                    {
                        "id": layer["id"],
                        "pixel_equality": equal,
                        "preview_status": response.status_code,
                        "elapsed_seconds": perf_counter() - start,
                        "source_file": layer["source_file"],
                        "provenance": layer["provenance"],
                        "pixels": layer["total_pixels"],
                    }
                )
            store = web.CACHE_ROOT / "regional-cubes" / f"{region['aoi']}.zarr"
            result["store_bytes"] = sum(p.stat().st_size for p in store.rglob("*") if p.is_file())
            report["regions"].append(result)
    report["passed"] = not report["errors"] and any(r["layers"] for r in report["regions"])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": result["passed"], "report": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
