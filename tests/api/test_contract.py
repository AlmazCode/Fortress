"""Assembled FastAPI + PostgreSQL + Redis/Celery; one smoke uses real HTTP."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import socket
import threading
import time
from uuid import uuid4

from celery.contrib.testing.worker import start_worker
import httpx
import pytest
import uvicorn

from contracts.python_ports import validate_contract
from fixture_runner import FixtureRunner, TestComponents

KEY = 'test-only-shared-operator-key-32-chars'


def build(database, redis_runtime, tmp_path, *, mode='violation', production=False):
    from backend.app.main import create_app
    from backend.app.settings import Settings
    settings = Settings(api_key=KEY, database_url=database[0].url.render_as_string(hide_password=False),
                        redis_url=redis_runtime.url, runtime_root=tmp_path / 'runtime',
                        profile='production' if production else 'test')
    components = None if production else TestComponents(FixtureRunner(mode))
    return create_app(settings, test_components=components)


@contextmanager
def http_server(app):
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False, lifespan='on'))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    until = time.monotonic()+5
    while not server.started and time.monotonic() < until:
        time.sleep(.01)
    assert server.started
    try:
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit = True
        thread.join(timeout=8)
        sock.close()
        assert not thread.is_alive()


@pytest.mark.asyncio
async def test_real_http_upload_worker_result_diagnostics_media(database, redis_runtime, tmp_path, clip):
    app = build(database, redis_runtime, tmp_path)
    with start_worker(app.state.celery, pool='solo', perform_ping_check=False, loglevel='CRITICAL', shutdown_timeout=5), http_server(app) as url:
        async with httpx.AsyncClient(base_url=url, headers={'X-API-Key': KEY}) as client:
            assert (await client.get('/api/ui/v1/model')).json()['test_only'] is True
            response = await client.post('/api/v1/analyze', files={'file': ('private-source.mov', clip.read_bytes(), 'video/quicktime')})
            assert response.status_code == 202
            assert set(response.json()) == {'job_id'}
            job_id = response.json()['job_id']
            assert app.state.repository.get(job_id).upload.path.exists()
            until = time.monotonic()+10
            states = []
            while time.monotonic() < until:
                public = (await client.get(f'/api/v1/jobs/{job_id}')).json()
                validate_contract('job', public)
                states.append(public['status'])
                if public['status'] != 'processing': break
                await asyncio.sleep(.04)
            assert public['status'] == 'done' and public['verdict'] == 'violation'
            assert set(public) == {'job_id', 'status', 'verdict', 'violations'}
            diagnostics = (await client.get(f'/api/ui/v1/jobs/{job_id}')).json()
            validate_contract('diagnostics', diagnostics)
            assert diagnostics['provenance']['kind'] == 'synthetic'
            assert diagnostics['unknown'] and diagnostics['limitations']
            prefix = f'/api/ui/v1/jobs/{job_id}'
            assert (await client.get(prefix+'/media')).content == clip.read_bytes()
            preview = await client.get(prefix+'/preview')
            assert preview.status_code == 200 and preview.headers['content-type'] == 'video/mp4'
            frame = await client.get(prefix+'/frames/v0f0')
            assert frame.status_code == 200 and frame.content.startswith(b'\xff\xd8')
            for path in [f'/api/v1/jobs/{job_id}', prefix, prefix+'/media', prefix+'/preview', prefix+'/frames/v0f0']:
                assert (await client.get(path, headers={'X-API-Key': 'wrong'})).status_code == 401
            for frame_id in ['unknown', 'v99999f0', 'v0f2']:
                missing = await client.get(prefix + '/frames/' + frame_id)
                assert missing.status_code == 404
                assert missing.json()['error']['code'] == 'media_not_found'
                validate_contract('diagnostics', missing.json())


@pytest.mark.asyncio
async def test_real_http_not_found_jobs_use_contract_error_body(database, redis_runtime, tmp_path):
    app = build(database, redis_runtime, tmp_path, production=True)
    with http_server(app) as url:
        async with httpx.AsyncClient(base_url=url, headers={'X-API-Key': KEY}) as client:
            for job_id in [str(uuid4()), 'malformed-id']:
                for path in [f'/api/v1/jobs/{job_id}', f'/api/ui/v1/jobs/{job_id}',
                             f'/api/ui/v1/jobs/{job_id}/media', f'/api/ui/v1/jobs/{job_id}/preview',
                             f'/api/ui/v1/jobs/{job_id}/frames/v0f0']:
                    response = await client.get(path)
                    assert response.status_code == 404
                    assert response.json()['error']['code'] == 'job_not_found'
                    validate_contract('diagnostics', response.json())
                    assert response.headers['cache-control'] == 'private, no-store'
                    assert KEY not in response.text and str(tmp_path) not in response.text
            response = await client.get('/api/unknown-route')
            assert response.status_code == 404
            assert response.json()['error']['code'] == 'job_not_found'
            validate_contract('diagnostics', response.json())


@pytest.mark.asyncio
async def test_real_http_not_found_media_preserves_existing_job(database, redis_runtime, tmp_path, clip):
    app = build(database, redis_runtime, tmp_path)
    with http_server(app) as url:
        async with httpx.AsyncClient(base_url=url, headers={'X-API-Key': KEY}) as client:
            accepted = await client.post('/api/v1/analyze', files={'file': ('synthetic.mp4', clip.read_bytes())})
            assert accepted.status_code == 202
            job_id = accepted.json()['job_id']
            job = app.state.repository.get(job_id)
            job.upload.path.unlink()
            for suffix in ['/media', '/preview', '/frames/v0f0', '/frames/unknown']:
                response = await client.get(f'/api/ui/v1/jobs/{job_id}' + suffix)
                assert response.status_code == 404
                assert response.json()['error']['code'] == 'media_not_found'
                validate_contract('diagnostics', response.json())
                assert response.headers['cache-control'] == 'private, no-store'
                assert KEY not in response.text and str(tmp_path) not in response.text
            response = await client.get(f'/api/v1/jobs/{job_id}')
            assert response.status_code == 200 and response.json()['status'] == 'processing'


@pytest.mark.asyncio
async def test_production_without_model_never_accepts_or_uses_fixtures(database, redis_runtime, tmp_path, clip):
    app = build(database, redis_runtime, tmp_path, production=True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers={'X-API-Key': KEY}) as client:
        model = (await client.get('/api/ui/v1/model')).json()
        validate_contract('diagnostics', model)
        assert model['status'] != 'ready' and model['trained'] is False and model['test_only'] is False
        response = await client.post('/api/v1/analyze', files={'file': ('clip.mp4', clip.read_bytes())})
        assert response.status_code == 503 and response.json()['error']['code'] == 'model_not_ready'
        assert app.state.repository.pending_outbox() == []
        assert not list(app.state.storage.originals.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize('mode, expected', [('clean', 'no_violation'), ('failed', 'inference_failed'), ('unknown', 'insufficient_evidence')])
async def test_terminal_outcomes_preserve_public_contract(database, redis_runtime, tmp_path, clip, mode, expected):
    app = build(database, redis_runtime, tmp_path, mode=mode)
    async with app.router.lifespan_context(app):
        with start_worker(app.state.celery, pool='solo', perform_ping_check=False, loglevel='CRITICAL', shutdown_timeout=5):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers={'X-API-Key': KEY}) as client:
                response = await client.post('/api/v1/analyze', files={'file': ('clip.mp4', clip.read_bytes())})
                assert response.status_code == 202
                job_id = response.json()['job_id']
                until = time.monotonic()+8
                while time.monotonic() < until:
                    body = (await client.get(f'/api/v1/jobs/{job_id}')).json()
                    if body['status'] != 'processing': break
                    await asyncio.sleep(.03)
                validate_contract('job', body)
                assert body.get('reason', body.get('verdict')) == expected
                if mode != 'clean': assert 'violations' not in body


@pytest.mark.asyncio
async def test_assembled_api_error_matrix(database, redis_runtime, tmp_path, clip):
    app = build(database, redis_runtime, tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.post('/api/v1/analyze')).status_code == 401
        client.headers['X-API-Key'] = KEY
        checks = [await client.post('/api/v1/analyze'),
                  await client.post('/api/v1/analyze', files={'file': ('broken.mp4', b'not video')}),
                  await client.post('/api/v1/analyze', content=b'', headers={'Content-Length': str(201*1024*1024)})]
        assert [response.status_code for response in checks] == [400, 400, 413]
        for response in checks: validate_contract('diagnostics', response.json())
        from test_upload_decode import make_clip
        unsupported = make_clip(tmp_path / 'unsupported.avi')
        response = await client.post('/api/v1/analyze', files={'file': ('looks-valid.mp4', unsupported.read_bytes())})
        assert response.status_code == 415
        validate_contract('diagnostics', response.json())
        response = await client.post('/api/v1/analyze', files={'file': ('clip.mp4', clip.read_bytes())})
        assert response.status_code == 202
        duplicate = await client.post('/api/v1/analyze', files={'file': ('clip.mp4', clip.read_bytes())})
        assert duplicate.status_code == 429
        validate_contract('diagnostics', duplicate.json())


@pytest.mark.asyncio
async def test_real_database_unavailability_is_a_private_503(database, redis_runtime, tmp_path):
    from backend.app.db import create_db_engine
    app = build(database, redis_runtime, tmp_path)
    unavailable = create_db_engine(database[0].url.set(query={'host': str(tmp_path / 'missing-socket')}))
    original = app.state.repository.engine
    app.state.repository.engine = unavailable
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers={'X-API-Key': KEY}) as client:
            response = await client.get(f'/api/v1/jobs/{uuid4()}')
            assert response.status_code == 503
            validate_contract('diagnostics', response.json())
            assert str(tmp_path) not in response.text and KEY not in response.text
    finally:
        app.state.repository.engine = original
        unavailable.dispose()


def test_test_components_cannot_be_installed_in_production(database, redis_runtime, tmp_path):
    from backend.app.main import create_app
    from backend.app.settings import Settings
    settings = Settings(api_key=KEY, database_url=database[0].url.render_as_string(hide_password=False), redis_url=redis_runtime.url, runtime_root=tmp_path / 'runtime')
    with pytest.raises(ValueError): create_app(settings, test_components=TestComponents(FixtureRunner()))
    assert KEY not in repr(settings) and str(database[0].url) not in repr(settings)
