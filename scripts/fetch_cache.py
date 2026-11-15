#!/usr/bin/env python3
"""Download, verify and assemble the public cache release. No credentials, no generated fallback.

    uv run python scripts/fetch_cache.py --repo owner/name --tag release-tag [--force]
Alternatively set BAILASAR_REPO and BAILASAR_RELEASE_TAG.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from cache_release import assemble, require_valid, verify_manifest, verify_parts  # noqa: E402

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
RETRIES = 3


def not_cached(message: str) -> SystemExit:
    return SystemExit(f"not cached: {message}")


def download(base: str, name: str, dest_dir: Path) -> Path:
    dest = dest_dir / name
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(f"{base}/{name}", timeout=120) as response:
                dest.write_bytes(response.read())
            return dest
        except (urllib.error.URLError, TimeoutError) as error:
            client_error = isinstance(error, urllib.error.HTTPError) and error.code < 500
            if client_error or attempt == RETRIES:
                raise not_cached(f"release asset unavailable: {name} ({error})") from None
            time.sleep(2 * attempt)
    raise AssertionError("unreachable")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=os.environ.get("BAILASAR_REPO", ""))
    parser.add_argument("--tag", default=os.environ.get("BAILASAR_RELEASE_TAG", ""))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    if not REPO_RE.match(args.repo):
        raise not_cached("--repo or BAILASAR_REPO must specify owner/name")
    if not args.tag:
        raise not_cached("--tag or BAILASAR_RELEASE_TAG is required")
    # Encode the tag as a single URL segment, including tags that contain slashes.
    base = f"https://github.com/{args.repo}/releases/download/{quote(args.tag, safe='')}"

    with tempfile.TemporaryDirectory() as tmp:
        parts_dir = Path(tmp)
        manifest_path = download(base, "cache_manifest.json", parts_dir)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            # Validate names before constructing any local path or download URL.
            errors = verify_manifest(manifest)
            if errors:
                raise ValueError("; ".join(errors))
        except (OSError, ValueError) as error:
            raise not_cached(f"invalid manifest: {error}") from None
        for part in manifest["parts"]:
            download(base, part["name"], parts_dir)
        try:
            require_valid(verify_parts(manifest, parts_dir))
            assemble(manifest, parts_dir, ROOT / "local_cache", args.force)
        except (OSError, ValueError, KeyError) as error:
            raise not_cached(str(error)) from None
    print("cache fetch: verified and assembled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
