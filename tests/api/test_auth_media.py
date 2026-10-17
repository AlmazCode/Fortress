"""A3 auth uses a shared operator key; it does not claim per-user isolation."""
from datetime import datetime, timezone
import io
from uuid import uuid4

from fastapi import FastAPI, UploadFile
import httpx
import pytest

from test_persistence import database, bundle
from test_upload_decode import clip, ReadyModel, validator

KEY = 'test-only-shared-operator-key-32-chars'


async def media_app(database, tmp_path, clip):
    from backend.app.api_upload import UploadService
    from backend.app.auth import ApiKeyAuth, ApiKeyMiddleware
    from backend.app.media import MediaService, create_media_router
    from backend.app.storage import LocalStorage
    _, repo = database
    storage = LocalStorage(tmp_path / 'runtime')
    accepted = await UploadService(storage, validator(), repo, ReadyModel()).accept(UploadFile(io.BytesIO(clip.read_bytes()), filename='private-name.mov'))
    job = repo.get(accepted['job_id'])
    auth = ApiKeyAuth(KEY)
    service = MediaService(repo, storage)
    app = FastAPI()
    app.add_middleware(ApiKeyMiddleware, auth=auth)
    app.include_router(create_media_router(service))
    # The middleware covers all API routes; final public/UI routing belongs to A.
    for path in ['/api/v1/jobs/{job_id}', '/api/ui/v1/jobs/{job_id}', '/api/ui/v1/model']:
        app.add_api_route(path, lambda: {'protected': True})
    return app, service, job


@pytest.mark.asyncio
async def test_auth_precedes_every_data_endpoint_and_body(database, tmp_path, clip, caplog):
    app, service, job = await media_app(database, tmp_path, clip)
    paths = [f'/api/v1/jobs/{job.job_id}', f'/api/ui/v1/jobs/{job.job_id}', '/api/ui/v1/model',
             f'/api/ui/v1/jobs/{job.job_id}/media', f'/api/ui/v1/jobs/{job.job_id}/preview',
             f'/api/ui/v1/jobs/{job.job_id}/frames/v0f0']
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        for path in paths:
            for headers in [{}, {'X-API-Key': 'wrong'}, {'X-API-Key': KEY + '-wrong'}]:
                response = await client.get(path, headers=headers)
                assert response.status_code == 401 and response.json()['error']['code'] == 'invalid_key'
            assert (await client.get(path + '?api_key=' + KEY)).status_code == 401
        response = await client.get(paths[3], headers={'X-API-Key': KEY})
        assert response.status_code == 200 and response.content == clip.read_bytes()
        assert response.headers['cache-control'] == 'private, no-store'
        assert 'private-name' not in str(response.headers)
        assert str(service.storage.root) not in str(response.headers)
        missing = await client.get(f'/api/ui/v1/jobs/{uuid4()}/media', headers={'X-API-Key': KEY})
        assert missing.status_code == 404
    # Application code emits no key/path/body logs. HTTP client's own debug logging is outside the service.
    assert not [r for r in caplog.records if r.name.startswith('backend')]


@pytest.mark.asyncio
async def test_missing_preview_frame_and_corrupt_jpeg_preserve_job(database, tmp_path, clip):
    from backend.app.jobs import public_job
    app, service, job = await media_app(database, tmp_path, clip)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers={'X-API-Key': KEY}) as client:
        prefix = f'/api/ui/v1/jobs/{job.job_id}'
        assert (await client.get(prefix + '/frames/v0f0')).status_code == 404
        preview = await client.get(prefix + '/preview')
        assert preview.status_code == 200 and preview.headers['content-type'] == 'video/mp4'
        job.upload.path.unlink()
        assert (await client.get(prefix + '/media')).status_code == 404
        assert (await client.get(prefix + '/preview')).status_code == 404
        assert public_job(service.repository.get(job.job_id))['status'] == 'processing'


@pytest.mark.asyncio
async def test_frame_endpoint_returns_exact_committed_jpeg(database, tmp_path, clip):
    import base64
    from backend.app.media import EvidenceProvider
    app, service, job = await media_app(database, tmp_path, clip)
    frames = EvidenceProvider().frames(job.upload.path, [.3], deadline_monotonic=__import__('time').monotonic()+10)
    result = bundle(job.job_id)
    result.public.update(verdict='violation', violations=[{'type': 'test-event', 'timecode_sec': .3,
                         'description': 'Synthetic check', 'evidence_frames': [frames[0].public()]}])
    now = datetime.now(timezone.utc)
    lease = service.repository.claim(job.job_id, 'test', now=now)
    assert service.repository.finish(lease, result, now=now)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers={'X-API-Key': KEY}) as client:
        response = await client.get(f'/api/ui/v1/jobs/{job.job_id}/frames/v0f0')
        assert response.status_code == 200 and response.content == frames[0].jpeg
        assert response.headers['content-type'] == 'image/jpeg'
        assert (await client.get(f'/api/ui/v1/jobs/{job.job_id}/frames/unknown')).status_code == 404
    assert service.repository.get(job.job_id).result == result.public


def test_missing_configuration_and_duplicate_headers_fail_closed():
    from backend.app.auth import ApiKeyAuth
    from starlette.requests import Request
    from starlette.exceptions import HTTPException
    with pytest.raises(ValueError):
        ApiKeyAuth('')
    auth = ApiKeyAuth(KEY)
    request = Request({'type': 'http', 'headers': [(b'x-api-key', KEY.encode()), (b'x-api-key', KEY.encode())]})
    with pytest.raises(HTTPException) as error:
        auth(request)
    assert error.value.status_code == 401

@pytest.mark.asyncio
async def test_corrupt_source_and_saved_frame_return_error_without_losing_result(database, tmp_path, clip):
    import copy
    import time
    from sqlalchemy import update
    from backend.app.media import EvidenceProvider
    from backend.app.models import Result
    app, service, job = await media_app(database, tmp_path, clip)
    frames = EvidenceProvider().frames(job.upload.path, [.3], deadline_monotonic=time.monotonic()+10)
    result = bundle(job.job_id)
    result.public.update(verdict='violation', violations=[{'type': 'test', 'timecode_sec': .3, 'description': 'Synthetic', 'evidence_frames': [frames[0].public()]}])
    now = datetime.now(timezone.utc)
    assert service.repository.finish(service.repository.claim(job.job_id, 'test', now=now), result, now=now)
    service.preview(job.job_id)
    data = bytearray(job.upload.path.read_bytes())
    data[-1] ^= 1
    job.upload.path.write_bytes(data)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers={'X-API-Key': KEY}) as client:
        prefix = f'/api/ui/v1/jobs/{job.job_id}'
        assert (await client.get(prefix + '/preview')).status_code == 400
        assert (await client.get(prefix + '/media')).status_code == 400
        broken = copy.deepcopy(result.public)
        broken['violations'][0]['evidence_frames'][0]['image_base64'] = 'YmFk'
        with database[0].begin() as connection:
            connection.execute(update(Result).values(public=broken))
        assert (await client.get(prefix + '/frames/v0f0')).status_code == 400
    stored = service.repository.get(job.job_id)
    assert stored.state == 'done' and stored.result == broken
