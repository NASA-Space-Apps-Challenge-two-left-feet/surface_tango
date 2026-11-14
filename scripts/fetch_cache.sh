#!/usr/bin/env bash
# Public release download only. No credentials, API calls, or generated fallback.
# Usage: bash scripts/fetch_cache.sh --repo owner/name --tag release-tag [--force]
# Alternatively set BAILASAR_REPO and BAILASAR_RELEASE_TAG.
set -euo pipefail

REPO=${BAILASAR_REPO:-}
TAG=${BAILASAR_RELEASE_TAG:-}
FORCE=()
while (($#)); do
    case "$1" in
        --repo|--tag)
            (($# >= 2)) || { echo "not cached: $1 requires a value" >&2; exit 1; }
            if [[ $1 == --repo ]]; then REPO=$2; else TAG=$2; fi
            shift 2
            ;;
        --force) FORCE=(--force); shift ;;
        *) echo "not cached: unknown argument: $1" >&2; exit 1 ;;
    esac
done
[[ $REPO =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || {
    echo "not cached: --repo or BAILASAR_REPO must specify owner/name" >&2; exit 1;
}
[[ -n $TAG ]] || {
    echo "not cached: --tag or BAILASAR_RELEASE_TAG is required" >&2; exit 1;
}
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)
TEMP_DIR=$(mktemp -d)
trap 'rm -rf -- "$TEMP_DIR"' EXIT
# Encode tag as a single URL segment, including tags containing slashes.
ENCODED_TAG=$(python -c 'import sys; from urllib.parse import quote; print(quote(sys.argv[1], safe=""))' "$TAG")
BASE="https://github.com/$REPO/releases/download/$ENCODED_TAG"
download() {
    if ! curl -fL --retry 3 -o "$TEMP_DIR/$1" -- "$BASE/$1"; then
        echo "not cached: release asset unavailable: $1" >&2
        exit 1
    fi
}
download cache_manifest.json
# Validate names before constructing any local path or download URL.
python - "$SCRIPT_DIR" "$TEMP_DIR/cache_manifest.json" > "$TEMP_DIR/parts.txt" <<'PY'
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from cache_release import verify_manifest

try:
    manifest = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    errors = verify_manifest(manifest)
    if errors:
        raise ValueError("; ".join(errors))
    for part in manifest["parts"]:
        print(part["name"])
except (OSError, ValueError) as error:
    sys.exit(f"not cached: invalid manifest: {error}")
PY
mapfile -t PART_NAMES < "$TEMP_DIR/parts.txt"
for NAME in "${PART_NAMES[@]}"; do
    download "$NAME"
done
python "$SCRIPT_DIR/cache_release.py" verify \
    --manifest "$TEMP_DIR/cache_manifest.json" --parts-dir "$TEMP_DIR"
python "$SCRIPT_DIR/cache_release.py" assemble \
    --manifest "$TEMP_DIR/cache_manifest.json" --parts-dir "$TEMP_DIR" \
    --cache-dir "$ROOT/local_cache" "${FORCE[@]}"
