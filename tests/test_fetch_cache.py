"""Hand-written bytes test transport/packaging logic only; no app data is produced.

Checksums use hashlib on literal test bytes. Releases stay inside tmp_path;
the commit field is a verifier fixture, never evidence of a real cache build.
"""

import errno
import hashlib
import http.client
import io
import json
import urllib.error
from collections import Counter
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
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


@pytest.mark.parametrize("operation", ["backup", "install", "mkdir"])
def test_interrupt_after_mutation_restores_originals(release, monkeypatch, operation):
    before = old_cache(release)
    original_replace = cache_release.os.replace
    original_mkdir = Path.mkdir
    interrupted = []

    def replace(source, target):
        result = original_replace(source, target)
        selected = (
            "-backup-" in str(target) if operation == "backup" else "-staging-" in str(source)
        )
        if operation != "mkdir" and selected and not interrupted:
            interrupted.append(target)
            raise KeyboardInterrupt
        return result

    def mkdir(target, *args, **kwargs):
        result = original_mkdir(target, *args, **kwargs)
        if operation == "mkdir" and target == release.destination / "empty" and not interrupted:
            interrupted.append(target)
            raise KeyboardInterrupt
        return result

    monkeypatch.setattr(cache_release.os, "replace", replace)
    monkeypatch.setattr(Path, "mkdir", mkdir)
    with pytest.raises(KeyboardInterrupt):
        fetch_cache.main([*ARGS, "--force"])
    assert interrupted
    assert snapshot(release.destination) == before
    assert_no_install_dirs(release)


def test_rollback_continues_and_keeps_unrestored_backup(release, monkeypatch):
    old_cache(release)
    original_replace = cache_release.os.replace
    original_unlink = Path.unlink
    blocked = release.destination / "nested" / "b.bin"

    def replace(source, target):
        if "-backup-" in str(source) and target == blocked:
            raise PermissionError("held open during restore")
        result = original_replace(source, target)
        if "-staging-" in str(source) and target == blocked:
            raise OSError("install interrupted")
        return result

    def unlink(target, *args, **kwargs):
        if target == blocked:
            raise PermissionError("held open during unlink")
        return original_unlink(target, *args, **kwargs)

    monkeypatch.setattr(cache_release.os, "replace", replace)
    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(SystemExit, match="rollback incomplete") as error:
        fetch_cache.main([*ARGS, "--force"])
    backups = list(release.root.glob(".local_cache-backup-*"))
    assert len(backups) == 1
    backup = backups[0]
    assert str(backup) in str(error.value)
    assert f"move {backup / 'nested' / 'b.bin'} back to {blocked}" in str(error.value)
    assert "held open during unlink" in str(error.value)
    assert "held open during restore" in str(error.value)
    assert (backup / "nested" / "b.bin").read_bytes() == b"previous"
    assert (release.destination / "a.bin").read_bytes() == b"old"
    assert (release.destination / "withheld.bin").read_bytes() == b"keep"
    assert not (release.destination / "empty").exists()
    assert not (release.root / ".local_cache.lock").exists()


def test_second_fetch_refused_while_lock_held(release):
    lock = release.root / ".local_cache.lock"
    with cache_release.cache_lock(release.destination):
        before = lock.read_bytes()
        owner = json.loads(before)
        assert owner["pid"] > 0
        assert owner["hostname"]
        assert datetime.fromisoformat(owner["since"]).utcoffset() == timedelta(0)
        with pytest.raises(SystemExit) as error:
            fetch_cache.main(ARGS)
        assert str(error.value) == (
            f"not cached: another fetch holds {lock} (pid {owner['pid']}, "
            f"since {owner['since']}); if no fetch is running, rerun with --break-lock"
        )
        assert not release.calls
        assert lock.read_bytes() == before
    assert not lock.exists()


def test_break_lock(release, capsys):
    lock = release.root / ".local_cache.lock"
    stale = '{"pid": 123, "hostname": "old-host", "since": "2026-01-01T00:00:00Z"}'
    lock.write_text(stale, encoding="utf-8")
    assert fetch_cache.main([*ARGS, "--break-lock"]) == 0
    assert f"removed lock {lock}: {stale}" in capsys.readouterr().out
    assert_no_install_dirs(release)


@pytest.mark.parametrize("failure", [False, True])
def test_lock_held_during_requests_and_removed_afterwards(release, monkeypatch, failure):
    lock = release.root / ".local_cache.lock"
    original_urlopen = fetch_cache.urllib.request.urlopen

    def urlopen(*args, **kwargs):
        assert lock.is_file()
        if failure:
            raise urllib.error.HTTPError("url", 404, "missing", {}, None)
        return original_urlopen(*args, **kwargs)

    monkeypatch.setattr(fetch_cache.urllib.request, "urlopen", urlopen)
    if failure:
        with pytest.raises(SystemExit, match="release asset unavailable"):
            fetch_cache.main(ARGS)
    else:
        assert fetch_cache.main(ARGS) == 0
    assert not lock.exists()


