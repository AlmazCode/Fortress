"""Local protected media, elapsed-PTS previews and genuine source JPEGs."""
import asyncio
import base64
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import io
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image

from contracts.python_ports import ContractError, PersistenceUnavailable, validate_contract
from .storage import IntakeError, MAX_UPLOAD_BYTES
from .video import VideoValidator

PRIVATE = {'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'}


def _ffmpeg(arguments, *, deadline, executable='ffmpeg'):
    remaining = min(120, deadline-time.monotonic())
    if remaining <= 0:
        raise IntakeError(400, 'invalid_request', 'Media time budget exceeded.')
    try:
        result = subprocess.run([executable, '-v', 'error', '-nostdin', '-max_alloc', '67108864',
            '-threads', '2', '-filter_threads', '1', '-protocol_whitelist', 'file',
            '-err_detect', 'explode', *arguments], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=remaining)
    except subprocess.TimeoutExpired:
        raise IntakeError(400, 'invalid_request', 'Media time budget exceeded.') from None
    except OSError:
        raise IntakeError(503, 'service_unavailable', 'Media runtime is unavailable.') from None
    if result.returncode:
        raise IntakeError(400, 'invalid_request', 'Media could not be decoded.')


def _jpeg(data):
    try:
        if len(data) > 16*1024*1024 or not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
            raise ValueError
        with Image.open(io.BytesIO(data)) as image:
            if image.format != 'JPEG' or max(image.size) > 1920 or min(image.size) > 1080:
                raise ValueError
            image.load()
    except (OSError, ValueError):
        raise IntakeError(400, 'invalid_request', 'Evidence frame is unavailable or damaged.') from None
    return data


@dataclass(frozen=True)
class SourceFrame:
    index: int
    source_pts: int
    origin_pts: int
    time_base_num: int
    time_base_den: int
    jpeg: bytes

    @property
    def timestamp_sec(self):
        return float((self.source_pts-self.origin_pts)*Fraction(self.time_base_num, self.time_base_den))

    def public(self):
        return {'timestamp_sec': self.timestamp_sec, 'image_base64': base64.b64encode(self.jpeg).decode('ascii')}


