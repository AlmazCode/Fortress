"""Shared synchronous ports and offline validators, contract version 1.0.

Implementations belong to A1–A5, M4 and R. No backend, training or network is
started here. JSON schemas are the serialized authority; these ports define IO.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from functools import lru_cache
import io
import json
import math
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Protocol, Sequence, TypedDict

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

JSON = dict[str, Any]
InternalState = Literal["queued", "running", "done", "failed"]


class ContractError(ValueError):
    """Invalid boundary payload; callers must not log raw media or secrets."""


class CapacityExceeded(RuntimeError):
    """Atomic admission denied: map to 429 before returning a job id."""


class PersistenceUnavailable(RuntimeError):
    """No confirmed durable acceptance: map to 503, never return 202."""


class ModelNotReady(RuntimeError):
    """No usable trained/validated production release: map to 503."""


@dataclass(frozen=True)
class VideoInfo:
    duration_sec: float
    width: int
    height: int
    fps: float
    rotation: int
    source_start_pts: int
    time_base_num: int
    time_base_den: int
    vfr: bool


@dataclass(frozen=True)
class AcceptedUpload:
    """Validated local original; path is internal and never a response field."""
    path: Path
    sha256: str
    size_bytes: int
    video: VideoInfo


@dataclass(frozen=True)
class JobLease:
    job_id: str
    owner: str
    token: int
    expires_at: datetime


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    state: InternalState
    accepted_at: datetime
    deadline_at: datetime
    upload: AcceptedUpload
    result: JSON | None = None
    diagnostics: JSON | None = None
    reason: str | None = None


@dataclass(frozen=True)
class OutboxItem:
    id: int
    job_id: str
    created_at: datetime


@dataclass(frozen=True)
class AnalysisBundle:
    public: JSON
    diagnostics: JSON


class JobRepository(Protocol):
    """PostgreSQL is authoritative; all datetime arguments are UTC-aware.

    create commits job + outbox + the single-capacity reservation atomically,
    after fsync of the original. A committed job survives client disconnect.
    Claim/renew/finish/fail compare the monotonic fencing token and deadline;
    stale, duplicate and late writes return False/None and never overwrite.
    An expired running lease may be reclaimed, not reset to a clean verdict.
    """
    def create(self, upload: AcceptedUpload, *, now: datetime,
               deadline_seconds: int = 240) -> JobRecord: ...
    def get(self, job_id: str) -> JobRecord | None: ...
    def claim(self, job_id: str, owner: str, *, now: datetime,
              lease_seconds: int = 30) -> JobLease | None: ...
    def renew(self, lease: JobLease, *, now: datetime,
              lease_seconds: int = 30) -> JobLease | None: ...
    def finish(self, lease: JobLease, result: AnalysisBundle, *, now: datetime) -> bool: ...
    def fail(self, lease: JobLease, reason: str, *, now: datetime) -> bool: ...
    def expire(self, *, now: datetime) -> Sequence[str]: ...
    def pending_outbox(self, *, limit: int = 100) -> Sequence[OutboxItem]: ...
    def mark_published(self, outbox_id: int, *, now: datetime) -> None: ...


class UploadValidator(Protocol):
    """Bound byte/CPU/time/decode work before acceptance; no shell commands."""
    def validate(self, path: Path, *, size_bytes: int,
                 deadline_monotonic: float) -> AcceptedUpload: ...


class ReleaseProvider(Protocol):
    """Offline only. Validate hashes, compatibility and non-test provenance."""
    def readiness(self) -> JSON: ...  # diagnostics.schema.json/$defs/Model
    def load(self, directory: Path) -> JSON: ...  # validated release descriptor


class TimelineProvider(Protocol):
    """events.schema.json output. Reset GRU/session at scene boundaries."""
    def infer(self, path: Path, *, deadline_monotonic: float) -> JSON: ...


class RuleEngine(Protocol):
    """Each finding is triggered/not_triggered/unknown, with source provenance."""
    def evaluate(self, timeline: JSON) -> Sequence[JSON]: ...


class EvidenceProvider(Protocol):
    """Only valid source frames, 1–3 real JPEGs per public violation."""
    def extract(self, path: Path, findings: Sequence[JSON], *,
                deadline_monotonic: float) -> Sequence[JSON]: ...


class AnalysisRunner(Protocol):
    """A: orchestration; M4: inference; R: rules. Synthetic runner is test-only.

    No usable model -> reject before create. After acceptance any failure is a
    durable failed job. Zero observable supported coverage -> insufficient_evidence;
    partial coverage may produce done but must retain limitations in diagnostics.
    """
    def analyze(self, job: JobRecord, *, deadline_monotonic: float) -> AnalysisBundle: ...


@lru_cache
def _schemas() -> tuple[dict[str, JSON], Registry]:
    directory = Path(__file__).parent
    schemas = {p.name.removesuffix(".schema.json"): json.loads(p.read_text())
               for p in directory.glob("*.schema.json")}
    # Registry without a retrieve callback: an unknown ref fails closed,
    # never performs a network fetch during inference.
    registry = Registry().with_resources(
        (s["$id"], Resource.from_contents(s)) for s in schemas.values()
    )
    return schemas, registry


def _walk(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError("Non-finite numeric value")
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def validate_contract(name: str, payload: JSON) -> None:
    """Validate schema and cross-field constraints without network or writes.

    This is structural validation, not evidence of source authenticity, actual
    dataset readiness, model quality or file hashes. The owning modules perform
    those IO checks and record real evidence before marking anything ready.
    """
    schemas, registry = _schemas()
    if name not in schemas:
        raise ContractError("Unknown contract")
    validator = Draft202012Validator(schemas[name], registry=registry,
                                     format_checker=FormatChecker())
    error = next(validator.iter_errors(payload), None)
    if error is not None:
        raise ContractError(f"{name}: invalid structure at "
                            + "/".join(map(str, error.absolute_path)))

    for item in _walk(payload):
        if {"start_sec", "end_sec"} <= item.keys():
            if item["end_sec"] < item["start_sec"]:
                raise ContractError("Interval end precedes start")
        if {"source_pts", "origin_pts", "time_base", "timestamp_sec"} <= item.keys():
            tb = item["time_base"]
            expected = float((item["source_pts"] - item["origin_pts"])
                             * Fraction(tb["num"], tb["den"]))
            if not math.isclose(expected, item["timestamp_sec"], abs_tol=1e-6):
                raise ContractError("Source PTS mapping disagrees with timestamp")
        if "image_base64" in item:
            try:
                from PIL import Image
                data = base64.b64decode(item["image_base64"], validate=True)
                if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
                    raise ContractError("Evidence JPEG is incomplete")
                with Image.open(io.BytesIO(data)) as image:
                    if (image.format != "JPEG" or max(image.size) > 1920
                            or min(image.size) > 1080):
                        raise ContractError("Evidence must be a bounded JPEG")
                    # JPEG verify() only checks the header. Decode bounded pixels
                    # too; the explicit EOI check also covers tolerant decoders.
                    image.load()
            except (ValueError, OSError) as error:
                raise ContractError("Evidence is not a valid JPEG") from error

    if name == "manifest":
        ids: set[str] = set()
        partitions: dict[tuple[str, str], str] = {}
        for record in payload["videos"]:
            if record["video_id"] in ids:
                raise ContractError("Duplicate video id")
            ids.add(record["video_id"])
            if record["split"] == "excluded":
                continue
            for key in ("canonical_id", "group_id"):
                identity = (key, record[key])
                previous = partitions.setdefault(identity, record["split"])
                if previous != record["split"]:
                    raise ContractError("Canonical video/group crosses split")
    elif name == "objects":
        for frame in payload["frames"]:
            for item in frame["objects"]:
                x, y, width, height = item["bbox"]
                if x + width > frame["width"] or y + height > frame["height"]:
                    raise ContractError("Object box is outside source frame")
    elif name == "diagnostics" and "public" in payload:
        if payload["public"]["job_id"] != payload["job_id"]:
            raise ContractError("Diagnostics belongs to another job")
        if payload["coverage"] == "none" and payload["public"]["status"] == "done":
            raise ContractError("No observable coverage cannot yield done")
    elif name == "release":
        paths = [entry["path"] for entry in payload["files"]]
        if len(paths) != len(set(paths)):
            raise ContractError("Duplicate release path")
        required = {payload["checkpoint"], payload["taxonomy"]["path"],
                    payload["thresholds"], payload["metrics"]["path"], payload["model_card"]}
        if not required <= set(paths):
            raise ContractError("Release manifest omits a required artifact")
        if payload["intended_use"] == "production":
            if any(entry["sha256"] == "0" * 64 for entry in payload["files"]):
                raise ContractError("Placeholder hash cannot be production")
