"""Stage and restore real cache releases; this module never publishes assets.

Stage requires --source-commit supplied by the release owner. Sidecars named
provenance.json accept a mapping of relative file paths to records (or a
provenance list with path fields). Records contain source, granule_ids, missing.
Zarr attributes.nisar_provenance (v3) and .zattrs (v2) are also read, scoped
to the array's name. Unknown or ambiguous records remain explicitly missing.
Keep the cache quiescent while staging; changing files aborts staging.
"""

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

# GitHub's documented per-asset ceiling: keep each asset strictly below 2 GiB.
# https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
MAX_ASSET_BYTES = 2 * 1024**3 - 1


def sha256_file(file):
    digest = hashlib.sha256()
    with file.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(value):
    """Use portable POSIX names, including when restoring on Windows."""
    return (
        isinstance(value, str)
        and bool(value)
        and "\\" not in value
        and ":" not in value
        and all(ord(char) >= 32 for char in value)
        and not value.startswith("/")
        and all(
            part not in ("", ".", "..") and not part.endswith((".", " "))
            for part in value.split("/")
        )
    )


def asset_name(value):
    return (
        safe_relative(value)
        and "/" not in value
        and all(char.isascii() and (char.isalnum() or char in "._-") for char in value)
    )


def verify_manifest(manifest) -> list[str]:
    """Return schema/ordering errors without requiring a JSON Schema package."""
    errors = []
    if not isinstance(manifest, dict):
        return ["manifest must be an object"]

    def keys(record, required, label):
        if not isinstance(record, dict):
            errors.append(f"{label} must be an object")
            return False
        if set(record) != set(required):
            errors.append(f"{label}: expected keys {', '.join(required)}")
        return True

    def checksum(value, label):
        if not (
            isinstance(value, str)
            and len(value) == 64
            and all(char in "0123456789abcdefABCDEF" for char in value)
        ):
            errors.append(f"{label}: sha256 must be 64 hex characters")

    def asset(record, label, part=False):
        required = ["name", "sha256", "size_bytes"] + (["index"] if part else [])
        if not keys(record, required, label):
            return
        if not asset_name(record.get("name")):
            errors.append(f"{label}: unsafe asset name")
        checksum(record.get("sha256"), label)
        size = record.get("size_bytes")
        if type(size) is not int or size <= 0:
            errors.append(f"{label}: size_bytes must be a positive integer")
        elif part and size > MAX_ASSET_BYTES:
            errors.append(f"{label}: exceeds GitHub per-asset limit")

    keys(
        manifest,
        ["schema_version", "build_time_utc", "source_commit", "archive", "parts", "provenance"],
        "manifest",
    )
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        errors.append("unsupported schema_version")
    try:
        stamp = datetime.fromisoformat(manifest.get("build_time_utc", "").replace("Z", "+00:00"))
        if stamp.utcoffset() != UTC.utcoffset(None):
            errors.append("build_time_utc must be UTC")
    except (ValueError, TypeError, AttributeError):
        errors.append("build_time_utc must be an ISO 8601 UTC timestamp")
    commit = manifest.get("source_commit")
    if not (
        isinstance(commit, str)
        and len(commit) in (40, 64)
        and all(char in "0123456789abcdefABCDEF" for char in commit)
    ):
        errors.append("source_commit must be a full hex commit ID")
    asset(manifest.get("archive"), "archive")
    if isinstance(manifest.get("archive"), dict):
        if manifest["archive"].get("name") == "cache_manifest.json":
            errors.append("archive name is reserved")
    parts = manifest.get("parts")
    if not isinstance(parts, list) or not parts:
        errors.append("parts must be a non-empty list")
    else:
        names = {"cache_manifest.json"}
        if isinstance(manifest.get("archive"), dict):
            name = manifest["archive"].get("name")
            if isinstance(name, str):
                names.add(name)
        for index, part in enumerate(parts):
            asset(part, f"part {index}", part=True)
            if not isinstance(part, dict):
                continue
            if type(part.get("index")) is not int or part["index"] != index:
                errors.append("part indices must be contiguous from 0 in list order")
            name = part.get("name")
            if isinstance(name, str):
                if name in names:
                    errors.append("duplicate or reserved part name")
                names.add(name)
    entries = manifest.get("provenance")
    if not isinstance(entries, list):
        errors.append("provenance must be a list")
    else:
        seen = set()
        for entry in entries:
            if not keys(
                entry,
                ["path", "sha256", "source", "granule_ids", "missing"],
                "provenance entry",
            ):
                continue
            name = entry.get("path")
            if not safe_relative(name):
                errors.append("unsafe provenance path")
            elif name in seen:
                errors.append(f"duplicate provenance path: {name}")
            else:
                seen.add(name)
            checksum(entry.get("sha256"), "provenance")
            if entry.get("source") not in ("live", "cached"):
                errors.append("provenance source must be live or cached")
            if type(entry.get("missing")) is not bool:
                errors.append("provenance missing must be boolean")
            ids = entry.get("granule_ids")
            if not isinstance(ids, list) or any(
                not isinstance(item, str) or not item.strip() for item in ids
            ):
                errors.append("granule_ids must be a list of non-empty strings")
            elif not ids and entry.get("missing") is not True:
                errors.append("non-missing provenance requires granule IDs")
    return errors


