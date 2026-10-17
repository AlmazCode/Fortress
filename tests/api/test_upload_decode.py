"""A2 uses actual FFmpeg media and PostgreSQL; readiness below is a test stub."""
import asyncio
import io
import json
from pathlib import Path
import subprocess
import sys
import time

import httpx
import pytest
from fastapi import FastAPI, UploadFile

from test_persistence import database


def make_clip(path, *, size='64x48', rate='10', duration='1', extra=()):
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i',
                    f'testsrc2=size={size}:rate={rate}:duration={duration}',
                    '-c:v', 'libx264', '-threads', '1', '-pix_fmt', 'yuv420p',
                    *extra, '-y', str(path)], check=True, timeout=20, capture_output=True)
    return path


@pytest.fixture
def clip(tmp_path):
    return make_clip(tmp_path / 'source.mp4')


class ReadyModel:
    def readiness(self):
        return {'schema_version': '1.0', 'status': 'ready', 'reason': None,
                'release_version': 'synthetic-readiness-stub', 'trained': True,
                'validated': True, 'test_only': False, 'limitations': ['TEST STUB ONLY']}


def validator(**kwargs):
    from backend.app.video import VideoValidator
    return VideoValidator(**kwargs)


def validate(path, **kwargs):
    return validator(**kwargs).validate(path, size_bytes=path.stat().st_size,
                                      deadline_monotonic=time.monotonic() + 30)


def test_real_decode_and_nonzero_source_pts(tmp_path):
    path = make_clip(tmp_path / 'offset.mov', extra=('-output_ts_offset', '3.5'))
    result = validate(path)
    assert result.video.source_start_pts * result.video.time_base_num / result.video.time_base_den == pytest.approx(3.5)
    assert result.video.duration_sec == pytest.approx(1, abs=.05)
    assert result.video.width == 64 and result.video.height == 48
    assert len(result.sha256) == 64 and result.path == path.resolve()


def test_rotation_and_vfr_are_preserved(tmp_path, clip):
    rotated = tmp_path / 'rotated.mov'
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-display_rotation:v:0', '90',
                    '-i', str(clip), '-c', 'copy', str(rotated)], check=True, capture_output=True)
    assert validate(rotated).video.rotation == 90
    vfr = make_clip(tmp_path / 'vfr.mp4', extra=('-vf', r'setpts=if(lt(N\,5)\,N/(10*TB)\,(N-5)/(5*TB)+0.5/TB)', '-fps_mode', 'vfr'))
    result = validate(vfr)
    assert result.video.vfr is True and result.video.fps <= 10.1


@pytest.mark.parametrize('damage', ['random', 'truncated'])
def test_damaged_media_is_rejected(tmp_path, clip, damage):
    from backend.app.storage import IntakeError
    path = tmp_path / 'looks-valid.mp4'
    path.write_bytes(b'not a video' if damage == 'random' else clip.read_bytes()[:100])
    with pytest.raises(IntakeError) as caught:
        validate(path)
    assert caught.value.status == 400


def test_decoder_timeout_is_bounded(tmp_path, clip):
    from backend.app.storage import IntakeError
    executable = tmp_path / 'slow-probe'
    executable.write_text(f'#!{sys.executable}\nimport time\ntime.sleep(10)\n')
    executable.chmod(0o700)
    start = time.monotonic()
    with pytest.raises(IntakeError) as caught:
        validate(clip, ffprobe=str(executable), timeout_seconds=.15)
    assert caught.value.status == 400 and time.monotonic() - start < 2


@pytest.mark.asyncio
async def test_202_only_after_durable_original_job_and_outbox(database, tmp_path, clip):
    from backend.app.api_upload import UploadService, create_upload_router
    from backend.app.storage import LocalStorage
    _, repo = database
    storage = LocalStorage(tmp_path / 'runtime')
    service = UploadService(storage, validator(), repo, ReadyModel())
    async def authorize(request):
        return None  # A2 isolated route harness; real key checks belong to A3/A.
    app = FastAPI()
    app.include_router(create_upload_router(service, authorize))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
        response = await client.post('/api/v1/analyze', files={'file': ('../../escape.mov', clip.read_bytes(), 'video/quicktime')})
    assert response.status_code == 202, response.text
    assert set(response.json()) == {'job_id'}
    job = repo.get(response.json()['job_id'])
    assert job.upload.path.parent == storage.originals and job.upload.path.exists()
    assert job.upload.path.read_bytes() == clip.read_bytes()
    assert len(repo.pending_outbox()) == 1
    assert list(storage.incoming.iterdir()) == []
    assert not (tmp_path / 'escape.mov').exists()


@pytest.mark.asyncio
async def test_missing_model_and_busy_reject_before_acceptance(database, tmp_path, clip):
    from backend.app.api_upload import UploadService
    from backend.app.storage import IntakeError, LocalStorage
    _, repo = database
    storage = LocalStorage(tmp_path / 'runtime')
    service = UploadService(storage, validator(), repo, ReadyModel())
    first = await service.accept(UploadFile(io.BytesIO(clip.read_bytes()), filename='file.mp4'))
    with pytest.raises(IntakeError) as busy:
        await service.accept(UploadFile(io.BytesIO(clip.read_bytes()), filename='file.mp4'))
    assert busy.value.status == 429 and len(list(storage.originals.iterdir())) == 1
    class NotReady:
        def readiness(self):
            result = ReadyModel().readiness()
            result.update(status='not_ready', trained=False, validated=False, reason='missing', release_version=None)
            return result
    service.release = NotReady()
    with pytest.raises(IntakeError) as missing:
        await service.accept(UploadFile(io.BytesIO(b'invalid file'), filename='file.mp4'))
    assert missing.value.status == 503
    assert repo.get(first['job_id']) is not None


@pytest.mark.asyncio
async def test_cancellation_during_commit_preserves_original(database, tmp_path, clip):
    from backend.app.api_upload import UploadService
    from backend.app.storage import LocalStorage
    import threading
    _, repo = database
    entered, release = threading.Event(), threading.Event()
    saved = []
    class SlowCommit:
        def create(self, original, **kwargs):
            entered.set()
            release.wait(5)
            record = repo.create(original, **kwargs)
            saved.append(record)
            return record
    storage = LocalStorage(tmp_path / 'runtime')
    task = asyncio.create_task(UploadService(storage, validator(), SlowCommit(), ReadyModel()).accept(
        UploadFile(io.BytesIO(clip.read_bytes()), filename='file.mp4')))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
    for _ in range(100):
        if saved:
            break
        await asyncio.sleep(.02)
    assert saved and saved[0].upload.path.exists()
    assert repo.get(saved[0].job_id) is not None
