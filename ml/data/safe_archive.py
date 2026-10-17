"""Bounded transactional ZIP import. Archive content is never executed."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import stat
import struct
import tempfile
import unicodedata
import zipfile
import zlib


class ArchiveRejected(ValueError):
    pass


@dataclass(frozen=True)
class ArchiveLimits:
    max_entries: int = 2000
    max_file_bytes: int = 512 * 1024**2
    max_total_bytes: int = 2 * 1024**3
    max_ratio: float = 100.0
    max_archive_bytes: int = 512 * 1024**2

    def __post_init__(self):
        if min(self.max_entries, self.max_file_bytes, self.max_total_bytes, self.max_archive_bytes) <= 0 or not 1 <= self.max_ratio <= 10000:
            raise ValueError("invalid archive limits")


def _central_directory_preflight(source: Path, limits: ArchiveLimits) -> int:
    # Bound central-directory allocation before ZipFile builds its entry list.
    with source.open("rb") as incoming:
        incoming.seek(max(0, source.stat().st_size - 65557))
        tail = incoming.read(65557)
    offset = tail.rfind(b"PK\x05\x06")
    if offset < 0 or len(tail) - offset < 22:
        raise ArchiveRejected("missing ZIP end record")
    _, disk, directory_disk, disk_count, count, size, _, comment = struct.unpack_from("<4s4H2LH", tail, offset)
    if offset + 22 + comment != len(tail) or disk or directory_disk or disk_count != count:
        raise ArchiveRejected("split/trailing/invalid ZIP metadata")
    if count == 65535 or size == 0xFFFFFFFF:
        raise ArchiveRejected("ZIP64 unsupported within bounded import")
    if count > limits.max_entries or size > limits.max_entries * 4096:
        raise ArchiveRejected("archive entry/central-directory limit")
    return count


def _name(info: zipfile.ZipInfo) -> tuple[str, ...]:
    name = info.filename
    if not name or "\\" in name or name.startswith("/") or "\x00" in name:
        raise ArchiveRejected("unsafe archive path")
    parts = name.rstrip("/").split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    for part in parts:
        if (part in ("", ".", "..") or part.endswith((" ", "."))
                or any(ord(c) < 32 or c in ':<>|"?*' for c in part)
                or part.split(".")[0].upper() in reserved):
            raise ArchiveRejected("unsafe archive component")
    if PurePosixPath(name).is_absolute():
        raise ArchiveRejected("absolute archive path")
    mode = info.external_attr >> 16
    kind = stat.S_IFMT(mode)
    if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or stat.S_ISLNK(mode):
        raise ArchiveRejected("links or special files are forbidden")
    if bool(kind == stat.S_IFDIR) != info.is_dir() and kind:
        raise ArchiveRejected("inconsistent directory metadata")
    if info.flag_bits & 1:
        raise ArchiveRejected("encrypted archive is unsupported")
    return tuple(parts)


def _remove_staging(staging: Path, parent: Path) -> None:
    # Delete only the private directory created by this invocation.
    resolved = staging.resolve()
    if resolved.parent != parent or not resolved.name.startswith(".fortress-import-"):
        raise RuntimeError("staging cleanup escaped output parent")
    shutil.rmtree(resolved)


def extract_zip(source: Path, destination: Path, *, limits: ArchiveLimits = ArchiveLimits()) -> dict:
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or not source.is_file():
        raise ArchiveRejected("archive must be a regular local file")
    parent = destination.parent.resolve(strict=True)
    target = parent / destination.name
    if destination.name in ("", ".", "..") or target.exists() or target.is_symlink():
        raise FileExistsError("destination must be new")
    before = source.stat()
    if before.st_size > limits.max_archive_bytes:
        raise ArchiveRejected("compressed archive byte limit")
    expected_count = _central_directory_preflight(source, limits)
    staging = None
    try:
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > limits.max_entries or len(infos) != expected_count:
                raise ArchiveRejected("archive entry count limit")
            entries, names, spellings, total = [], {}, {}, 0
            for info in infos:
                parts = _name(info)
                canonical = tuple(unicodedata.normalize("NFC", p).casefold() for p in parts)
                for index in range(1, len(parts) + 1):
                    key, spelling = canonical[:index], parts[:index]
                    if key in spellings and spellings[key] != spelling:
                        raise ArchiveRejected("implicit directory case/unicode collision")
                    spellings[key] = spelling
                if canonical in names:
                    raise ArchiveRejected("duplicate/case/unicode path collision")
                names[canonical] = info.is_dir()
                if info.file_size < 0 or info.file_size > limits.max_file_bytes:
                    raise ArchiveRejected("per-file byte limit")
                total += info.file_size
                if total > limits.max_total_bytes:
                    raise ArchiveRejected("total byte limit")
                if info.file_size / max(1, info.compress_size) > limits.max_ratio:
                    raise ArchiveRejected("compression ratio limit")
                entries.append((info, parts))
            for path in names:
                if any(names.get(path[:i]) is False for i in range(1, len(path))):
                    raise ArchiveRejected("file/directory collision")
            # All metadata is validated before any extracted output exists.
            staging = Path(tempfile.mkdtemp(prefix=".fortress-import-", dir=parent))
            actual = 0
            hashes = []
            for info, parts in entries:
                output = staging.joinpath(*parts)
                if info.is_dir():
                    output.mkdir(parents=True, exist_ok=True)
                    continue
                output.parent.mkdir(parents=True, exist_ok=True)
                count, digest = 0, hashlib.sha256()
                with archive.open(info) as incoming, output.open("xb") as outgoing:
                    while chunk := incoming.read(1024 * 1024):
                        count += len(chunk)
                        actual += len(chunk)
                        if count > min(info.file_size, limits.max_file_bytes) or actual > limits.max_total_bytes:
                            raise ArchiveRejected("actual decompressed byte limit")
                        outgoing.write(chunk)
                        digest.update(chunk)
                if count != info.file_size:
                    raise ArchiveRejected("decompressed size disagrees")
                hashes.append({"path": "/".join(parts), "sha256": digest.hexdigest(), "size_bytes": count})
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ArchiveRejected("archive changed during import")
        if target.exists() or target.is_symlink():
            raise FileExistsError("destination appeared during import")
        staging.rename(target)
        staging = None
        return {"files": hashes, "size_bytes": actual, "entries": len(infos), "executed": False}
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, zlib.error, EOFError) as exc:
        raise ArchiveRejected("unreadable or unsupported archive") from exc
    finally:
        if staging is not None:
            _remove_staging(staging, parent)