def verify_parts(manifest, parts_dir) -> list[str]:
    errors = verify_manifest(manifest)
    if errors:
        return errors
    parts_dir = Path(parts_dir)
    for part in manifest["parts"]:
        file = parts_dir / part["name"]
        try:
            if file.is_symlink() or not file.is_file():
                errors.append(f"missing part or unsafe link: {part['name']}")
            elif file.stat().st_size != part["size_bytes"]:
                errors.append(f"part size mismatch: {part['name']}")
            elif sha256_file(file).lower() != part["sha256"].lower():
                errors.append(f"part sha256 mismatch: {part['name']}")
        except OSError as error:
            errors.append(f"cannot read part {part['name']}: {error}")
    return errors


def recorded_provenance(file, root):
    """Read explicit sidecars first, then array-scoped Zarr attributes."""
    for parent in (file.parent, *file.parent.parents):
        if not parent.is_relative_to(root):
            break
        sidecar = parent / "provenance.json"
        if sidecar.is_file():
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("provenance"), list):
                records = {item["path"]: item for item in data["provenance"]}
            elif isinstance(data, dict) and isinstance(data.get("path"), str):
                records = {data["path"]: data}
            else:
                records = data
            if isinstance(records, dict):
                record = records.get(file.relative_to(parent).as_posix())
                if isinstance(record, dict):
                    return {
                        "source": record.get("source", "cached"),
                        "granule_ids": record.get("granule_ids", []),
                        "missing": record.get("missing", not record.get("granule_ids")),
                    }
        for metadata in (parent / "zarr.json", parent / ".zattrs"):
            if not metadata.is_file():
                continue
            data = json.loads(metadata.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError(f"invalid Zarr metadata object: {metadata}")
            attrs = data.get("attributes", data)
            if not isinstance(attrs, dict):
                raise ValueError(f"invalid Zarr attributes object: {metadata}")
            mapping = attrs.get("nisar_provenance", {})
            if isinstance(mapping, str):
                mapping = json.loads(mapping)
            if not isinstance(mapping, dict):
                continue
            relative = file.relative_to(parent).parts
            record = mapping.get(relative[0])
            if isinstance(record, str) and record.startswith("NISAR_"):
                # The warmer appends processing notes after the recorded scene ID.
                return {
                    "source": "cached",
                    "granule_ids": [record.split(" (", 1)[0]],
                    "missing": False,
                }
    return {"source": "cached", "granule_ids": [], "missing": True}


def require_valid(errors):
    if errors:
        raise ValueError("\n".join(errors))


def stage(cache_dir, output_dir, source_commit, max_part_bytes=MAX_ASSET_BYTES):
    """Write a complete inventory, compressed archive parts and a manifest."""
    if type(max_part_bytes) is not int or not 0 < max_part_bytes <= MAX_ASSET_BYTES:
        raise ValueError("max-part-bytes must be positive and within the GitHub asset limit")
    root = Path(cache_dir).resolve()  # Worktree local_cache may link to the main checkout.
    output = Path(output_dir).resolve()
    if not root.is_dir():
        raise ValueError("not cached: cache directory does not exist")
    if output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError("cache and output directories must not contain one another")
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty")
    paths = sorted(root.rglob("*"))
    for file in paths:
        if file.is_symlink() or not (file.is_file() or file.is_dir()):
            raise ValueError(f"unsupported cache entry (nothing skipped): {file}")
        if not safe_relative(file.relative_to(root).as_posix()):
            raise ValueError(f"unsafe cache entry: {file}")
    entries = []
    for file in paths:
        name = file.relative_to(root).as_posix()
        print(f"include {'file' if file.is_file() else 'directory'}: {name}")
        if file.is_file():
            entry = {
                "path": name,
                "sha256": sha256_file(file),
                **recorded_provenance(file, root),
            }
            entries.append(entry)
            if entry["missing"]:
                print(f"missing provenance: {name}")
    manifest = {
        "schema_version": 1,
        "build_time_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_commit": source_commit,
        "archive": {"name": "cache.tar.gz"},
        "parts": [],
        "provenance": entries,
    }
    output.mkdir(parents=True, exist_ok=True)
    archive = output / manifest["archive"]["name"]
    with tarfile.open(archive, "w:gz", dereference=True) as bundle:
        for file in paths:
            bundle.add(file, arcname=file.relative_to(root).as_posix(), recursive=False)
    if sorted(root.rglob("*")) != paths:
        raise ValueError("cache inventory changed during stage")
    # Check the archived bytes, not just a second read of the source directory.
    with tarfile.open(archive, "r:gz") as bundle:
        for entry in entries:
            with bundle.extractfile(entry["path"]) as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != entry["sha256"]:
                raise ValueError(f"cache changed during stage: {entry['path']}")
    manifest["archive"].update(sha256=sha256_file(archive), size_bytes=archive.stat().st_size)
    manifest["parts"] = []
    with archive.open("rb") as stream:
        while stream.peek(1):
            index = len(manifest["parts"])
            part = output / f"cache.tar.gz.part-{index:06d}"
            remaining = max_part_bytes
            with part.open("wb") as target:
                while remaining and (chunk := stream.read(min(remaining, 1024 * 1024))):
                    target.write(chunk)
                    remaining -= len(chunk)
            manifest["parts"].append(
                {
                    "name": part.name,
                    "sha256": sha256_file(part),
                    "size_bytes": part.stat().st_size,
                    "index": index,
                }
            )
            print(f"asset: {part.name} ({part.stat().st_size} bytes, measured by stage)")
    require_valid(verify_parts(manifest, output))
    (output / "cache_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    archive.unlink()
    return manifest


def preflight_destination(cache_dir, force=False):
    """Reject ineligible destinations before downloading or assembling assets."""
    destination = Path(cache_dir).absolute()
    if any(parent.is_symlink() for parent in (destination, *destination.parents)):
        raise ValueError("cache destination must not traverse symlinks")
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        if not force or not destination.is_dir():
            raise ValueError("refusing non-empty local_cache; use --force to overlay files")
    return destination


def install_staged(staging, destination):
    """Overlay verified files, restoring the previous tree if installation fails."""
    backup = Path(tempfile.mkdtemp(prefix=f".{destination.name}-backup-", dir=destination.parent))
    placed = []
    saved = []
    directories = []

    def ensure_directory(target):
        if target.is_dir():
            return
        ensure_directory(target.parent)
        if target.exists():
            save(target)
        target.mkdir()
        directories.append(target)

    def save(target):
        stored = backup / target.relative_to(destination)
        stored.parent.mkdir(parents=True, exist_ok=True)
        os.replace(target, stored)
        saved.append((target, stored))

    try:
        ensure_directory(destination)
        for source in sorted(staging.rglob("*")):
            target = destination / source.relative_to(staging)
            if source.is_dir():
                ensure_directory(target)
            else:
                ensure_directory(target.parent)
                if target.exists():
                    if target.is_dir():
                        raise ValueError(f"cannot overlay directory with file: {target}")
                    save(target)
                os.replace(source, target)
                placed.append(target)
    except BaseException:
        for target in reversed(placed):
            target.unlink()
        for target in reversed(directories):
            target.rmdir()
        for target, stored in reversed(saved):
            os.replace(stored, target)
        # Keep backups available if rollback itself raises.
        shutil.rmtree(backup)
        raise
    shutil.rmtree(backup)


def assemble(manifest, parts_dir, cache_dir, force=False):
    """Validate bytes before extraction; force overlays files, preserving unlisted files."""
    require_valid(verify_parts(manifest, parts_dir))
    destination = preflight_destination(cache_dir, force)
    archive = Path(parts_dir) / manifest["archive"]["name"]
    if archive.exists() or archive.is_symlink():
        raise ValueError("temporary archive path already exists")
    created = False
    try:
        with archive.open("xb") as target:
            created = True
            for part in manifest["parts"]:
                with (Path(parts_dir) / part["name"]).open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        target.write(chunk)
        if (
            archive.stat().st_size != manifest["archive"]["size_bytes"]
            or sha256_file(archive).lower() != manifest["archive"]["sha256"].lower()
        ):
            raise ValueError("archive sha256 or size mismatch")
        expected = {entry["path"]: entry for entry in manifest["provenance"]}
        with tarfile.open(archive, "r:gz") as bundle:
            members = bundle.getmembers()
            seen = set()
            files = set()
            for member in members:
                name = member.name
                if not safe_relative(name) or not (member.isfile() or member.isdir()):
                    raise ValueError(f"unsafe archive member: {name}")
                if name in seen:
                    raise ValueError(f"duplicate archive member: {name}")
                seen.add(name)
                target = destination.joinpath(*PurePosixPath(name).parts)
                if any(parent.is_symlink() for parent in (target, *target.parents)):
                    raise ValueError(f"unsafe destination link: {name}")
                if member.isfile():
                    files.add(name)
                    if name not in expected:
                        raise ValueError(f"archive file lacks manifest entry: {name}")
                    with bundle.extractfile(member) as stream:
                        digest = hashlib.file_digest(stream, "sha256").hexdigest()
                    if digest.lower() != expected[name]["sha256"].lower():
                        raise ValueError(f"provenance sha256 mismatch: {name}")
            if files != set(expected):
                raise ValueError("archive is missing manifest files")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix=f".{destination.name}-staging-", dir=destination.parent
            ) as tmp:
                staging = Path(tmp)
                for member in members:
                    target = staging.joinpath(*PurePosixPath(member.name).parts)
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with bundle.extractfile(member) as stream, target.open("wb") as output:
                            while chunk := stream.read(1024 * 1024):
                                output.write(chunk)
                for entry in expected.values():
                    if sha256_file(staging / entry["path"]).lower() != entry["sha256"].lower():
                        raise ValueError(f"extracted sha256 mismatch: {entry['path']}")
                preflight_destination(destination, force)
                install_staged(staging, destination)
    finally:
        if created:
            archive.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    staging = commands.add_parser("stage")
    staging.add_argument("--cache-dir", type=Path, default=Path("local_cache"))
    staging.add_argument("--output-dir", type=Path, default=Path("dist/cache-release"))
    staging.add_argument("--source-commit", required=True)
    staging.add_argument("--max-part-bytes", type=int, default=MAX_ASSET_BYTES)
    for command in ("verify", "assemble"):
        sub = commands.add_parser(command)
        sub.add_argument("--manifest", type=Path, required=True)
        sub.add_argument("--parts-dir", type=Path, required=True)
        if command == "assemble":
            sub.add_argument("--cache-dir", type=Path, default=Path("local_cache"))
            sub.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "stage":
            stage(args.cache_dir, args.output_dir, args.source_commit, args.max_part_bytes)
        else:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            require_valid(verify_parts(manifest, args.parts_dir))
            if args.command == "assemble":
                assemble(manifest, args.parts_dir, args.cache_dir, args.force)
        print(f"cache {args.command}: verified")
    except (OSError, ValueError, TypeError, KeyError, EOFError, tarfile.TarError) as error:
        parser.exit(1, f"not cached: {error}\n")


if __name__ == "__main__":
    main()
