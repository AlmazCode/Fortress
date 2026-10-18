"""Same-origin Windows prototype with genuine model, UI, API and private media."""
import argparse
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import threading

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from contracts.python_ports import ContractError, PersistenceUnavailable, validate_contract
from backend.app.api import create_api_router
from backend.app.api_upload import UploadService, create_upload_router
from backend.app.auth import ApiKeyAuth, ApiKeyMiddleware
from backend.app.media import MediaService, create_media_router
from backend.app.schemas import MissingRelease
from backend.app.storage import IntakeError, LocalStorage
from backend.app.video import VideoValidator
from .inference import model_limitations, predictor
from .repository import LocalRepository
from .power import IdleSleepInhibitor
from .runtime import run_worker


def load_config(path):
    config = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if config['device'] not in ('cpu', 'cuda') or config.get('prototype_enabled') is not True:
        raise ValueError('Explicit prototype configuration and device required')
    for key in ('runtime_root', 'bundle_root', 'api_key_file', 'ffmpeg_dir'):
        p = Path(config[key]).resolve()
        if not p.is_absolute() or any((parent/'.git').exists() for parent in [p, *p.parents]):
            raise ValueError('Private configuration paths must be outside Git')
    config['api_key'] = json.loads(Path(config['api_key_file']).read_text(encoding='utf-8-sig'))['api_key']
    ApiKeyAuth(config['api_key'])
    os.environ['PATH'] = config['ffmpeg_dir']+os.pathsep+os.environ.get('PATH', '')
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    return config


class PrototypeRelease:
    def __init__(self, config):
        self.path = Path(config['bundle_root'])/'weights.pt'
        model = predictor(config['bundle_root'], config['device'])
        self.digest = model.metadata['weights_sha256']
        prefix = 'prototype-weak-risk-' if model.metadata.get('risk_extension') else 'prototype-uniform-gru-'
        if model.metadata.get('seed_vote_extension'):
            self.path = Path(config['bundle_root'])/'control'/'weights.pt'
            self.digest = model.metadata['seed_vote_extension']['model_sha256']
            prefix = 'prototype-seed-vote-'
        if model.metadata.get('source_action_extension'):
            self.path = Path(config['bundle_root'])/'seed_vote'/'control'/'weights.pt'
            self.digest = model.metadata['source_action_extension']['model_sha256']
            prefix = 'prototype-source-actions-'
        self.integrity_files = getattr(model, 'integrity_files', [(self.path, self.digest)])
        self.version = prefix+self.digest[:12]
        self.limitations = model_limitations(model.metadata)
        del model

    def readiness(self):
        try:
            valid = True
            for path, digest in self.integrity_files:
                with path.open('rb') as stream:
                    valid = valid and hashlib.file_digest(stream, 'sha256').hexdigest() == digest
        except OSError:
            valid = False
        if not valid:
            return MissingRelease().readiness()
        return {'schema_version': '1.0', 'status': 'prototype', 'reason': 'experimental_model',
                'release_version': self.version, 'trained': True, 'validated': False,
                'test_only': False, 'limitations': self.limitations}


class PrototypeUpload(UploadService):
    def check_ready(self):
        value = self.release.readiness()
        validate_contract('diagnostics', value)
        if value['status'] != 'prototype' or not value['trained'] or value['validated'] or value['test_only']:
            raise IntakeError(503, 'model_not_ready', 'A configured local prototype is unavailable.')


def create_app(config, frontend_root, *, release=None, start_worker=True):
    root = Path(config['runtime_root'])
    storage = LocalStorage(root/'media', sync_directories=os.name != 'nt')
    repo = LocalRepository(root/'jobs.sqlite3')
    release = release if release is not None else PrototypeRelease(config)
    media = MediaService(repo, storage)
    auth = ApiKeyAuth(config['api_key'])
    sleep_inhibitor = IdleSleepInhibitor()
    @asynccontextmanager
    async def lifespan(app):
        stop = threading.Event()
        worker = threading.Thread(target=run_worker, args=(repo, config, stop, sleep_inhibitor), name='native-worker', daemon=True)
        if start_worker:
            worker.start()
        try:
            yield
        finally:
            stop.set()
            if start_worker:
                worker.join(timeout=10)
    app = FastAPI(title='Fortress local prototype', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(ApiKeyMiddleware, auth=auth)
    app.state.repository, app.state.media, app.state.release = repo, media, release
    app.include_router(create_upload_router(PrototypeUpload(storage, VideoValidator(), repo, release), auth))
    app.include_router(create_api_router(repo, release))
    app.include_router(create_media_router(media))
    @app.exception_handler(IntakeError)
    async def intake(request, error):
        return JSONResponse(error.payload(), status_code=error.status)
    @app.exception_handler(PersistenceUnavailable)
    @app.exception_handler(ContractError)
    async def unavailable(request, error):
        return JSONResponse(IntakeError(503, 'service_unavailable', 'Service temporarily unavailable.').payload(), status_code=503)
    @app.exception_handler(RequestValidationError)
    async def validation(request, error):
        return JSONResponse(IntakeError(400, 'invalid_request', 'Invalid request.').payload(), status_code=400)
    @app.exception_handler(HTTPException)
    async def http(request, error):
        code = 'job_not_found' if error.status_code == 404 else 'invalid_request'
        return JSONResponse(IntakeError(error.status_code, code, 'Request could not be completed.').payload(), status_code=error.status_code)
    @app.middleware('http')
    async def private_responses(request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'private, no-store'
        return response
    @app.get('/healthz')
    async def health():
        return {'status': 'ok', 'mode': 'prototype', 'production_ready': False,
                'idle_sleep_inhibited': sleep_inhibitor.active}
    @app.get('/api/ui/v1/rules')
    async def normative_rules():
        from rules.rk_cash import catalog
        return catalog()
    @app.post('/api/local/v1/shutdown')
    async def shutdown():
        callback = getattr(app.state, 'request_shutdown', None)
        if callback is None:
            raise IntakeError(503, 'service_unavailable', 'Shutdown is unavailable.')
        callback()
        return {'status': 'stopping'}
    frontend_root = Path(frontend_root).resolve()
    if not (frontend_root/'index.html').is_file():
        raise ValueError('Build frontend before starting the service')
    app.mount('/', StaticFiles(directory=frontend_root, html=True), name='frontend')
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--frontend', type=Path, default=Path(__file__).resolve().parents[2]/'frontend'/'dist')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    import uvicorn
    app = create_app(load_config(args.config), args.frontend)
    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, access_log=False, log_level='warning'))
    app.state.request_shutdown = lambda: setattr(server, 'should_exit', True)
    server.run()


if __name__ == '__main__':
    main()
