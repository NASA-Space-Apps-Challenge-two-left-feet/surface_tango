#!/usr/bin/env python3
"""Download, verify and assemble the public cache release. No credentials, no generated fallback.

    uv run python scripts/fetch_cache.py --repo owner/name --tag release-tag [--force]
Alternatively set BAILASAR_REPO and BAILASAR_RELEASE_TAG.
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from cache_release import (  # noqa: E402
    assemble,
    cache_lock,
    preflight_destination,
    require_valid,
    verify_manifest,
    verify_parts,
)

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
RETRIES = 3
CHUNK_BYTES = 1024 * 1024
# Bound untrusted manifest downloads; manifests contain metadata, never tile bytes.
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_RETRY_WAIT = 60


def not_cached(message: str) -> SystemExit:
    return SystemExit(f"not cached: {message}")


def download(base: str, name: str, dest_dir: Path, max_bytes: int) -> Path:
    dest = dest_dir / name
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(f"{base}/{name}", timeout=120) as response:
                try:
                    output = dest.open("wb")
                except OSError as error:
                    raise not_cached(f"local write failed for {name}: {error}") from None
                try:
                    received = 0
                    while chunk := response.read(min(CHUNK_BYTES, max_bytes - received + 1)):
                        received += len(chunk)
                        if received > max_bytes:
                            raise ValueError(f"release asset exceeds size limit: {name}")
                        try:
                            output.write(chunk)
                        except OSError as error:
                            raise not_cached(f"local write failed for {name}: {error}") from None
                finally:
                    try:
                        output.close()
                    except OSError as error:
                        raise not_cached(f"local write failed for {name}: {error}") from None
            return dest
        except SystemExit:
            dest.unlink(missing_ok=True)
            raise
        except ValueError as error:
            dest.unlink(missing_ok=True)
            raise not_cached(str(error)) from None
        except (urllib.error.URLError, http.client.IncompleteRead, OSError) as error:
            dest.unlink(missing_ok=True)
            client_error = (
                isinstance(error, urllib.error.HTTPError)
                and error.code != 429
                and not 500 <= error.code < 600
            )
            if client_error or attempt == RETRIES:
                raise not_cached(f"release asset unavailable: {name} ({error})") from None
            wait = 2**attempt
            if isinstance(error, urllib.error.HTTPError):
                try:
                    value = error.headers.get("Retry-After", "")
                    try:
                        retry_after = float(value)
                    except ValueError:
                        retry_after = (
                            parsedate_to_datetime(value) - datetime.now(UTC)
                        ).total_seconds()
                    if math.isfinite(retry_after) and retry_after >= 0:
                        wait = retry_after
                except (ValueError, TypeError, AttributeError, OverflowError):
                    pass
            time.sleep(min(wait, MAX_RETRY_WAIT))
    raise AssertionError("unreachable")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=os.environ.get("BAILASAR_REPO", ""))
    parser.add_argument("--tag", default=os.environ.get("BAILASAR_RELEASE_TAG", ""))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--break-lock", action="store_true")
    args = parser.parse_args(argv)

    if not REPO_RE.match(args.repo):
        raise not_cached("--repo or BAILASAR_REPO must specify owner/name")
    if not args.tag:
        raise not_cached("--tag or BAILASAR_RELEASE_TAG is required")
    try:
        with cache_lock(ROOT / "local_cache", args.break_lock):
            return fetch(args)
    except (OSError, ValueError) as error:
        raise not_cached(str(error)) from None


def fetch(args) -> int:
    """Fetch while main holds the destination's exclusive writer lock."""
    destination = preflight_destination(ROOT / "local_cache", args.force)
    # Encode the tag as a single URL segment, including tags that contain slashes.
    base = f"https://github.com/{args.repo}/releases/download/{quote(args.tag, safe='')}"

    with tempfile.TemporaryDirectory() as tmp:
        parts_dir = Path(tmp)
        manifest_path = download(base, "cache_manifest.json", parts_dir, MAX_MANIFEST_BYTES)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            # Validate names before constructing any local path or download URL.
            errors = verify_manifest(manifest)
            if errors:
                raise ValueError("; ".join(errors))
        except (OSError, ValueError) as error:
            raise not_cached(f"invalid manifest: {error}") from None
        for part in manifest["parts"]:
            download(base, part["name"], parts_dir, part["size_bytes"])
        try:
            require_valid(verify_parts(manifest, parts_dir))
            assemble(manifest, parts_dir, destination, args.force, _lock_held=True)
        except (OSError, ValueError, KeyError) as error:
            raise not_cached(str(error)) from None
    print("cache fetch: verified and assembled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
