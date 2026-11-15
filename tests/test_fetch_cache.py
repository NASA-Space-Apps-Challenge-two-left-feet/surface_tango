"""Hand-written bytes test transport/packaging logic only; no app data is produced.

Checksums use hashlib on literal test bytes. Releases stay inside tmp_path;
the commit field is a verifier fixture, never evidence of a real cache build.
"""

import hashlib
import http.client
import io
import json
import urllib.error
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import cache_release, fetch_cache

ARGS = ["--repo", "owner/repository", "--tag", "published/tag"]


@pytest.fixture
def release(tmp_path, monkeypatch):
    source = tmp_path / "input"
    source.mkdir()
    (source / "a.bin").write_bytes(b"abc")
    (source / "nested").mkdir()
    (source / "nested" / "b.bin").write_bytes(b"def")
    (source / "empty").mkdir()
    parts = tmp_path / "parts"
    manifest = cache_release.stage(source, parts, "a" * 40, max_part_bytes=128)
    assert manifest["provenance"][0]["sha256"] == hashlib.sha256(b"abc").hexdigest()
    assets = {file.name: file.read_bytes() for file in parts.iterdir()}
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(fetch_cache, "ROOT", root)
    calls = Counter()
    events = {}
    sleeps = []

    class Response(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= fetch_cache.CHUNK_BYTES
            return super().read(size)

    def urlopen(url, timeout):
        assert "/published%2Ftag/" in url
        assert timeout > 0
        name = url.rsplit("/", 1)[1]
        calls[name] += 1
        if events.get(name):
            event = events[name].pop(0)
            if isinstance(event, BaseException):
                raise event
            return event
        return Response(assets[name])

    monkeypatch.setattr(fetch_cache.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(fetch_cache.time, "sleep", sleeps.append)
    return SimpleNamespace(
        root=root,
        destination=root / "local_cache",
        manifest=manifest,
        assets=assets,
        calls=calls,
        events=events,
        sleeps=sleeps,
        part=manifest["parts"][0]["name"],
    )


def snapshot(destination):
    return {
        file.relative_to(destination).as_posix(): file.read_bytes() if file.is_file() else None
        for file in destination.rglob("*")
    }


def old_cache(release):
    release.destination.mkdir()
    (release.destination / "a.bin").write_bytes(b"old")
    (release.destination / "nested").mkdir()
    (release.destination / "nested" / "b.bin").write_bytes(b"previous")
    (release.destination / "withheld.bin").write_bytes(b"keep")
    return snapshot(release.destination)


def assert_no_install_dirs(release):
    assert sorted(file.name for file in release.root.iterdir()) == ["local_cache"]


def test_success(release):
    assert fetch_cache.main(ARGS) == 0
    assert (release.destination / "a.bin").read_bytes() == b"abc"
    assert (release.destination / "nested" / "b.bin").read_bytes() == b"def"
    assert (release.destination / "empty").is_dir()
    assert all(count == 1 for count in release.calls.values())
    assert_no_install_dirs(release)


@pytest.mark.parametrize("kind", ["sha256", "truncated", "oversized"])
def test_bad_part(release, kind):
    data = release.assets[release.part]
    if kind == "sha256":
        release.assets[release.part] = bytes([data[0] ^ 1]) + data[1:]
        message = "part sha256 mismatch"
    elif kind == "truncated":
        release.assets[release.part] = data[:-1]
        message = "part size mismatch"
    else:
        release.assets[release.part] = data + b"extra"
        message = "exceeds size limit"
    with pytest.raises(SystemExit, match=message):
        fetch_cache.main(ARGS)
    assert not release.destination.exists()
    assert release.calls[release.part] == 1


@pytest.mark.parametrize("code,headers,wait", [(429, {"Retry-After": "7"}, 7), (503, {}, 2)])
def test_http_retry(release, code, headers, wait):
    release.events[release.part] = [urllib.error.HTTPError("url", code, "busy", headers, None)]
    assert fetch_cache.main(ARGS) == 0
    assert release.calls[release.part] == 2
    assert release.sleeps == [wait]


@pytest.mark.parametrize(
    "error",
    [
        http.client.IncompleteRead(b"partial", 10),
        ConnectionError("lost"),
        OSError("read failed"),
        urllib.error.URLError("offline"),
        TimeoutError("timeout"),
    ],
)
def test_interrupted_read_retry(release, monkeypatch, error):
    class Interrupted(io.BytesIO):
        def read(self, size):
            if self.tell():
                raise error
            return super().read(1)

    release.events[release.part] = [Interrupted(b"partial")]
    original_sleep = fetch_cache.time.sleep

    def sleep(wait):
        # The failed attempt must be removed before retrying.
        assert not any(Path(file).exists() for file in partial_paths)
        original_sleep(wait)

    partial_paths = []
    original_open = Path.open

    def open_file(file, *args, **kwargs):
        if file.name == release.part and args == ("wb",):
            partial_paths.append(file)
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_file)
    monkeypatch.setattr(fetch_cache.time, "sleep", sleep)
    assert fetch_cache.main(ARGS) == 0
    assert release.calls[release.part] == 2
    assert release.sleeps == [2]


def test_404_not_retried(release):
    release.events[release.part] = [urllib.error.HTTPError("url", 404, "Not Found", {}, None)]
    with pytest.raises(SystemExit) as error:
        fetch_cache.main(ARGS)
    assert str(error.value) == (
        f"not cached: release asset unavailable: {release.part} (HTTP Error 404: Not Found)"
    )
    assert release.calls[release.part] == 1
    assert release.sleeps == []


def test_nonempty_refused_before_request(release):
    before = old_cache(release)
    with pytest.raises(SystemExit, match="refusing non-empty local_cache"):
        fetch_cache.main(ARGS)
    assert not release.calls
    assert snapshot(release.destination) == before


def test_symlink_refused_before_request(release, tmp_path):
    try:
        release.destination.symlink_to(tmp_path / "input", target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable")
    with pytest.raises(SystemExit, match="must not traverse symlinks"):
        fetch_cache.main([*ARGS, "--force"])
    assert not release.calls


def test_force_corrupt_preserves_cache(release):
    before = old_cache(release)
    data = release.assets[release.part]
    release.assets[release.part] = bytes([data[0] ^ 1]) + data[1:]
    with pytest.raises(SystemExit, match="part sha256 mismatch"):
        fetch_cache.main([*ARGS, "--force"])
    assert snapshot(release.destination) == before
    assert_no_install_dirs(release)


def test_force_success_preserves_unlisted(release):
    old_cache(release)
    assert fetch_cache.main([*ARGS, "--force"]) == 0
    assert (release.destination / "a.bin").read_bytes() == b"abc"
    assert (release.destination / "nested" / "b.bin").read_bytes() == b"def"
    assert (release.destination / "withheld.bin").read_bytes() == b"keep"
    assert_no_install_dirs(release)


@pytest.mark.parametrize("force", [False, True])
def test_install_failure_rolls_back(release, monkeypatch, force):
    before = old_cache(release) if force else None
    original_replace = cache_release.os.replace
    installed = []

    def replace(source, target):
        if "-staging-" in str(source):
            if installed:
                raise OSError("install interrupted")
            installed.append(target)
        return original_replace(source, target)

    monkeypatch.setattr(cache_release.os, "replace", replace)
    with pytest.raises(SystemExit, match="install interrupted"):
        fetch_cache.main([*ARGS, *(["--force"] if force else [])])
    assert installed
    if force:
        assert snapshot(release.destination) == before
        assert_no_install_dirs(release)
    else:
        assert list(release.root.iterdir()) == []


def test_extracted_hash_failure_preserves_cache(release, monkeypatch):
    before = old_cache(release)
    original_hash = fetch_cache.assemble.__globals__["sha256_file"]

    def checksum(file):
        if "-staging-" in str(file):
            return hashlib.sha256(b"wrong").hexdigest()
        return original_hash(file)

    monkeypatch.setitem(fetch_cache.assemble.__globals__, "sha256_file", checksum)
    with pytest.raises(SystemExit, match="extracted sha256 mismatch"):
        fetch_cache.main([*ARGS, "--force"])
    assert snapshot(release.destination) == before
    assert_no_install_dirs(release)


def test_manifest_size_cap(release, monkeypatch):
    monkeypatch.setattr(fetch_cache, "MAX_MANIFEST_BYTES", 1)
    with pytest.raises(SystemExit, match="exceeds size limit: cache_manifest.json"):
        fetch_cache.main(ARGS)
    assert release.calls == {"cache_manifest.json": 1}


@pytest.mark.parametrize("malformed", [False, True])
def test_invalid_manifest_before_parts(release, malformed):
    if malformed:
        release.assets["cache_manifest.json"] = b"{"
    else:
        release.manifest["parts"][0]["name"] = "../escape"
        release.assets["cache_manifest.json"] = json.dumps(release.manifest).encode()
    with pytest.raises(SystemExit, match="invalid manifest"):
        fetch_cache.main(ARGS)
    assert release.calls == {"cache_manifest.json": 1}


def test_retry_budget_and_wait_cap(release):
    release.events[release.part] = [
        urllib.error.HTTPError("url", 429, "busy", {"Retry-After": "9999"}, None)
        for _ in range(fetch_cache.RETRIES)
    ]
    with pytest.raises(SystemExit, match="release asset unavailable"):
        fetch_cache.main(ARGS)
    assert release.calls[release.part] == fetch_cache.RETRIES
    assert release.sleeps == [fetch_cache.MAX_RETRY_WAIT] * (fetch_cache.RETRIES - 1)


def test_exponential_backoff(release):
    release.events[release.part] = [urllib.error.URLError("offline")] * 2
    assert fetch_cache.main(ARGS) == 0
    assert release.sleeps == [2, 4]
