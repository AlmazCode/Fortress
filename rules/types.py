"""Internal rule state; serialized findings retain the K contract."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any


class Truth(str, Enum):
    TRUE = 'true'
    FALSE = 'false'
    UNKNOWN = 'unknown'


@dataclass(frozen=True)
class Interval:
    start_sec: float
    end_sec: float
    scene_id: str

    def __post_init__(self):
        if not self.scene_id or not all(math.isfinite(x) and x >= 0 for x in (self.start_sec, self.end_sec)) or self.end_sec < self.start_sec:
            raise ValueError('Invalid source-time interval')

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> 'Interval':
        return cls(float(value['start_sec']), float(value['end_sec']), value['scene_id'])

    def as_json(self) -> dict[str, Any]:
        return {'start_sec':self.start_sec, 'end_sec':self.end_sec, 'scene_id':self.scene_id}


@dataclass(frozen=True)
class Relation:
    kind: str
    subject_id: str | None
    object_id: str | None
    known: bool

    def __post_init__(self):
        if self.known and (not self.subject_id or not self.object_id):
            raise ValueError('Known relation needs both endpoints')


@dataclass(frozen=True)
class Observation:
    class_id: str
    interval: Interval
    score: float | None
    state: str
    known_mask: bool
    visibility: str
    actor_id: str | None
    relations: tuple[Relation, ...] = ()

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> 'Observation':
        return cls(value['class_id'], Interval.from_json(value['interval']), value['score'], value['state'],
                   value['known_mask'], value['visibility'], value['actor_id'],
                   tuple(Relation(**r) for r in value['relations']))

    @property
    def observed(self) -> bool:
        return self.known_mask and self.state == 'present' and self.visibility in ('visible','partial')


@dataclass
class SessionSpan:
    reference_id: str | None
    actor_id: str | None
    scene_id: str
    start_sec: float
    end_sec: float | None = None
    visibility_complete: bool = False
    closed_by_scene: bool = False


@dataclass(frozen=True)
class RuleInputs:
    """Explicit evidence supplied by a validated producer; defaults fail closed.

    These are internal evaluator inputs, not extra fields appended to K events.
    A global timeline score does not populate identity or completeness flags.
    """
    antecedent: Truth = Truth.UNKNOWN
    condition: Truth = Truth.UNKNOWN
    exception: Truth = Truth.UNKNOWN
    interval_complete: bool = False
    visibility_complete: bool = False
    recognizer_validated: bool = False
    stage_ended: bool = False
    alternatives_checked: bool = False
    relations_known: bool = False
    video_id: str | None = None
    scene_id: str | None = None
    interval: Interval | None = None

    @property
    def absence_ready(self) -> bool:
        return all((self.interval_complete, self.visibility_complete, self.recognizer_validated,
                    self.stage_ended, self.alternatives_checked, self.relations_known))
