"""Dedicated prefork worker kill/restart and result-commit failure injection."""
from datetime import datetime, timezone
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest
from sqlalchemy import text

from test_persistence import database, upload, bundle
from test_outbox import redis_runtime
from test_idempotency import CountingRunner


def wait_until(check, timeout=10):
    until = time.monotonic()+timeout
    while time.monotonic() < until:
        if check(): return
        time.sleep(.03)
    raise AssertionError('Dedicated worker did not reach expected state')


def stop_worker(process):
    if process and process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def test_kill_restart_prefork_worker_recovers_same_job(database, redis_runtime, tmp_path):
    from backend.app.celery_app import create_celery
    from backend.app.outbox import OutboxDispatcher, CeleryPublisher
    _, repo = database
    job = repo.create(upload(tmp_path), now=datetime.now(timezone.utc))
    app = create_celery(redis_runtime.url)
    dispatcher = OutboxDispatcher(repo, CeleryPublisher(app), republish_seconds=.1)
    env = os.environ.copy()
    env.update(FORTRESS_TEST_WORKER_DATABASE=database[0].url.render_as_string(hide_password=False),
               FORTRESS_TEST_WORKER_BROKER=redis_runtime.url, FORTRESS_TEST_WORKER_ROOT=str(tmp_path),
               PYTHONPATH=str(Path(__file__).resolve().parents[2]))
    def start():
        return subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--test-worker'], env=env,
                                start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    worker = start()
    try:
        dispatcher.tick()
        marker = tmp_path / 'calls.txt'
        wait_until(lambda: marker.exists())
        assert repo.get(job.job_id).state == 'running'
        stop_worker(worker)
        assert repo.get(job.job_id).result is None
        time.sleep(2.1)  # Explicit test lease, not the production 30-second lease.
        worker = start()
        dispatcher.tick()
        wait_until(lambda: repo.get(job.job_id).state == 'done')
        assert len(marker.read_text().splitlines()) == 2
        with database[0].connect() as connection:
            assert connection.scalar(text('SELECT count(*) FROM results')) == 1
    finally:
        stop_worker(worker)
        app.close()


def test_result_commit_rollback_then_retry_has_one_terminal_result(database, tmp_path):
    from backend.app.tasks import TaskExecutor
    from contracts.python_ports import PersistenceUnavailable
    engine, repo = database
    job = repo.create(upload(tmp_path), now=datetime.now(timezone.utc))
    runner = CountingRunner(delay=0)
    executor = TaskExecutor(repo, runner, tmp_path / 'gpu.lock', lease_seconds=1, renew_seconds=.2)
    with engine.begin() as connection:
        connection.execute(text("CREATE FUNCTION refuse_result() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected result failure'; END $$"))
        connection.execute(text('CREATE TRIGGER refuse_result BEFORE INSERT ON results FOR EACH ROW EXECUTE FUNCTION refuse_result()'))
    with pytest.raises(PersistenceUnavailable):
        executor.execute(job.job_id)
    assert repo.get(job.job_id).state == 'running' and repo.get(job.job_id).result is None
    with engine.begin() as connection:
        connection.execute(text('DROP TRIGGER refuse_result ON results'))
    time.sleep(1.05)
    assert executor.execute(job.job_id) == 'done'
    assert executor.execute(job.job_id) == 'ignored'
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM results')) == 1


def worker_main():
    # This entry point exists only in tests, with an explicit test flag and DSN.
    from backend.app.celery_app import create_celery
    from backend.app.db import create_db_engine
    from backend.app.jobs import JobRepository
    from backend.app.tasks import register_tasks, TaskExecutor
    root = Path(os.environ['FORTRESS_TEST_WORKER_ROOT'])
    class RestartRunner:
        def analyze(self, job, *, deadline_monotonic):
            marker = root / 'calls.txt'
            first = not marker.exists()
            with marker.open('a') as target:
                target.write(str(os.getpid())+'\n')
                target.flush()
                os.fsync(target.fileno())
            if first:
                time.sleep(120)
            return bundle(job.job_id)
    app = create_celery(os.environ['FORTRESS_TEST_WORKER_BROKER'])
    def factory():
        return TaskExecutor(JobRepository(create_db_engine(os.environ['FORTRESS_TEST_WORKER_DATABASE'])),
                            RestartRunner(), root / 'gpu.lock', lease_seconds=2, renew_seconds=.3)
    register_tasks(app, factory)
    app.Worker(pool='prefork', concurrency=1, loglevel='CRITICAL', without_heartbeat=True,
               without_gossip=True, without_mingle=True).start()


if __name__ == '__main__' and sys.argv[1:] == ['--test-worker']:
    worker_main()
