"""Read-only local source import with a K manifest and a separate audit sidecar."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import stat
import struct
import time

from contracts.python_ports import validate_contract
from ml.data.deduplicate import dhash64, duplicate_report, stable_hash


class SourceRejected(ValueError):
    pass


@dataclass(frozen=True)
class ProbeLimits:
    max_sources: int = 500
    max_source_bytes: int = 2 * 1024**3
    max_frames: int = 200000
    max_frame_pixels: int = 16_777_216
    max_decoded_pixels: int = 4_000_000_000
    max_decode_seconds: float = 120.0

    def __post_init__(self):
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
               for v in asdict(self).values()):
            raise ValueError("probe limits must be positive")
        if any(not isinstance(v, int) for k, v in asdict(self).items() if k != "max_decode_seconds"):
            raise ValueError("count/byte/pixel limits must be integers")


def local_source(root: Path, relative: str) -> Path:
    # Never dereference an archive-supplied path, symlink, device or URL.
    if (not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative
            or relative.startswith("/") or any(p in ("", ".", "..") for p in relative.split("/"))):
        raise SourceRejected("unsafe_relative_path")
    path = root
    for part in PurePosixPath(relative).parts:
        path = path / part
        if path.is_symlink():
            raise SourceRejected("symlink_source")
    if not path.exists():
        raise SourceRejected("source_missing")
    if not stat.S_ISREG(path.stat().st_mode):
        raise SourceRejected("source_not_regular")
    if not path.resolve().is_relative_to(root.resolve()):
        raise SourceRejected("source_outside_root")
    return path


def source_hash(path: Path, max_bytes: int) -> str:
    before = path.stat()
    if before.st_size > max_bytes:
        raise SourceRejected("source_byte_limit")
    digest, count = hashlib.sha256(), 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            count += len(chunk)
            if count > max_bytes:
                raise SourceRejected("source_byte_limit")
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or count != before.st_size:
        raise SourceRejected("source_changed")
    return digest.hexdigest()


def open_local_video(path: Path):
    """Detect container bytes, including backend-owned .part/.video paths.

    Keep demuxers restricted before their header readers run: merely checking the
    detected format afterwards would allow playlists to open other sources.
    Callers still validate regular local paths, source hashes and decode budgets.
    """
    import av

    return av.open(str(path), mode="r", options={
        "format_whitelist": "mov,matroska,webm,avi",
        "protocol_whitelist": "file", "err_detect": "explode"})


def probe_video(path: Path, *, limits: ProbeLimits = ProbeLimits()) -> tuple[dict, dict]:
    """Decode the entire video; never infer timing from nominal FPS.

    Loop budgets are not an OS sandbox for the native decoder. Inputs must be
    local regular files; protocol whitelist forbids playlist network access.
    """
    started, pts, durations, fingerprints = time.monotonic(), [], [], []
    shape, rotation, tb = None, None, None
    pixels, next_sample = 0, Fraction(0)
    with open_local_video(path) as container:
        if len(container.streams.video) != 1:
            raise SourceRejected("expected_one_video_stream")
        stream = container.streams.video[0]
        stream.codec_context.thread_count = 1
        if not stream.time_base or stream.time_base <= 0:
            raise SourceRejected("missing_time_base")
        tb = Fraction(stream.time_base)
        for frame in container.decode(stream):
            if len(pts) >= limits.max_frames or time.monotonic() - started > limits.max_decode_seconds:
                raise SourceRejected("decode_budget")
            size = frame.width * frame.height
            pixels += size
            if min(frame.width, frame.height) <= 0 or size > limits.max_frame_pixels or pixels > limits.max_decoded_pixels:
                raise SourceRejected("pixel_budget")
            if frame.pts is None or not frame.time_base:
                raise SourceRejected("missing_pts")
            source_pts = Fraction(frame.pts) * frame.time_base / tb
            if source_pts.denominator != 1:
                raise SourceRejected("incompatible_time_base")
            point = int(source_pts)
            if pts and point <= pts[-1]:
                raise SourceRejected("nonmonotonic_pts")
            angle = int(frame.rotation) % 360
            if angle not in (0, 90, 180, 270):
                raise SourceRejected("unsupported_rotation")
            for side in frame.side_data:
                if side.type.name == "DISPLAYMATRIX":
                    matrix = struct.unpack("=9i", bytes(side))
                    a, b, u, c, d, v, x, y, w = matrix
                    if (a*a + b*b != 65536**2 or c*c + d*d != 65536**2
                            or a*c + b*d != 0 or a*d-b*c != 65536**2
                            or any((u, v, x, y)) or w != 1 << 30):
                        raise SourceRejected("unsupported_display_transform")
            # Some containers expose the legacy tag instead of display-matrix.
            legacy = stream.metadata.get("rotate")
            if legacy is not None:
                try:
                    tagged = Fraction(legacy) % 360
                except (ValueError, ZeroDivisionError):
                    raise SourceRejected("invalid_rotation_metadata")
                if tagged.denominator != 1 or int(tagged) not in (0, 90, 180, 270):
                    raise SourceRejected("unsupported_rotation")
                if angle not in (0, int(tagged)):
                    raise SourceRejected("conflicting_rotation_metadata")
                angle = int(tagged)
            current_shape = (frame.width, frame.height)
            if shape is not None and (shape != current_shape or rotation != angle):
                raise SourceRejected("changing_geometry")
            shape, rotation = current_shape, angle
            pts.append(point)
            duration = Fraction(frame.duration or 0) * frame.time_base
            durations.append(duration)
            elapsed = (point - pts[0]) * tb
            if len(fingerprints) < 8 and elapsed >= next_sample:
                fingerprints.append(dhash64(frame.to_image()))
                next_sample = elapsed + 1
        if not pts:
            raise SourceRejected("no_decodable_frames")
        if durations[-1] > 0:
            end = pts[-1] * tb + durations[-1]
        elif stream.duration is not None and stream.start_time is not None:
            end = (stream.start_time + stream.duration) * tb
        else:
            raise SourceRejected("unknown_final_frame_duration")
        duration_sec = end - pts[0] * tb
        if duration_sec <= 0 or end <= pts[-1] * tb:
            raise SourceRejected("invalid_duration")
    deltas = [b-a for a,b in zip(pts, pts[1:])]
    metadata = {"duration_sec": float(duration_sec), "width": shape[0], "height": shape[1],
                "source_start_pts": pts[0], "time_base": {"num": tb.numerator, "den": tb.denominator},
                "rotation": rotation, "vfr": len(set(deltas)) > 1}
    audit = {"decoded_frames": len(pts), "last_source_pts": pts[-1],
             "timing": "decoded_pts", "rotation_convention": "counterclockwise_degrees",
             "fingerprint_method": "dhash64-first-8-at-1sec-v1", "fingerprints": fingerprints,
             "pts_sha256": stable_hash(pts)}
    return metadata, audit


def build_manifest(root: Path, sources: list[dict], *, dataset_version: str,
                   limits: ProbeLimits = ProbeLimits()) -> dict:
    root = Path(root).resolve(strict=True)
    if not root.is_dir() or not isinstance(dataset_version, str) or not dataset_version.strip():
        raise ValueError("source root/version required")
    if not isinstance(sources, list) or any(not isinstance(s, dict) or not isinstance(s.get("path"), str) for s in sources):
        raise ValueError("sources must be a list of path records")
    if len(sources) > limits.max_sources:
        raise ValueError("source count limit")
    paths = [s["path"] for s in sources]
    if len(paths) != len(set(paths)):
        raise ValueError("source paths must be unique")
    records, audits, fingerprints = [], [], {}
    for source in sorted(sources, key=lambda s: s["path"]):
        relative = source["path"]
        row = {"path": relative, "source_id": source.get("source_id"), "sha256": None,
               "rights": source.get("rights", "unknown"), "kind": source.get("kind", "unknown"),
               "group_id": source.get("group_id"), "viewpoint": source.get("viewpoint"),
               "availability": "unverified", "quarantine_reason": None, "eligible_for_split": False}
        if row["rights"] not in ("unknown", "confirmed", "restricted"):
            raise ValueError("rights must be explicit unknown/confirmed/restricted")
        try:
            path = local_source(root, relative)
            row["sha256"] = source_hash(path, limits.max_source_bytes)
            row["size_bytes"] = path.stat().st_size
            before = path.stat()
            metadata, decode = probe_video(path, limits=limits)
            after = path.stat()
            if ((before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
                    or source_hash(path, limits.max_source_bytes) != row["sha256"]):
                raise SourceRejected("source_changed")
            if row["kind"] not in ("original", "synthetic"):
                raise SourceRejected("provenance_kind_unknown")
            video_id = "video-" + stable_hash(relative)[:24]
            source_id = row["source_id"]
            group_id = row["group_id"]
            missing = [key for key, value in (("source_id", source_id), ("group_id", group_id))
                       if not isinstance(value, str) or not value.strip()]
            # Missing identities remain excluded and are not invented as real groups.
            canonical = "sha256:" + row["sha256"]
            records.append({"video_id": video_id, "canonical_id": canonical,
                            "group_id": group_id if "group_id" not in missing else "unverified:" + video_id,
                            "scene_id": video_id + ":unsegmented", "path": relative,
                            "sha256": row["sha256"], "split": "excluded", **metadata, "official_label": None,
                            "provenance": {"kind": row["kind"], "source_id": source_id if "source_id" not in missing else video_id,
                                           "sha256": row["sha256"]}})
            row.update(availability="available", video_id=video_id, decode=decode,
                       identity_missing=missing, eligible_for_split=not missing and row["rights"] == "confirmed")
            fingerprints[video_id] = decode["fingerprints"]
        except SourceRejected as exc:
            row.update(availability="missing" if str(exc) == "source_missing" else "quarantined",
                       quarantine_reason=str(exc))
        except (OSError, ValueError, EOFError):
            row.update(availability="quarantined", quarantine_reason="decode_or_io_error")
        audits.append(row)
    manifest = None
    if records:
        manifest = {"schema_version": "1.0", "dataset_version": dataset_version,
                    "split_version": "unassigned-v1", "videos": records}
        validate_contract("manifest", manifest)
    duplicate = duplicate_report(records, fingerprints)
    return {"manifest": manifest,
            "audit": {"audit_version": "import-v1", "dataset_version": dataset_version,
                      "sources": audits, "source_config_sha256": stable_hash(sources), "limits": asdict(limits),
                      "valid_video_count": len(records), "data_state": "imported_unassigned" if records else "data_not_ready",
                      "training_ready": False, "annotations_reviewed": False,
                      "limitations": ["Import/decode is not annotation or ML validation.",
                                      "Unsegmented scene placeholders require D4 scene review.",
                                      "Native decode loop budgets do not provide OS process isolation."]},
            "duplicates": duplicate}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="new local JSON bundle; never overwrite")
    args = parser.parse_args(argv)
    import yaml
    try:
        config = yaml.safe_load(args.config.read_text(encoding="utf-8-sig"))
        result = build_manifest(Path(config["source_root"]), config["sources"],
                                dataset_version=config["dataset_version"],
                                limits=ProbeLimits(**config.get("probe_limits", {})))
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.write("\n")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps({"videos": result["audit"]["valid_video_count"],
                      "data_state": result["audit"]["data_state"], "training_ready": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