@pytest.mark.parametrize("seconds", [17, 9999, -10])
def test_http_date_retry_after(release, monkeypatch, seconds):
    now = datetime(2026, 11, 15, tzinfo=UTC)

    class Clock:
        @staticmethod
        def now(tz):
            assert tz == UTC
            return now

    monkeypatch.setattr(fetch_cache, "datetime", Clock)
    value = format_datetime(now + timedelta(seconds=seconds), usegmt=True)
    release.events[release.part] = [
        urllib.error.HTTPError("url", 429, "busy", {"Retry-After": value}, None)
    ]
    assert fetch_cache.main(ARGS) == 0
    assert release.calls[release.part] == 2
    assert release.sleeps == [min(seconds, fetch_cache.MAX_RETRY_WAIT) if seconds >= 0 else 2]


@pytest.mark.parametrize("value", ["-1", "nan", "inf", "invalid"])
def test_invalid_retry_after_uses_backoff(release, value):
    release.events[release.part] = [
        urllib.error.HTTPError("url", 503, "busy", {"Retry-After": value}, None)
    ]
    assert fetch_cache.main(ARGS) == 0
    assert release.sleeps == [2]


@pytest.mark.parametrize("operation", ["open", "write", "close"])
def test_local_disk_error_not_retried(release, monkeypatch, operation):
    original_open = Path.open
    partial_paths = []

    class FullDisk:
        def __init__(self, stream):
            self.stream = stream

        def write(self, chunk):
            if operation == "write":
                raise OSError(errno.ENOSPC, "disk full")
            return self.stream.write(chunk)

        def close(self):
            self.stream.close()
            if operation == "close":
                raise OSError(errno.ENOSPC, "disk full")

    def open_file(target, *args, **kwargs):
        if target.name == release.part and args == ("wb",):
            partial_paths.append(target)
            if operation == "open":
                raise PermissionError(errno.EACCES, "access denied")
            return FullDisk(original_open(target, *args, **kwargs))
        return original_open(target, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_file)
    with pytest.raises(SystemExit, match=f"not cached: local write failed for {release.part}:"):
        fetch_cache.main(ARGS)
    assert release.calls[release.part] == 1
    assert release.sleeps == []
    assert partial_paths and not any(target.exists() for target in partial_paths)
    assert not (release.root / ".local_cache.lock").exists()


def test_failed_backup_move_leaves_original_untouched(release, monkeypatch):
    before = old_cache(release)
    original_replace = cache_release.os.replace

    def replace(source, target):
        if "-backup-" in str(target):
            raise KeyboardInterrupt
        return original_replace(source, target)

    monkeypatch.setattr(cache_release.os, "replace", replace)
    with pytest.raises(KeyboardInterrupt):
        fetch_cache.main([*ARGS, "--force"])
    assert snapshot(release.destination) == before
    assert_no_install_dirs(release)


def test_failed_install_does_not_remove_unowned_file(release, monkeypatch):
    original_replace = cache_release.os.replace
    target_file = release.destination / "a.bin"

    def replace(source, target):
        if "-staging-" in str(source):
            target.write_bytes(b"unrelated")
            raise OSError("move never happened")
        return original_replace(source, target)

    monkeypatch.setattr(cache_release.os, "replace", replace)
    with pytest.raises(SystemExit, match="move never happened"):
        fetch_cache.main(ARGS)
    assert target_file.read_bytes() == b"unrelated"
    assert_no_install_dirs(release)


@pytest.mark.parametrize("failure", [False, True])
def test_direct_assembly_holds_and_releases_lock(release, tmp_path, monkeypatch, failure):
    lock = release.root / ".local_cache.lock"
    original_install = cache_release.install_staged

    def install(staging, destination):
        assert lock.is_file()
        if failure:
            raise OSError("install failed")
        original_install(staging, destination)

    monkeypatch.setattr(cache_release, "install_staged", install)
    if failure:
        with pytest.raises(OSError, match="install failed"):
            cache_release.assemble(release.manifest, tmp_path / "parts", release.destination)
    else:
        cache_release.assemble(release.manifest, tmp_path / "parts", release.destination)
        assert (release.destination / "a.bin").read_bytes() == b"abc"
    assert not lock.exists()


def test_direct_assembly_refused_while_locked(release, tmp_path):
    with cache_release.cache_lock(release.destination):
        lock = release.root / ".local_cache.lock"
        before = lock.read_bytes()
        with pytest.raises(ValueError, match="another fetch holds"):
            cache_release.assemble(release.manifest, tmp_path / "parts", release.destination)
        assert lock.read_bytes() == before
        assert not release.destination.exists()
