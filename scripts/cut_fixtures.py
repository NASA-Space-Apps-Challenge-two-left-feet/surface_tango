"""Cut unchanged windows from a local real-data cube; never fetch data."""

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE_KEYS = {
    "gunw_coherence": "gunw_coherence_pre",
    "slope_deg": "fabdem_slope",
    "rain_15d_mm": "chirps_15d",
    "agb_mgha": "esa_agb",
}


def path_component(value):
    """Keep user-supplied names within their designated directories."""
    if not value or value in {".", ".."} or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise argparse.ArgumentTypeError("use only letters, digits, underscores and hyphens")
    return value


def cut_fixture(args):
    """Validate and serialize a real window and its recorded evidence."""
    cache = ROOT / "local_cache"
    cube = cache / args.aoi / "antioquia_sar_cube.zarr"
    if not cache.is_dir():
        raise ValueError("local_cache/ is absent; a human must build or download the real cache")
    if not cube.is_dir():
        raise ValueError(f"source cube is absent: {cube}")
    if args.row < 0 or args.col < 0 or args.size <= 0:
        raise ValueError("row and col must be nonnegative; size must be positive")
    names = args.vars
    if len(set(names)) != len(names):
        raise ValueError("variable names must be unique")
    output = ROOT / "tests" / "fixtures" / args.aoi
    target = output / f"{args.name}.npz"
    sidecar = target.with_suffix(".provenance.json")
    if target.exists() or sidecar.exists():
        raise ValueError("fixture already exists; choose a new --name for human review")
    with xr.open_zarr(cube, chunks=None, mask_and_scale=False) as dataset:
        recorded = dataset.attrs.get("nisar_provenance")
        provenance = json.loads(recorded) if isinstance(recorded, str) else recorded
        if not isinstance(provenance, dict):
            raise ValueError("cube must have a mapping in its nisar_provenance attribute")
        arrays = {}
        sources = {}
        for name in names:
            if name not in dataset.data_vars:
                raise ValueError(f"variable absent from cube: {name}")
            variable = dataset[name]
            if variable.dims != ("y", "x"):
                raise ValueError(f"{name}: expected spatial dimensions (y, x)")
            if args.row + args.size > variable.sizes["y"] or (
                args.col + args.size > variable.sizes["x"]
            ):
                raise ValueError(f"window extends beyond {name}")
            key = PROVENANCE_KEYS.get(name, name)
            if key not in provenance:
                raise ValueError(f"no recorded provenance for {name} (key {key})")
            sources[name] = provenance[key]
            arrays[name] = variable.isel(
                y=slice(args.row, args.row + args.size),
                x=slice(args.col, args.col + args.size),
            ).values
            if sources[name] == "missing" and not np.isnan(arrays[name]).all():
                raise ValueError(f"{name}: values contradict recorded missing provenance")
        if all(np.isnan(array).all() for array in arrays.values()):
            raise ValueError("window is entirely NaN; no fixture written")
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **arrays)
    payload = buffer.getvalue()
    if len(payload) >= 1_000_000:
        raise ValueError("fixture must be under 1 MB; choose a smaller window or fewer variables")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    metadata = {
        "source_cube": cube.relative_to(ROOT).as_posix(),
        "variables": names,
        "window": {"row": args.row, "col": args.col, "size": args.size},
        "nisar_provenance": provenance,
        "nisar_provenance_attribute": recorded,
        "variable_provenance": sources,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "cut_time_utc": datetime.now(UTC).isoformat(),
        "git_commit": commit,
    }
    serialized = json.dumps(metadata, indent=2, ensure_ascii=False) + "\n"
    output.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(payload)
    with sidecar.open("x", encoding="utf-8") as handle:
        handle.write(serialized)
    print(f"Wrote {target.relative_to(ROOT)} and {sidecar.relative_to(ROOT)}; review before commit")


def main():
    """Expose the local cutter as a command line tool."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", required=True, type=path_component)
    parser.add_argument("--name", required=True, type=path_component)
    parser.add_argument("--row", required=True, type=int)
    parser.add_argument("--col", required=True, type=int)
    parser.add_argument("--size", required=True, type=int)
    parser.add_argument("--vars", required=True, nargs="+")
    args = parser.parse_args()
    try:
        cut_fixture(args)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"Cannot cut fixture: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
