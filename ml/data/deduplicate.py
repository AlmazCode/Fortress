"""Exact clusters and conservative near-duplicate candidates; never deletes sources."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re

from PIL import Image


def stable_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def dhash64(image: Image.Image) -> str:
    gray = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = gray.tobytes()
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | (pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    return f"{bits:016x}"


@dataclass(frozen=True)
class NearConfig:
    method: str = "dhash64-first-8-at-1sec-v1"
    max_hamming: int = 4
    min_samples: int = 3
    min_duration_ratio: float = 0.95
    max_pairs: int = 200000

    def __post_init__(self):
        if (self.method != "dhash64-first-8-at-1sec-v1" or not 0 <= self.max_hamming <= 64
                or not 1 <= self.min_samples <= 8 or not 0 < self.min_duration_ratio <= 1
                or self.max_pairs < 1):
            raise ValueError("invalid near-duplicate configuration")


def duplicate_report(records: list[dict], fingerprints: dict[str, list[str]], *,
                     config: NearConfig = NearConfig()) -> dict:
    rows = sorted(records, key=lambda row: row["video_id"])
    if len({r["video_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate video ID")
    if len(rows) * (len(rows) - 1) // 2 > config.max_pairs:
        raise ValueError("pair budget exceeded; partition audit workload explicitly")
    groups = {}
    for row in rows:
        if not re.fullmatch("[a-f0-9]{64}", row["sha256"]):
            raise ValueError("invalid source SHA-256")
        groups.setdefault(row["sha256"], []).append(row["video_id"])
        for sample in fingerprints.get(row["video_id"], []):
            if not re.fullmatch("[a-f0-9]{16}", sample):
                raise ValueError("invalid dHash sample")
    exact = [{"cluster_id": "sha256:" + sha, "sha256": sha, "video_ids": members}
             for sha, members in sorted(groups.items()) if len(members) > 1]
    near = []
    for i, left in enumerate(rows):
        for right in rows[i + 1:]:
            if left["sha256"] == right["sha256"]:
                continue
            a, b = fingerprints.get(left["video_id"], []), fingerprints.get(right["video_id"], [])
            if min(len(a), len(b)) < config.min_samples:
                continue
            durations = (left["duration_sec"], right["duration_sec"])
            if min(durations) <= 0 or min(durations) / max(durations) < config.min_duration_ratio:
                continue
            distances = [(int(x, 16) ^ int(y, 16)).bit_count() for x, y in zip(a, b)]
            if max(distances) <= config.max_hamming:
                near.append({"video_ids": [left["video_id"], right["video_id"]],
                             "distances": distances, "review_status": "candidate",
                             "reason": "aligned early visual hashes; not proof of identity"})
    settings = asdict(config)
    return {"method_version": "duplicates-v1", "config": settings, "config_sha256": stable_hash(settings),
            "exact_clusters": exact, "near_candidates": near, "originals_deleted": False,
            "limitations": ["Early dHash can miss edits/shifts and can match static scenes; review source pixels.",
                            "Candidate edges are conservatively grouped for split, not assigned canonical identity."]}
