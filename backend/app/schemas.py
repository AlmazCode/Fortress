"""Response builders obey the committed schemas; no public/UI field mixing."""
import copy
from contracts.python_ports import ModelNotReady, validate_contract
from .jobs import public_job
from .storage import MAX_UPLOAD_BYTES


class MissingRelease:
    def readiness(self):
        return {'schema_version': '1.0', 'status': 'not_ready', 'reason': 'model_not_ready',
                'release_version': None, 'trained': False, 'validated': False, 'test_only': False,
                'limitations': ['No validated trained release is loaded. ML adapter integration is required.']}

    def load(self, directory):
        raise ModelNotReady('Validated release loader is not integrated')


class MissingRunner:
    def analyze(self, job, *, deadline_monotonic):
        raise ModelNotReady('No validated analysis runtime is loaded')


def media_links(job):
    prefix = f'/api/ui/v1/jobs/{job.job_id}'
    return {name: {'url': prefix+suffix, 'content_type': 'video/mp4', 'max_bytes': MAX_UPLOAD_BYTES}
            for name, suffix in [('original', '/media'), ('preview', '/preview')]}


def job_diagnostics(job, *, test_only=False):
    if job.diagnostics is not None:
        result = copy.deepcopy(job.diagnostics)
    else:
        result = {'schema_version': '1.0', 'job_id': job.job_id, 'public': public_job(job),
            'stage': {'queued': 'queued', 'running': 'inference', 'failed': 'failed'}[job.state],
            'processed_sec': None, 'duration_sec': job.upload.video.duration_sec, 'coverage': 'none',
            'unknown': ['Analysis has no committed supported observations.'], 'unsupported': [],
            'limitations': ['A shared operator key does not provide per-user isolation.'],
            'versions': {key: None for key in ['dataset', 'annotations', 'split', 'rules', 'model', 'preprocessing', 'taxonomy']},
            'timeline': None, 'media': {'original': None, 'preview': None},
            'provenance': {'kind': 'synthetic' if test_only else 'original', 'source_id': job.job_id, 'sha256': job.upload.sha256}}
    result['media'] = media_links(job)
    if job.state != 'done':
        result['media']['preview'] = None
    validate_contract('diagnostics', result)
    return result
