import asyncio
from datetime import datetime, timezone
import io

import pytest
from fastapi import UploadFile

from test_persistence import database
from test_upload_decode import clip, ReadyModel, validator


@pytest.mark.asyncio
async def test_concurrent_real_uploads_have_one_slot_and_failure_releases_it(database, tmp_path, clip):
    from backend.app.api_upload import UploadService
    from backend.app.storage import IntakeError, LocalStorage
    repo = database[1]
    storage = LocalStorage(tmp_path / 'runtime')
    service = UploadService(storage, validator(), repo, ReadyModel())
    async def accept():
        try:
            return await service.accept(UploadFile(io.BytesIO(clip.read_bytes())))
        except IntakeError as error:
            return error.status
    outcomes = await asyncio.gather(*(accept() for _ in range(8)))
    accepted = [x for x in outcomes if isinstance(x, dict)]
    assert len(accepted) == 1 and outcomes.count(429) == 7
    assert len(list(storage.originals.iterdir())) == 1 and not list(storage.incoming.iterdir())
    lease = repo.claim(accepted[0]['job_id'], 'test', now=datetime.now(timezone.utc))
    assert repo.fail(lease, 'inference_failed', now=datetime.now(timezone.utc))
    assert isinstance(await accept(), dict)
