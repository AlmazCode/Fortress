"""A4 real transport delivery and concurrent fenced executor checks."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import threading
import time

import pytest
from celery.contrib.testing.worker import start_worker
from sqlalchemy import select, func

from test_persistence import database, upload, bundle
from test_outbox import redis_runtime


class CountingRunner:
    def __init__(self, *, delay=.2, error=None):
        self.calls, self.delay, self.error = 0, delay, error
        self.started = threading.Event()

    def analyze(self, job, *, deadline_monotonic):
        self.calls += 1
        self.started.set()
        time.sleep(self.delay)
        if self.error:
            raise self.error
        return bundle(job.job_id)


def test_parallel_workers_and_duplicate_delivery_produce_one_result(database, tmp_path):
    from backend.app.tasks import TaskExecutor
    from backend.app.models import Result
    _, repo = database
    job = repo.create(upload(tmp_path), now=datetime.now(timezone.utc))
    runner = CountingRunner()
    executor = TaskExecutor(repo, runner, tmp_path / 'gpu.lock')
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: executor.execute(job.job_id), range(8)))
    assert runner.calls == 1 and outcomes.count('done') == 1
    assert executor.execute(job.job_id) == 'ignored'
    with database[0].connect() as connection:
        assert connection.scalar(select(func.count()).select_from(Result)) == 1


def test_real_celery_redis_duplicate_delivery(database, redis_runtime, tmp_path):
    from backend.app.celery_app import create_celery
    from backend.app.outbox import CeleryPublisher, OutboxDispatcher
    from backend.app.tasks import TaskExecutor, register_tasks
    _, repo = database
    runner = CountingRunner(delay=.05)
    app = create_celery(redis_runtime.url)
    register_tasks(app, lambda: TaskExecutor(repo, runner, tmp_path / 'gpu.lock'))
    job = repo.create(upload(tmp_path), now=datetime.now(timezone.utc))
    publisher = CeleryPublisher(app)
    publisher.publish(job.job_id, job.deadline_at, now=datetime.now(timezone.utc))
    OutboxDispatcher(repo, publisher).tick()
    with start_worker(app, pool='solo', perform_ping_check=False, loglevel='CRITICAL', shutdown_timeout=5):
        until = time.monotonic()+5
        while time.monotonic() < until and repo.get(job.job_id).state != 'done':
            time.sleep(.03)
        assert repo.get(job.job_id).state == 'done'
        time.sleep(.1)
    assert runner.calls == 1
    assert app.conf.worker_concurrency == 1 and app.conf.worker_prefetch_multiplier == 1
    assert app.conf.task_acks_late and app.conf.task_reject_on_worker_lost
    app.close()


def test_renewal_keeps_slow_execution_single_and_failure_is_durable(database, tmp_path):
    from backend.app.tasks import TaskExecutor, AnalysisFailure
    _, repo = database
    job = repo.create(upload(tmp_path), now=datetime.now(timezone.utc))
    runner = CountingRunner(delay=1.3, error=AnalysisFailure('insufficient_evidence'))
    executor = TaskExecutor(repo, runner, tmp_path / 'gpu.lock', lease_seconds=1, renew_seconds=.2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(executor.execute, job.job_id)
        assert runner.started.wait(2)
        time.sleep(1.05)
        assert executor.execute(job.job_id) == 'deferred'
        assert running.result(timeout=3) == 'failed'
    assert runner.calls == 1
    assert repo.get(job.job_id).reason == 'insufficient_evidence'
    assert repo.create(upload(tmp_path), now=datetime.now(timezone.utc)).state == 'queued'


def test_expired_owner_is_replaced_and_stale_finish_rejected(database, tmp_path):
    from backend.app.tasks import TaskExecutor
    _, repo = database
    now = datetime.now(timezone.utc)
    job = repo.create(upload(tmp_path), now=now)
    stale = repo.claim(job.job_id, 'dead-worker', now=now-timedelta(seconds=2), lease_seconds=1)
    runner = CountingRunner(delay=0)
    assert TaskExecutor(repo, runner, tmp_path / 'gpu.lock').execute(job.job_id) == 'done'
    assert not repo.finish(stale, bundle(job.job_id), now=datetime.now(timezone.utc))
    assert runner.calls == 1


def test_separate_celery_apps_keep_their_own_executor_factory():
    from backend.app.celery_app import create_celery
    from backend.app.tasks import register_tasks
    apps = []
    try:
        for index in range(5):
            app = create_celery('redis://127.0.0.1:1/0')
            apps.append(app)
            class Executor:
                def __init__(self, identity): self.identity = identity
                def execute(self, job_id): return self.identity
            register_tasks(app, lambda identity=index: Executor(identity))
            app.finalize()
            assert app.tasks['fortress.analyze'].run('unused-job') == index
    finally:
        for app in apps: app.close()
