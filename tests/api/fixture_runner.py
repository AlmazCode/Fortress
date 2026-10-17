"""Explicit test injection only. Production code never imports this module."""
from dataclasses import dataclass
import time

from backend.app.api_upload import UploadService
from backend.app.media import EvidenceProvider
from backend.app.tasks import AnalysisFailure
from contracts.python_ports import AnalysisBundle


class FixtureRelease:
    def readiness(self):
        return {'schema_version': '1.0', 'status': 'not_ready', 'reason': 'model_not_ready',
                'release_version': None, 'trained': False, 'validated': False, 'test_only': True,
                'limitations': ['Synthetic API test profile; no trained or validated model.']}


class FixtureUploadService(UploadService):
    def check_ready(self):
        # Injection requires Settings(profile='test') and explicit components.
        # It does not falsify the UI's model readiness or production release.
        pass


class FixtureRunner:
    def __init__(self, mode='violation', delay=.1):
        self.mode, self.delay, self.calls = mode, delay, 0

    def analyze(self, job, *, deadline_monotonic):
        self.calls += 1
        time.sleep(self.delay)
        if self.mode == 'failed':
            raise AnalysisFailure('inference_failed')
        if self.mode == 'unknown':
            raise AnalysisFailure('insufficient_evidence')
        violations = []
        if self.mode == 'violation':
            evidence = EvidenceProvider().frames(job.upload.path, [.2], deadline_monotonic=deadline_monotonic)
            violations = [{'type': 'synthetic_test_event', 'timecode_sec': .2, 'description': 'Synthetic software check, no legal or ML conclusion.',
                           'evidence_frames': [frame.public() for frame in evidence]}]
        public = {'job_id': job.job_id, 'status': 'done', 'verdict': 'violation' if violations else 'no_violation', 'violations': violations}
        diagnostics = {'schema_version': '1.0', 'job_id': job.job_id, 'public': public, 'stage': 'done',
            'processed_sec': job.upload.video.duration_sec, 'duration_sec': job.upload.video.duration_sec,
            'coverage': 'partial', 'unknown': ['Real events not evaluated.'], 'unsupported': ['All production rules.'],
            'limitations': ['TEST ONLY: synthetic fixture, not ML validation.'],
            'versions': {name: None for name in ['dataset', 'annotations', 'split', 'rules', 'model', 'preprocessing', 'taxonomy']},
            'timeline': None, 'media': {'original': None, 'preview': None},
            'provenance': {'kind': 'synthetic', 'source_id': 'software-test', 'sha256': job.upload.sha256}}
        return AnalysisBundle(public, diagnostics)


@dataclass
class TestComponents:
    __test__ = False
    runner: FixtureRunner
    release: FixtureRelease = None
    upload_service_factory = FixtureUploadService

    def __post_init__(self):
        self.release = FixtureRelease()
