"""Protected public status and separate UI data routes."""
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter
from .jobs import public_job
from .schemas import job_diagnostics
from .storage import IntakeError
from contracts.python_ports import validate_contract


def create_api_router(repository, release, *, test_only=False):
    router = APIRouter()
    def get_job(job_id):
        repository.expire(now=datetime.now(timezone.utc))
        job = repository.get(job_id)
        if job is None:
            raise IntakeError(404, 'job_not_found', 'Job is unavailable.')
        return job
    @router.get('/api/v1/jobs/{job_id}')
    async def status(job_id: str):
        return public_job(await asyncio.to_thread(get_job, job_id))
    @router.get('/api/ui/v1/jobs/{job_id}')
    async def diagnostics(job_id: str):
        return job_diagnostics(await asyncio.to_thread(get_job, job_id), test_only=test_only)
    @router.get('/api/ui/v1/model')
    async def model():
        readiness = await asyncio.to_thread(release.readiness)
        validate_contract('diagnostics', readiness)
        return readiness
    return router
