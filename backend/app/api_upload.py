"""Bounded multipart admission; production wiring and auth are supplied by A/A3."""
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import inspect
import time

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException

from contracts.python_ports import CapacityExceeded, ContractError, ModelNotReady, PersistenceUnavailable, validate_contract
from .storage import IntakeError


class UploadService:
    def __init__(self, storage, validator, repository, release):
        self.storage, self.validator, self.repository, self.release = storage, validator, repository, release

    def check_ready(self):
        try:
            readiness = self.release.readiness()
            validate_contract('diagnostics', readiness)
        except (ContractError, ModelNotReady, OSError):
            raise IntakeError(503, 'model_not_ready', 'A validated trained release is unavailable.') from None
        if readiness.get('status') != 'ready':
            raise IntakeError(503, 'model_not_ready', 'Import a validated trained release.')

    async def accept(self, upload, *, received_at=None, deadline_monotonic=None):
        self.check_ready()
        received_at = received_at or datetime.now(timezone.utc)
        deadline_monotonic = deadline_monotonic or time.monotonic() + 240
        staged = await self.storage.spool(upload, deadline_monotonic=deadline_monotonic)
        original, preserve = None, False
        try:
            validated = await asyncio.to_thread(self.validator.validate, staged.path,
                size_bytes=staged.size_bytes, deadline_monotonic=deadline_monotonic)
            if validated.sha256 != staged.sha256:
                raise IntakeError(400, 'invalid_request', 'Upload changed during validation.')
            if time.monotonic() >= deadline_monotonic:
                raise IntakeError(400, 'invalid_request', 'Upload time budget exceeded.')
            original = self.storage.promote(staged.path)
            validated = replace(validated, path=original)
            # After commit dispatch the outcome may be ambiguous on disconnect or
            # database failure. Preserve the original for reference-aware cleanup.
            preserve = True
            task = asyncio.create_task(asyncio.to_thread(self.repository.create, validated, now=received_at))
            task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            try:
                record = await asyncio.shield(task)
            except CapacityExceeded:
                preserve = False
                raise IntakeError(429, 'capacity_exceeded', 'One unfinished job is already accepted.') from None
            except PersistenceUnavailable:
                raise IntakeError(503, 'service_unavailable', 'Durable acceptance could not be confirmed.') from None
            return {'job_id': record.job_id}
        except OSError:
            raise IntakeError(503, 'service_unavailable', 'Upload storage is unavailable.') from None
        finally:
            self.storage.discard(staged.path)
            if original is not None and not preserve:
                self.storage.discard(original)


def create_upload_router(service: UploadService, authorize) -> APIRouter:
    """authorize(request) must raise on denial and runs before body parsing."""
    class BoundedUploadRoute(APIRoute):
        def get_route_handler(self):
            handler = super().get_route_handler()
            async def bounded(request: Request):
                try:
                    authorization = authorize(request)
                    if inspect.isawaitable(authorization):
                        await authorization
                    service.check_ready()
                    max_body = service.storage.max_bytes + 65536
                    length = request.headers.get('content-length')
                    if length is not None:
                        try:
                            length = int(length)
                            if length < 0:
                                raise ValueError
                        except ValueError:
                            raise IntakeError(400, 'invalid_request', 'Invalid content length.') from None
                        if length > max_body:
                            raise IntakeError(413, 'upload_too_large', 'Upload exceeds the byte limit.')
                    request.state.received_at = datetime.now(timezone.utc)
                    request.state.deadline_monotonic = time.monotonic() + 240
                    receive, total = request._receive, 0
                    async def limited_receive():
                        nonlocal total
                        remaining = request.state.deadline_monotonic - time.monotonic()
                        if remaining <= 0:
                            raise HTTPException(400, 'Upload time budget exceeded.')
                        try:
                            message = await asyncio.wait_for(receive(), remaining)
                        except asyncio.TimeoutError:
                            raise HTTPException(400, 'Upload time budget exceeded.') from None
                        total += len(message.get('body', b''))
                        if total > max_body:
                            raise HTTPException(413, 'Upload exceeds the byte limit.')
                        return message
                    request._receive = limited_receive
                    return await handler(request)
                except IntakeError as error:
                    return JSONResponse(error.payload(), status_code=error.status)
                except RequestValidationError:
                    failure = IntakeError(400, 'invalid_request', 'Exactly one multipart file is required.')
                    return JSONResponse(failure.payload(), status_code=400)
                except HTTPException as error:
                    codes = {400: 'invalid_request', 401: 'invalid_key', 413: 'upload_too_large'}
                    failure = IntakeError(error.status_code, codes.get(error.status_code, 'invalid_request'),
                                          'Request could not be accepted.')
                    return JSONResponse(failure.payload(), status_code=failure.status)
            return bounded
    router = APIRouter(route_class=BoundedUploadRoute)
    @router.post('/api/v1/analyze', status_code=202)
    async def analyze(request: Request, file: UploadFile | None = File(None)):
        form = await request.form()
        if file is None or len(form.multi_items()) != 1 or list(form.keys()) != ['file']:
            raise IntakeError(400, 'invalid_request', 'Exactly one multipart file is required.')
        return await service.accept(file, received_at=request.state.received_at,
                                    deadline_monotonic=request.state.deadline_monotonic)
    return router
