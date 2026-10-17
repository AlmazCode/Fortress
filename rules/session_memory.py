"""Per-job, whole-video observations with explicit links and scene boundaries."""
from __future__ import annotations

import json
from typing import Any

from .types import Observation, SessionSpan


class SessionMemory:
    def __init__(self, job_id: str, video_id: str):
        if not job_id or not video_id:
            raise ValueError('Memory needs an explicit job and video')
        self.job_id = job_id
        self.video_id = video_id
        self.scene_id: str | None = None
        self._by_scene: dict[str, dict[str, Observation]] = {}
        self.sessions: list[SessionSpan] = []
        self.unresolved: set[tuple[str, str, str]] = set()
        self.unknown_links: bool = False
        self.late_scene_events: int = 0

    @property
    def observations(self) -> tuple[Observation, ...]:
        return tuple(sorted(self._by_scene.get(self.scene_id, {}).values(), key=lambda o:(o.interval.start_sec,o.interval.end_sec,o.class_id)))

    @property
    def whole_video_observations(self) -> tuple[Observation, ...]:
        return tuple(o for scene in self._by_scene.values() for o in scene.values())

    def ingest(self, timeline: dict[str, Any], *, job_id: str) -> None:
        if job_id != self.job_id or timeline['video_id'] != self.video_id:
            raise ValueError('Memory cannot cross job or video boundaries')
        scene = timeline['scene_id']
        if scene != self.scene_id and scene in self._by_scene:
            self.late_scene_events += len(timeline['observations'])
            return  # Never reactivate the actors or money from a closed scene.
        observations = [Observation.from_json(raw) for raw in timeline['observations']]
        if any(o.interval.scene_id != scene for o in observations):
            raise ValueError('Observation scene differs from window scene')
        if scene != self.scene_id:
            for span in self.sessions:
                if span.scene_id == self.scene_id and span.end_sec is None:
                    span.closed_by_scene = True
            self.scene_id = scene
            self._by_scene[scene] = {}
            self.unresolved.clear()
            self.unknown_links = True  # A cut is not evidence of a completed stage.
        for raw, observation in zip(timeline['observations'], observations):
            signature = json.dumps(raw, sort_keys=True, separators=(',',':'), allow_nan=False)
            self._by_scene[scene].setdefault(signature, observation)
        self._rebuild_scene_state()

    def _rebuild_scene_state(self) -> None:
        current = self.scene_id
        self.sessions = [span for span in self.sessions if span.scene_id != current]
        self.unresolved = set()
        open_sessions: dict[tuple[str, str], SessionSpan] = {}
        for observation in self.observations:
            if not observation.observed:
                continue  # Occlusion never resolves an open obligation.
            known = [r for r in observation.relations if r.known]
            if observation.actor_id is None or any(not r.known for r in observation.relations):
                self.unknown_links = True
            for relation in known:
                if relation.kind == 'session' and relation.subject_id == observation.actor_id:
                    key = (relation.subject_id, relation.object_id)
                    if observation.class_id == 'service_start':
                        if key not in open_sessions:
                            span = SessionSpan(relation.object_id, observation.actor_id, current, observation.interval.start_sec)
                            open_sessions[key] = span
                            self.sessions.append(span)
                    elif observation.class_id == 'service_end' and key in open_sessions:
                        open_sessions.pop(key).end_sec = observation.interval.end_sec
                if relation.kind == 'party':
                    key = (current, relation.subject_id, relation.object_id)
                    if observation.class_id == 'party_opened':
                        self.unresolved.add(key)
                    elif observation.class_id in ('party_stored','party_cleared'):
                        self.unresolved.discard(key)

    def snapshot(self) -> dict[str, Any]:
        return {'job_id':self.job_id, 'video_id':self.video_id, 'scene_id':self.scene_id,
                'observation_count':len(self.whole_video_observations),
                'current_observation_count':len(self.observations), 'unknown_links':self.unknown_links,
                'unresolved':sorted(self.unresolved), 'late_scene_events':self.late_scene_events,
                'sessions':[vars(span).copy() for span in self.sessions]}
