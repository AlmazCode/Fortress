"""Evidence and preview are checked against real decoded source PTS/pixels."""
import base64
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import time

from PIL import Image, ImageChops
import pytest
from fastapi import UploadFile

from test_persistence import database
from test_upload_decode import make_clip, validator, ReadyModel


def pts(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_frames',
        '-show_entries', 'frame=pts_time,width,height', '-of', 'json', str(path)], capture_output=True, check=True)
    return json.loads(result.stdout)['frames']


def source(tmp_path):
    original = make_clip(tmp_path / 'offset.mp4', extra=('-vf', r'setpts=if(lt(N\,5)\,N/(10*TB)\,(N-5)/(5*TB)+0.5/TB)', '-fps_mode', 'vfr', '-output_ts_offset', '3.5'))
    rotated = tmp_path / 'rotated.mov'
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-display_rotation:v:0', '90', '-i', str(original), '-c', 'copy', str(rotated)], capture_output=True, check=True)
    return rotated


def test_evidence_is_original_frame_with_nonzero_pts_vfr_and_rotation(tmp_path):
    from backend.app.media import EvidenceProvider
    path = source(tmp_path)
    provider = EvidenceProvider()
    frames = provider.frames(path, [0, .45, 1.2], deadline_monotonic=time.monotonic()+20)
    actual = pts(path)
    origin = float(actual[0]['pts_time'])
    assert len(frames) == 3
    for frame in frames:
        assert frame.timestamp_sec == pytest.approx((frame.source_pts-frame.origin_pts)*frame.time_base_num/frame.time_base_den)
        assert frame.timestamp_sec+origin == pytest.approx(float(actual[frame.index]['pts_time']))
        assert Image.open(io.BytesIO(frame.jpeg)).size == (48, 64)
        expected = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(path), '-vf', f'select=eq(n\\,{frame.index})', '-frames:v', '1', '-c:v', 'mjpeg', '-q:v', '2', '-threads', '1', '-f', 'image2pipe', '-'], capture_output=True, check=True)
        assert ImageChops.difference(Image.open(io.BytesIO(frame.jpeg)), Image.open(io.BytesIO(expected.stdout))).getbbox() is None
        assert base64.b64decode(frame.public()['image_base64'], validate=True) == frame.jpeg


@pytest.mark.asyncio
async def test_preview_preserves_elapsed_source_timeline_and_rotation(database, tmp_path):
    from backend.app.api_upload import UploadService
    from backend.app.media import MediaService
    from backend.app.storage import LocalStorage
    path = source(tmp_path)
    storage = LocalStorage(tmp_path / 'runtime')
    repo = database[1]
    accepted = await UploadService(storage, validator(), repo, ReadyModel()).accept(UploadFile(io.BytesIO(path.read_bytes())))
    service = MediaService(repo, storage)
    preview = service.preview(accepted['job_id'])
    before, after = pts(path), pts(preview)
    assert len(before) == len(after)
    origin = float(before[0]['pts_time'])
    assert [float(f['pts_time']) for f in after] == pytest.approx([float(f['pts_time'])-origin for f in before], abs=.0001)
    assert all((f['width'], f['height']) == (48, 64) for f in after)
    assert preview.stat().st_size <= 200*1024*1024
    assert service.preview(accepted['job_id']) == preview


def test_bad_or_out_of_range_frame_never_fabricates_evidence(tmp_path):
    from backend.app.media import EvidenceProvider
    from backend.app.storage import IntakeError
    path = source(tmp_path)
    provider = EvidenceProvider()
    for requested in [[-1], [float('nan')], [999], [], [0, .1, .2, .3]]:
        with pytest.raises(IntakeError):
            provider.frames(path, requested, deadline_monotonic=time.monotonic()+10)
    path.write_bytes(b'corrupted')
    with pytest.raises(IntakeError):
        provider.frames(path, [0], deadline_monotonic=time.monotonic()+10)