class EvidenceProvider:
    def __init__(self, *, ffmpeg='ffmpeg', ffprobe='ffprobe'):
        self.ffmpeg = ffmpeg
        self.validator = VideoValidator(ffprobe=ffprobe)

    def _index(self, path, deadline):
        try:
            info = self.validator.validate(path, size_bytes=Path(path).stat().st_size, deadline_monotonic=deadline).video
            frames = self.validator._run(['-select_streams', 'v:0', '-show_frames', '-show_entries', 'frame=pts', '-of', 'json', str(path)], deadline=deadline, max_output=4*1024*1024)['frames']
            points = [int(frame['pts']) for frame in frames]
            return info, points
        except (OSError, KeyError, ValueError) as error:
            if isinstance(error, IntakeError):
                raise
            raise IntakeError(400, 'invalid_request', 'Source frames are unavailable.') from None

    def frames(self, path, timestamps, *, deadline_monotonic):
        if not 1 <= len(timestamps) <= 3 or any(not math.isfinite(t) or t < 0 for t in timestamps):
            raise IntakeError(400, 'invalid_request', 'Request one to three valid source timestamps.')
        deadline = min(deadline_monotonic, time.monotonic()+120)
        info, points = self._index(path, deadline)
        if any(t >= info.duration_sec for t in timestamps):
            raise IntakeError(400, 'invalid_request', 'Frame timestamp is outside the source video.')
        elapsed = [(p-info.source_start_pts)*Fraction(info.time_base_num, info.time_base_den) for p in points]
        indices = dict.fromkeys(min(range(len(points)), key=lambda n: abs(float(elapsed[n])-t)) for t in timestamps)
        result = []
        # No user filename or filter expression is interpolated; n is a decoded frame index.
        with tempfile.TemporaryDirectory(prefix='fortress-evidence-') as directory:
            for index in indices:
                target = Path(directory) / f'{index}.jpg'
                _ffmpeg(['-i', str(path), '-map', '0:v:0', '-an', '-sn', '-dn', '-vf', f'select=eq(n\\,{index})',
                    '-frames:v', '1', '-c:v', 'mjpeg', '-q:v', '2', '-threads', '1', '-fs', str(16*1024*1024),
                    '-y', str(target)], deadline=deadline, executable=self.ffmpeg)
                try:
                    data = _jpeg(target.read_bytes())
                except OSError:
                    raise IntakeError(503, 'service_unavailable', 'Evidence storage is unavailable.') from None
                result.append(SourceFrame(index, points[index], info.source_start_pts, info.time_base_num, info.time_base_den, data))
        return result

    def extract(self, path, findings, *, deadline_monotonic):
        events = []
        for finding in findings:
            if finding['status'] != 'triggered':
                continue
            if finding['support'] != 'supported' or not finding['source']['verified']:
                raise ContractError('Evidence cannot authorize an unsupported finding')
            start, end = finding['interval']['start_sec'], finding['interval']['end_sec']
            if end < start:
                raise ContractError('Invalid finding interval')
            # Midpoint avoids selecting outside the supporting interval at its end.
            frames = self.frames(path, [(start+end)/2], deadline_monotonic=deadline_monotonic)
            if any(not start <= frame.timestamp_sec <= end for frame in frames):
                raise IntakeError(400, 'invalid_request', 'No source frame lies in the finding interval.')
            events.append({'type': finding['rule_id'], 'timecode_sec': start,
                           'description': finding['reason'], 'evidence_frames': [frame.public() for frame in frames]})
        return events


