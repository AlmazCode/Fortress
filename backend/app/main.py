"""Application/worker assembly. No training or synthetic production fallback."""
import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from contracts.python_ports import ContractError, PersistenceUnavailable
from .api import create_api_router
from .api_upload import UploadService, create_upload_router
from .auth import ApiKeyAuth, ApiKeyMiddleware
from .celery_app import create_celery
from .db import create_db_engine, migrate
from .deadlines import DeadlineRunner
from .jobs import JobRepository
from .media import MediaService, create_media_router
from .outbox import CeleryPublisher, OutboxDispatcher
from .schemas import MissingRelease, MissingRunner, media_links
from .settings import Settings
from .storage import IntakeError, LocalStorage
from .tasks import AnalysisFailure, TaskExecutor, register_tasks
from .video import VideoValidator


def _components(settings, test_components):
    if test_components is not None and settings.profile != 'test':
        raise ValueError('Synthetic components require the explicit test profile')
    if settings.profile == 'test' and test_components is None:
        raise ValueError('Test profile requires explicit test components')
    return ((test_components.release, test_components.runner, test_components.upload_service_factory)
            if test_components is not None else (MissingRelease(), MissingRunner(), UploadService))


class PreparedRunner:
    """Include preview construction in the same accepted job's time budget."""
    def __init__(self, runner, media):
        self.runner, self.media = runner, media

    def analyze(self, job, *, deadline_monotonic):
        result = self.runner.analyze(job, deadline_monotonic=deadline_monotonic)
        try:
            self.media.preview(job.job_id, deadline_monotonic=deadline_monotonic)
        except IntakeError:
            raise AnalysisFailure('evidence_failed') from None
        result.diagnostics['media'] = media_links(job)
        return result


def worker_factory(settings, runner):
    def factory():
        engine = create_db_engine(settings.database_url)
        repository = JobRepository(engine)
        storage = LocalStorage(settings.runtime_root)
        media = MediaService(repository, storage)
        executor = TaskExecutor(repository, DeadlineRunner(PreparedRunner(runner, media)), storage.root / 'gpu.lock')
        class ManagedExecutor:
            def execute(self, job_id):
                try:
                    return executor.execute(job_id)
                finally:
                    engine.dispose()
        return ManagedExecutor()
    return factory


def create_worker_app(settings=None, *, test_components=None):
    settings = settings or Settings.from_env()
    _, runner, _ = _components(settings, test_components)
    app = create_celery(settings.redis_url)
    register_tasks(app, worker_factory(settings, runner))
    return app


def create_app(settings=None, *, test_components=None):
    settings = settings or Settings.from_env()
    release, runner, upload_factory = _components(settings, test_components)
    engine = create_db_engine(settings.database_url)
    repository = JobRepository(engine)
    storage = LocalStorage(settings.runtime_root)
    media = MediaService(repository, storage)
    auth = ApiKeyAuth(settings.api_key)
    celery = create_worker_app(settings, test_components=test_components)
    dispatcher = OutboxDispatcher(repository, CeleryPublisher(celery))
    async def dispatch_until_stopped(stop):
        while not stop.is_set():
            try:
                await asyncio.to_thread(dispatcher.tick)
            except PersistenceUnavailable:
                pass  # DB remains authoritative; next bounded sweep retries.
            try:
                await asyncio.wait_for(stop.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass
    @asynccontextmanager
    async def lifespan(app):
        stop = asyncio.Event()
        dispatch_task = asyncio.create_task(dispatch_until_stopped(stop))
        try:
            yield
        finally:
            stop.set()
            await dispatch_task
            celery.close()
            engine.dispose()
    app = FastAPI(title='Fortress', version='1.0', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(ApiKeyMiddleware, auth=auth)
    app.state.repository, app.state.storage, app.state.media = repository, storage, media
    app.state.celery, app.state.dispatcher = celery, dispatcher
    app.include_router(create_upload_router(upload_factory(storage, VideoValidator(), repository, release), auth))
    app.include_router(create_api_router(repository, release, test_only=settings.profile == 'test'))
    app.include_router(create_media_router(media))
    @app.middleware('http')
    async def private_responses(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'private, no-store'
            response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
    @app.exception_handler(IntakeError)
    async def intake_error(request, error):
        return JSONResponse(error.payload(), status_code=error.status)
    @app.exception_handler(PersistenceUnavailable)
    @app.exception_handler(ContractError)
    async def service_error(request, error):
        failure = IntakeError(503, 'service_unavailable', 'Service data is temporarily unavailable.')
        return JSONResponse(failure.payload(), status_code=503)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        failure = IntakeError(400, 'invalid_request', 'Invalid request.')
        return JSONResponse(failure.payload(), status_code=400)
    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        status = error.status_code
        code = {400: 'invalid_request', 401: 'invalid_key', 404: 'not_found', 413: 'upload_too_large', 415: 'unsupported_media', 429: 'capacity_exceeded'}.get(status, 'invalid_request')
        failure = IntakeError(status, code, 'Request could not be completed.')
        return JSONResponse(failure.payload(), status_code=status)
    @app.get('/healthz')
    async def health():
        return {'status': 'ok'}  # Liveness only; model readiness is protected.
    return app


def main():
    parser = argparse.ArgumentParser(description='Fortress local backend; training deferred')
    parser.add_argument('command', choices=['api', 'worker', 'migrate', 'dispatch'])
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.command == 'api':
        import uvicorn
        uvicorn.run(create_app(settings), host=args.host, port=args.port, access_log=False)
    elif args.command == 'worker':
        create_worker_app(settings).Worker(pool='prefork', concurrency=1, loglevel='WARNING', quiet=True,
            without_gossip=True, without_mingle=True).start()
    else:
        engine = create_db_engine(settings.database_url)
        try:
            if args.command == 'migrate':
                migrate(engine)
            else:
                import time
                celery = create_celery(settings.redis_url)
                dispatcher = OutboxDispatcher(JobRepository(engine), CeleryPublisher(celery))
                try:
                    while True:
                        try:
                            dispatcher.tick()
                        except PersistenceUnavailable:
                            pass
                        time.sleep(1)
                finally:
                    celery.close()
        finally:
            engine.dispose()


if __name__ == '__main__':
    main()
