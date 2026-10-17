"""Real Redis/Celery transport and PostgreSQL; no broker mocks."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import tempfile
import time

import pytest
import redis
from sqlalchemy import select

from test_persistence import database, upload


class RedisRuntime:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.socket = self.directory / 'redis.sock'
        self.url = f'redis+socket://{self.socket}?virtual_host=0'
        self.client = redis.Redis(unix_socket_path=str(self.socket), socket_timeout=1)
        self.process = None

    def start(self):
        self.process = subprocess.Popen(['redis-server', '--port', '0', '--unixsocket', str(self.socket),
            '--unixsocketperm', '700', '--dir', str(self.directory), '--save', '', '--appendonly', 'no',
            '--maxmemory', '32mb', '--maxmemory-policy', 'noeviction'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        until = time.monotonic()+5
        while time.monotonic() < until:
            try:
                if self.client.ping(): return
            except redis.RedisError:
                time.sleep(.02)
        raise RuntimeError('Dedicated Redis did not start')

    def stop(self):
        if self.process is not None:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process = None
        self.client.connection_pool.disconnect()


@pytest.fixture
def redis_runtime():
    with tempfile.TemporaryDirectory(prefix='fortress-redis-') as directory:
        runtime = RedisRuntime(directory)
        runtime.start()
        try:
            yield runtime
        finally:
            runtime.stop()


def test_db_commit_survives_broker_outage_and_republish(database, redis_runtime, tmp_path):
    from backend.app.celery_app import create_celery
    from backend.app.outbox import OutboxDispatcher, CeleryPublisher
    from backend.app.models import Outbox
    engine, repo = database
    app = create_celery(redis_runtime.url)
    publisher = CeleryPublisher(app)
    dispatch = OutboxDispatcher(repo, publisher, republish_seconds=.1)
    now = datetime.now(timezone.utc)
    job = repo.create(upload(tmp_path), now=now)
    redis_runtime.stop()
    assert dispatch.tick(now=now)['published'] == 0
    assert repo.get(job.job_id).state == 'queued'
    assert len(repo.pending_outbox()) == 1
    redis_runtime.start()
    assert dispatch.tick(now=now)['published'] == 1
    with engine.connect() as connection:
        assert connection.scalar(select(Outbox.published_at)) is not None
    # Redis may lose already acknowledged publication: PostgreSQL repairs queued work.
    redis_runtime.stop()
    redis_runtime.start()
    assert dispatch.tick(now=now+timedelta(seconds=1))['published'] == 1
    assert redis_runtime.client.llen('fortress') == 1
    app.close()


def test_publish_before_db_mark_is_duplicate_safe(database, redis_runtime, tmp_path):
    from backend.app.celery_app import create_celery
    from backend.app.outbox import OutboxDispatcher, CeleryPublisher
    app = create_celery(redis_runtime.url)
    _, repo = database
    now = datetime.now(timezone.utc)
    job = repo.create(upload(tmp_path), now=now)
    publisher = CeleryPublisher(app)
    publisher.publish(job.job_id, job.deadline_at, now=now)  # process died here, before durable mark
    assert repo.pending_outbox()
    assert OutboxDispatcher(repo, publisher).tick(now=now)['published'] == 1
    assert redis_runtime.client.llen('fortress') == 2
    app.close()


def test_expired_job_has_terminal_state_without_broker(database, tmp_path):
    from backend.app.outbox import OutboxDispatcher
    class NoPublication:
        def publish(self, *args, **kwargs):
            raise AssertionError('Expired jobs must not be published')
    _, repo = database
    now = datetime.now(timezone.utc)
    job = repo.create(upload(tmp_path), now=now, deadline_seconds=1)
    report = OutboxDispatcher(repo, NoPublication()).tick(now=now+timedelta(seconds=2))
    assert report['expired'] == 1 and repo.get(job.job_id).reason == 'deadline_exceeded'
