"""Regression for Windows preview fsync and actual ffprobe/FFmpeg source PTS."""
from dataclasses import replace
from datetime import datetime, timezone
import shutil
import subprocess
import time

import pytest

from backend.app.media import MediaService
from backend.app.storage import LocalStorage
from backend.app.video import VideoValidator
from backend.local.repository import LocalRepository


def test_actual_native_mov_promote_decode_preview_and_source_frame(tmp_path):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('Actual FFmpeg/ffprobe required')
    storage = LocalStorage(tmp_path/'runtime'/'media', sync_directories=False)
    staged = storage.incoming/'native.mov'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=96x64:rate=30',
                    '-t','1','-an','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(staged)],check=True)
    validated = VideoValidator().validate(staged,size_bytes=staged.stat().st_size,deadline_monotonic=time.monotonic()+30)
    original = storage.promote(staged)
    repo = LocalRepository(tmp_path/'runtime'/'jobs.sqlite3')
    job = repo.create(replace(validated,path=original),now=datetime.now(timezone.utc))
    media = MediaService(repo,storage)
    preview = media.preview(job.job_id,deadline_monotonic=time.monotonic()+30)
    assert preview.is_file() and preview.stat().st_size > 100
    assert media.preview(job.job_id) == preview
    frame = media.evidence.frames(original,[.5],deadline_monotonic=time.monotonic()+30)[0]
    assert frame.jpeg.startswith(b'\xff\xd8') and abs(frame.timestamp_sec-.5)<.04
    assert original.read_bytes() and not staged.exists()
