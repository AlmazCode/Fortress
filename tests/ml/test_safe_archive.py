import hashlib
from pathlib import Path
import stat
import zipfile

import pytest

from ml.data.safe_archive import ArchiveLimits, ArchiveRejected, extract_zip


def archive(path, entries):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name, data in entries:
            output.writestr(name, data)
    return path


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/absolute", "//server/share",
    "a\\..\\escape", "a/../../x", "a//b", "a/./b", "a:b", "CON.txt", "dir/NUL",
    "trailing. ", "x/../y"])
def test_unsafe_path_leaves_no_output_or_partial_import(tmp_path, name):
    source = archive(tmp_path/"input.zip", [("good.txt", b"first"), (name, b"bad")])
    before = source.read_bytes()
    with pytest.raises(ArchiveRejected):
        extract_zip(source, tmp_path/"out")
    assert source.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["input.zip"]


def test_symlink_entry_rejected_before_writing(tmp_path):
    link = zipfile.ZipInfo("escape")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    source = archive(tmp_path/"link.zip", [("safe.txt", b"x"), (link, b"../outside")])
    with pytest.raises(ArchiveRejected, match="links"):
        extract_zip(source, tmp_path/"out")
    assert not (tmp_path/"out").exists()
    assert not list(tmp_path.glob(".fortress-import-*"))


@pytest.mark.parametrize("entries", [
    [("A.txt", b"x"), ("a.txt", b"y")],
    [("é.txt", b"x"), ("e\u0301.txt", b"y")],
    [("file", b"x"), ("file/child", b"y")],
    [("A/x", b"x"), ("a/y", b"y")],
])
def test_cross_platform_path_collisions_rejected(tmp_path, entries):
    source = archive(tmp_path/"input.zip", entries)
    with pytest.raises(ArchiveRejected, match="collision"):
        extract_zip(source, tmp_path/"out")
    assert not (tmp_path/"out").exists()


@pytest.mark.parametrize("limits", [
    ArchiveLimits(max_entries=1),
    ArchiveLimits(max_file_bytes=10),
    ArchiveLimits(max_total_bytes=25),
    ArchiveLimits(max_ratio=2),
])
def test_bomb_and_count_limits_are_transactional(tmp_path, limits):
    source = archive(tmp_path/"bomb.zip", [("a", b"z"*2000), ("b", b"z"*2000)])
    with pytest.raises(ArchiveRejected):
        extract_zip(source, tmp_path/"out", limits=limits)
    assert not (tmp_path/"out").exists()
    assert not list(tmp_path.glob(".fortress-import-*"))


def test_entry_limit_is_checked_before_zipfile_allocates_directory(tmp_path, monkeypatch):
    source = archive(tmp_path/"many.zip", [("a", b"a"), ("b", b"b")])
    def must_not_open(*args, **kwargs):
        raise AssertionError("central directory should not be allocated")
    monkeypatch.setattr(zipfile, "ZipFile", must_not_open)
    with pytest.raises(ArchiveRejected, match="limit"):
        extract_zip(source, tmp_path/"out", limits=ArchiveLimits(max_entries=1))


def test_crc_failure_rolls_back_after_first_file(tmp_path):
    source = archive(tmp_path/"bad.zip", [("first", b"keep"), ("second", b"payload")])
    with zipfile.ZipFile(source) as check:
        entry = check.getinfo("second")
        start = entry.header_offset + 30 + len(entry.filename.encode()) + len(entry.extra)
    data = bytearray(source.read_bytes())
    data[start] ^= 0xFF
    source.write_bytes(data)
    with pytest.raises((ArchiveRejected, OSError)):
        extract_zip(source, tmp_path/"out")
    assert not (tmp_path/"out").exists()
    assert not list(tmp_path.glob(".fortress-import-*"))


def test_valid_zip_is_data_only_preserves_original_and_never_overwrites(tmp_path):
    marker = tmp_path/"executed.txt"
    script = f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"
    source = archive(tmp_path/"valid.zip", [("nested/run.py", script.encode()), ("data.txt", b"bytes")])
    before = (source.read_bytes(), source.stat().st_mtime_ns)
    report = extract_zip(source, tmp_path/"out")
    assert not marker.exists()
    assert (tmp_path/"out/nested/run.py").read_bytes() == script.encode()
    assert report["executed"] is False and report["size_bytes"] == len(script.encode()) + 5
    assert report["files"][1]["sha256"] == hashlib.sha256(b"bytes").hexdigest()
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    with pytest.raises(FileExistsError):
        extract_zip(source, tmp_path/"out")
