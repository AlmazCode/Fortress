"""A5 deadline checks use wall time and real PostgreSQL, never fake a pass."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import time

import pytest
from sqlalchemy import text

from test_persistence import database, upload, bundle
from test_idempotency import CountingRunner


def test_budget_interrupts_uncooperative_runner():
    from backend.app.deadlines import DeadlineRunner
    from backend.app.tasks import AnalysisFailure
    started = time.monotonic()
    with pytest.raises(AnalysisFailure) as error:
        DeadlineRunner(CountingRunner(delay=10)).analyze(type('Job', (), {'job_id': 'unused'})(), deadline_monotonic=started+.1)
    assert error.value.reason == 'deadline_exceeded'
    assert time.monotonic()-started < .8


def test_queue_and_decode_time_are_included_and_capacity_released(database, tmp_path):
    from backend.app.deadlines import DeadlineRunner
    from backend.app.tasks import TaskExecutor
    _, repo = database
    started = datetime.now(timezone.utc)-timedelta(seconds=239.8)
    job = repo.create(upload(tmp_path), now=started)
    monotonic = time.monotonic()
    TaskExecutor(repo, DeadlineRunner(CountingRunner(delay=10)), tmp_path / 'gpu.lock').execute(job.job_id)
    assert time.monotonic()-monotonic < 1
    stored = repo.get(job.job_id)
    assert stored.state == 'failed' and stored.reason == 'deadline_exceeded' and stored.result is None
    assert repo.create(upload(tmp_path), now=datetime.now(timezone.utc)).state == 'queued'


def test_late_uncooperative_return_never_becomes_done(database, tmp_path):
    from backend.app.tasks import TaskExecutor
    _, repo = database
    job = repo.create(upload(tmp_path), now=datetime.now(timezone.utc)-timedelta(seconds=239.9))
    TaskExecutor(repo, CountingRunner(delay=.2), tmp_path / 'gpu.lock').execute(job.job_id)
    assert repo.get(job.job_id).reason == 'deadline_exceeded'
    assert repo.get(job.job_id).result is None


def test_lock_wait_cannot_commit_a_result_after_deadline(database, tmp_path):
    _, repo = database
    now = datetime.now(timezone.utc)
    job = repo.create(upload(tmp_path), now=now, deadline_seconds=1)
    lease = repo.claim(job.job_id, 'worker', now=now)
    # Block the row after the caller timestamp was taken, beyond the deadline.
    with database[0].connect() as blocker:
        transaction = blocker.begin()
        blocker.execute(text('SELECT 1 FROM jobs WHERE job_id=:id FOR UPDATE'), {'id': job.job_id})
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(repo.finish, lease, bundle(job.job_id), now=now)
            time.sleep(1.1)
            transaction.rollback()
            assert pending.result(timeout=5) is False
    repo.expire(now=datetime.now(timezone.utc))
    assert repo.get(job.job_id).state == 'failed' and repo.get(job.job_id).result is None


def test_slow_result_insert_is_rolled_back_when_deadline_expires(database, tmp_path):
    _, repo = database
    now = datetime.now(timezone.utc)
    job = repo.create(upload(tmp_path), now=now, deadline_seconds=1)
    lease = repo.claim(job.job_id, 'worker', now=now)
    with database[0].begin() as connection:
        connection.execute(text("CREATE FUNCTION slow_result() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(1.1); RETURN NEW; END $$"))
        connection.execute(text('CREATE TRIGGER slow_result BEFORE INSERT ON results FOR EACH ROW EXECUTE FUNCTION slow_result()'))
    assert repo.finish(lease, bundle(job.job_id), now=now) is False
    assert repo.get(job.job_id).result is None
    repo.expire(now=datetime.now(timezone.utc))
    assert repo.get(job.job_id).reason == 'deadline_exceeded'
