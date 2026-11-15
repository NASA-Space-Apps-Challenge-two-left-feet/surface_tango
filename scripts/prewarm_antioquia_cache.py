"""Antioquia / Aburrá Valley cache warmer wrapper.

Delegates to the unified cache builder in scripts/build_cache.py for Aburrá.
Preserves existing functions for backward compatibility with Docker compose and MCP tools.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_cache import build_cache_for_aoi  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent.parent / "local_cache" / "aburra"
COG_DIR = CACHE_DIR / "cogs"
ZARR_PATH = CACHE_DIR / "aburra_sar_cube.zarr"
MANIFEST_PATH = CACHE_DIR / "manifest.json"


def build_antioquia_offline_cube() -> Path:
    """Warps and stages the Aburrá Valley multi-hazard cache cube."""
    return build_cache_for_aoi("aburra")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prewarm Aburrá Valley cache (legacy wrapper)")
    parser.parse_args()
    build_antioquia_offline_cube()


if __name__ == "__main__":
    main()
