import io
import os
import time

import httpx
import pytest
from fastapi import FastAPI, UploadFile

from test_upload_decode import ReadyModel, clip, make_clip, validate, validator
from test_persistence import database


@pytest.mark.parametrize('size', ['1920x1080', '1080x1920'])
def test_both_max_orientations_are_valid(tmp_path, size):
    path = make_clip(tmp_path / 'valid.mp4', size=size, rate='2', duration='0.5')
    assert validate(path).video.duration_sec <= 1


@pytest.mark.parametrize('settings', [dict(size='1922x1080', rate='2', duration='0.5'),
                                     dict(size='16x16', rate='61', duration='0.5'),
                                     dict(size='16x16', rate='2', duration='181')])
def test_metadata_and_decode_limits_reject_unsupported_media(tmp_path, settings):
    from backend.app.storage import IntakeError
    path = make_clip(tmp_path / 'over.mp4', **settings)
    with pytest.raises(IntakeError) as caught:
        validate(path)
    assert caught.value.status == 415


def test_container_is_checked_independently_of_filename(tmp_path):
    from backend.app.storage import IntakeError
    path = make_clip(tmp_path / 'pretend.mp4', extra=('-f', 'avi'))
    with pytest.raises(IntakeError) as caught:
        validate(path)
    assert caught.value.status == 415


@pytest.mark.asyncio
async def test_stream_size_limit_cleans_partial_file(tmp_path):
    from backend.app.storage import IntakeError, LocalStorage
    storage = LocalStorage(tmp_path / 'runtime', max_bytes=32)
    with pytest.raises(IntakeError) as caught:
        await storage.spool(UploadFile(io.BytesIO(b'x' * 100), filename='x'), deadline_monotonic=time.monotonic()+5)
    assert caught.value.status == 413
    assert list(storage.incoming.iterdir()) == []


@pytest.mark.asyncio
async def test_disk_failure_is_503_and_cleans_temp_file(tmp_path, monkeypatch):
    from backend.app.storage import IntakeError, LocalStorage
    storage = LocalStorage(tmp_path / 'runtime')
    def full_disk(_):
        raise OSError('injected disk failure')
    monkeypatch.setattr(os, 'fsync', full_disk)
    with pytest.raises(IntakeError) as caught:
        await storage.spool(UploadFile(io.BytesIO(b'x'), filename='x'), deadline_monotonic=time.monotonic()+5)
    assert caught.value.status == 503 and list(storage.incoming.iterdir()) == []


@pytest.mark.asyncio
async def test_route_bounds_body_before_multipart_parsing(database, tmp_path):
    from backend.app.api_upload import UploadService, create_upload_router
    from backend.app.storage import LocalStorage
    _, repo = database
    async def authorize(request):
        pass
    service = UploadService(LocalStorage(tmp_path / 'runtime', max_bytes=32), validator(), repo, ReadyModel())
    app = FastAPI()
    app.include_router(create_upload_router(service, authorize))
    async def body():
        yield b'--abc\r\nContent-Disposition: form-data; name="file"; filename="file.mp4"\r\nContent-Type: video/mp4\r\n\r\n'
        for _ in range(10):
            yield b'x' * 65536
        yield b'\r\n--abc--\r\n'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
        response = await client.post('/api/v1/analyze', content=body(), headers={'content-type': 'multipart/form-data; boundary=abc'})
        assert response.status_code == 413
        response = await client.post('/api/v1/analyze', content=b'no body', headers={'content-length': str(300*1024*1024)})
        assert response.status_code == 413
        response = await client.post('/api/v1/analyze', files={'different': ('x', b'abc')})
        assert response.status_code == 400
    assert list(service.storage.incoming.iterdir()) == []

@pytest.mark.asyncio
async def test_malformed_multipart_and_non_file_field_use_contract_errors(tmp_path):
    import httpx
    from fastapi import FastAPI
    from backend.app.api_upload import UploadService, create_upload_router
    from backend.app.storage import LocalStorage
    from test_upload_decode import ReadyModel, validator
    app = FastAPI()
    app.include_router(create_upload_router(UploadService(LocalStorage(tmp_path / 'runtime'), validator(), None, ReadyModel()), lambda request: None))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        responses = [await client.post('/api/v1/analyze', content=b'invalid', headers={'content-type': 'multipart/form-data'}),
                     await client.post('/api/v1/analyze', data={'file': 'not a file'})]
    for response in responses:
        assert response.status_code == 400
        assert response.json()['error']['code'] == 'invalid_request'


@pytest.mark.asyncio
async def test_invalid_readiness_fails_closed_without_reading_file(tmp_path):
    from backend.app.api_upload import UploadService
    from backend.app.storage import IntakeError, LocalStorage
    from test_upload_decode import validator
    class InvalidRelease:
        def readiness(self):
            return {'status': 'ready'}
    with pytest.raises(IntakeError) as caught:
        await UploadService(LocalStorage(tmp_path / 'runtime'), validator(), None, InvalidRelease()).accept(None)
    assert caught.value.status == 503
    assert caught.value.code == 'model_not_ready'
