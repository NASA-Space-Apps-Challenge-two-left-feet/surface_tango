"""Hand-written bytes test packaging logic only; no app data is produced.

All checksums are computed with hashlib from the literal bytes in these tests.
The commit field is a verifier fixture, never a claim about a real cache build.
"""

import hashlib
import io
import json
import tarfile

import pytest

from scripts.cache_release import (
    assemble,
    main,
    stage,
    verify_manifest,
    verify_parts,
)


@pytest.fixture
def staged(tmp_path, capsys):
    root = tmp_path / "input"
    root.mkdir()
    (root / "tile.bin").write_bytes(b"abc")
    (root / "unknown.bin").write_bytes(b"def")
    (root / "empty-directory").mkdir()
    (root / "provenance.json").write_text(
        json.dumps(
            {
                "tile.bin": {"source": "live", "granule_ids": ["test-scene"], "missing": False},
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "parts"
    # A tiny byte limit exercises splitting; these are test settings only.
    main(
        [
            "stage",
            "--cache-dir",
            str(root),
            "--output-dir",
            str(output),
            "--source-commit",
            "a" * 40,
            "--max-part-bytes",
            "32",
        ]
    )
    manifest = json.loads((output / "cache_manifest.json").read_text(encoding="utf-8"))
    return root, output, manifest


def test_round_trip(staged, tmp_path):
    root, output, manifest = staged
    assert len(manifest["parts"]) >= 2
    assert all(part["size_bytes"] <= 32 for part in manifest["parts"])
    assert verify_manifest(manifest) == []
    assert verify_parts(manifest, output) == []
    main(["verify", "--manifest", str(output / "cache_manifest.json"), "--parts-dir", str(output)])
    restored = tmp_path / "restored"
    main(
        [
            "assemble",
            "--manifest",
            str(output / "cache_manifest.json"),
            "--parts-dir",
            str(output),
            "--cache-dir",
            str(restored),
        ]
    )
    assert (restored / "empty-directory").is_dir()
    for file in root.rglob("*"):
        if file.is_file():
            assert (restored / file.relative_to(root)).read_bytes() == file.read_bytes()
    known = next(entry for entry in manifest["provenance"] if entry["path"] == "tile.bin")
    assert known["source"] == "live"
    assert known["granule_ids"] == ["test-scene"]
    assert known["sha256"] == hashlib.sha256(b"abc").hexdigest()
    assert known["missing"] is False


def test_corrupt_part(staged):
    _, output, manifest = staged
    part = output / manifest["parts"][0]["name"]
    data = part.read_bytes()
    part.write_bytes(bytes([data[0] ^ 1]) + data[1:])
    assert any("sha256 mismatch" in error for error in verify_parts(manifest, output))


def test_missing_part(staged):
    _, output, manifest = staged
    (output / manifest["parts"][0]["name"]).unlink()
    assert any("missing part" in error for error in verify_parts(manifest, output))


def test_noncontiguous_indices(staged):
    _, _, manifest = staged
    manifest["parts"][0]["index"] = 1
    assert any("contiguous" in error for error in verify_manifest(manifest))


def test_missing_granule_ids_rejected(staged):
    _, _, manifest = staged
    entry = manifest["provenance"][0]
    entry.update(granule_ids=[], missing=False)
    assert any("requires granule IDs" in error for error in verify_manifest(manifest))


def test_unknown_provenance_is_missing(staged, capsys):
    _, _, manifest = staged
    unknown = next(entry for entry in manifest["provenance"] if entry["path"] == "unknown.bin")
    assert unknown["missing"] is True
    assert unknown["granule_ids"] == []
    assert "missing provenance: unknown.bin" in capsys.readouterr().out


@pytest.mark.parametrize("name", ["../escape", "/escape", "a/../../escape", "C:/escape"])
def test_path_traversal_rejected(staged, tmp_path, name):
    _, output, manifest = staged
    malicious = tmp_path / "malicious.tar.gz"
    with tarfile.open(malicious, "w:gz") as bundle:
        member = tarfile.TarInfo(name)
        member.size = len(b"abc")
        bundle.addfile(member, io.BytesIO(b"abc"))
    data = malicious.read_bytes()
    part = output / "hostile.part"
    part.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    manifest["archive"].update(sha256=digest, size_bytes=len(data))
    manifest["parts"] = [{"name": part.name, "sha256": digest, "size_bytes": len(data), "index": 0}]
    with pytest.raises(ValueError, match="unsafe archive member"):
        assemble(manifest, output, tmp_path / "restored")
    assert not (tmp_path / "escape").exists()
    assert not (tmp_path / "restored").exists()


def test_nonempty_destination_requires_force(staged, tmp_path):
    _, output, manifest = staged
    destination = tmp_path / "restored"
    destination.mkdir()
    (destination / "tile.bin").write_bytes(b"old")
    with pytest.raises(ValueError, match="non-empty"):
        assemble(manifest, output, destination)
    assert (destination / "tile.bin").read_bytes() == b"old"
    assemble(manifest, output, destination, force=True)
    assert (destination / "tile.bin").read_bytes() == b"abc"


def test_provenance_hash_mismatch_before_extraction(staged, tmp_path):
    _, output, manifest = staged
    manifest["provenance"][0]["sha256"] = hashlib.sha256(b"wrong").hexdigest()
    with pytest.raises(ValueError, match="provenance sha256 mismatch"):
        assemble(manifest, output, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


@pytest.mark.parametrize("metadata_name", ["zarr.json", ".zattrs"])
def test_zarr_recorded_array_provenance(tmp_path, metadata_name):
    root = tmp_path / "input"
    array = root / "cube.zarr" / "band" / "c"
    array.mkdir(parents=True)
    (array / "0").write_bytes(b"abc")
    attributes = {"nisar_provenance": json.dumps({"band": "NISAR_test_scene"})}
    document = {"attributes": attributes} if metadata_name == "zarr.json" else attributes
    (root / "cube.zarr" / metadata_name).write_text(json.dumps(document), encoding="utf-8")
    manifest = stage(root, tmp_path / "parts", "a" * 40, max_part_bytes=32)
    entry = next(item for item in manifest["provenance"] if item["path"].endswith("/c/0"))
    assert entry["granule_ids"] == ["NISAR_test_scene"]
    assert entry["missing"] is False