class MediaService:
    def __init__(self, repository, storage, *, ffmpeg='ffmpeg', ffprobe='ffprobe'):
        self.repository, self.storage = repository, storage
        self.ffmpeg = ffmpeg
        self.evidence = EvidenceProvider(ffmpeg=ffmpeg, ffprobe=ffprobe)
        self.cache = storage.root / 'previews'
        if self.cache.is_symlink():
            raise ValueError('Preview directory must not be a symlink')
        self.cache.mkdir(mode=0o700, exist_ok=True)
        self._lock, self._digests = threading.Lock(), {}

    def job(self, job_id):
        try:
            job = self.repository.get(job_id)
        except PersistenceUnavailable:
            raise IntakeError(503, 'service_unavailable', 'Job storage is unavailable.') from None
        if job is None:
            raise IntakeError(404, 'not_found', 'Job or media is unavailable.')
        return job

    def original(self, job_id):
        job = self.job(job_id)
        path = job.upload.path
        if (path.parent != self.storage.originals or path.is_symlink() or not re.fullmatch(r'[a-f0-9]{32}\.video', path.name)
                or not path.is_file()):
            raise IntakeError(404, 'not_found', 'Job or media is unavailable.')
        try:
            if path.stat().st_size != job.upload.size_bytes or not 0 < path.stat().st_size <= MAX_UPLOAD_BYTES:
                raise IntakeError(400, 'invalid_request', 'Original media is damaged.')
            with path.open('rb') as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != job.upload.sha256:
                    raise IntakeError(400, 'invalid_request', 'Original media is damaged.')
        except OSError:
            raise IntakeError(404, 'not_found', 'Job or media is unavailable.') from None
        return path

    def preview(self, job_id):
        path = self.original(job_id)
        job = self.job(job_id)
        deadline = time.monotonic()+120
        if not self._lock.acquire(timeout=120):
            raise IntakeError(503, 'service_unavailable', 'Preview generation is busy.')
        temporary = None
        try:
            target = self.cache / (job.upload.sha256 + '.mp4')
            if not target.is_symlink() and target.is_file() and target in self._digests:
                with target.open('rb') as source:
                    if hashlib.file_digest(source, 'sha256').hexdigest() == self._digests[target]:
                        return target
            descriptor, name = tempfile.mkstemp(dir=self.cache, suffix='.mp4')
            os.close(descriptor)
            temporary = Path(name)
            _ffmpeg(['-i', str(path), '-map', '0:v:0', '-an', '-sn', '-dn', '-map_metadata', '-1',
                     '-vf', 'setpts=PTS-STARTPTS', '-fps_mode', 'passthrough', '-enc_time_base', 'filter',
                     '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-threads', '2',
                     '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-fs', str(MAX_UPLOAD_BYTES),
                     '-y', str(temporary)], deadline=deadline, executable=self.ffmpeg)
            source_info, source_pts = self.evidence._index(path, deadline)
            preview_info, preview_pts = self.evidence._index(temporary, deadline)
            source_tb = Fraction(source_info.time_base_num, source_info.time_base_den)
            preview_tb = Fraction(preview_info.time_base_num, preview_info.time_base_den)
            if (len(source_pts) != len(preview_pts) or preview_info.rotation != 0 or
                any(abs(float((p-source_pts[0])*source_tb-q*preview_tb)) > .0001
                    for p, q in zip(source_pts, preview_pts))):
                raise IntakeError(400, 'invalid_request', 'Preview time mapping could not be verified.')
            with temporary.open('rb') as source:
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
                os.fsync(source.fileno())
            os.replace(temporary, target)
            self._digests[target] = digest
            return target
        except OSError:
            raise IntakeError(503, 'service_unavailable', 'Preview storage is unavailable.') from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            self._lock.release()

    def frame(self, job_id, frame_id):
        job = self.job(job_id)
        match = re.fullmatch(r'v([0-9]{1,5})f([0-2])', frame_id)
        if not match or job.result is None:
            raise IntakeError(404, 'not_found', 'Evidence frame is unavailable.')
        try:
            validate_contract('job', job.result)
            frame = job.result['violations'][int(match[1])]['evidence_frames'][int(match[2])]
            return _jpeg(base64.b64decode(frame['image_base64'], validate=True))
        except (IndexError, KeyError):
            raise IntakeError(404, 'not_found', 'Evidence frame is unavailable.') from None
        except (ValueError, ContractError):
            raise IntakeError(400, 'invalid_request', 'Evidence frame is unavailable or damaged.') from None


def create_media_router(service):
    """Install only behind ApiKeyMiddleware; the full application does so in A."""
    router = APIRouter()
    async def serve(job_id, kind, frame_id=None):
        try:
            if kind == 'frame':
                return Response(await asyncio.to_thread(service.frame, job_id, frame_id), media_type='image/jpeg', headers=PRIVATE)
            path = await asyncio.to_thread(service.original if kind == 'media' else service.preview, job_id)
            content_type = 'video/mp4'
            if kind == 'media':
                with path.open('rb') as source:
                    if source.read(12)[8:12] == b'qt  ':
                        content_type = 'video/quicktime'
            return FileResponse(path, media_type=content_type, headers=PRIVATE)
        except IntakeError as error:
            return JSONResponse(error.payload(), status_code=error.status, headers=PRIVATE)
        except OSError:
            error = IntakeError(503, 'service_unavailable', 'Media storage is unavailable.')
            return JSONResponse(error.payload(), status_code=503, headers=PRIVATE)
    @router.get('/api/ui/v1/jobs/{job_id}/media')
    async def original(job_id: str):
        return await serve(job_id, 'media')
    @router.get('/api/ui/v1/jobs/{job_id}/preview')
    async def preview(job_id: str):
        return await serve(job_id, 'preview')
    @router.get('/api/ui/v1/jobs/{job_id}/frames/{frame_id}')
    async def frame(job_id: str, frame_id: str):
        return await serve(job_id, 'frame', frame_id)
    return router
