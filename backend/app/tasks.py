"""Fenced execution with a shared host GPU slot, heartbeat and durable failures.

The service is local to one GPU host. All worker processes must use the same
runtime root/lock path. Keep the host lock until computation exits even if its
DB lease is lost: lease expiry alone must never overlap two GPU analyses.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import threading
import time
from uuid import uuid4

from billiard.exceptions import SoftTimeLimitExceeded
from contracts.python_ports import ModelNotReady, PersistenceUnavailable


class AnalysisFailure(RuntimeError):
    def __init__(self, reason):
        if reason not in {'insufficient_evidence', 'deadline_exceeded', 'decode_failed', 'inference_failed',
                          'evidence_failed', 'worker_lost', 'internal_error', 'release_invalid'}:
            raise ValueError('Unknown durable failure reason')
        self.reason = reason
        super().__init__(reason)


def utc_now():
    return datetime.now(timezone.utc)


@contextmanager
def gpu_slot(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('Shared absolute GPU lock path required')
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    held = False
    try:
        try:
            if os.name == 'nt':
                import msvcrt
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            held = True
        except OSError as error:
            import errno
            if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
        yield held
    finally:
        os.close(descriptor)


class TaskExecutor:
    def __init__(self, repository, runner, lock_path, *, lease_seconds=30, renew_seconds=5):
        if not 0 < renew_seconds < lease_seconds <= 60:
            raise ValueError('Heartbeat must be shorter than the bounded lease')
        self.repository, self.runner, self.lock_path = repository, runner, Path(lock_path)
        self.lease_seconds, self.renew_seconds = lease_seconds, renew_seconds

    def execute(self, job_id):
        repo = self.repository
        repo.expire(now=utc_now())
        with gpu_slot(self.lock_path) as held:
            if not held:
                return 'deferred'
            lease = repo.claim(job_id, str(uuid4()), now=utc_now(), lease_seconds=self.lease_seconds)
            if lease is None:
                return 'ignored'
            stop, lost = threading.Event(), threading.Event()
            def heartbeat():
                while not stop.wait(self.renew_seconds):
                    try:
                        if repo.renew(lease, now=utc_now(), lease_seconds=self.lease_seconds) is None:
                            lost.set()
                            return
                    except PersistenceUnavailable:
                        lost.set()
                        return
            thread = threading.Thread(target=heartbeat, name='fortress-lease', daemon=True)
            thread.start()
            reason, result = None, None
            try:
                job = repo.get(job_id)
                if job is None:
                    return 'ignored'
                remaining = (job.deadline_at-utc_now()).total_seconds()
                if remaining <= 0:
                    reason = 'deadline_exceeded'
                else:
                    result = self.runner.analyze(job, deadline_monotonic=time.monotonic()+remaining)
            except AnalysisFailure as error:
                reason = error.reason
            except SoftTimeLimitExceeded:
                reason = 'deadline_exceeded'
            except ModelNotReady:
                reason = 'release_invalid'
            except PersistenceUnavailable:
                raise
            except Exception:
                # No raw third-party exceptions, SQL parameters, paths or media logs.
                reason = 'internal_error'
            finally:
                stop.set()
                thread.join(timeout=4)
            if lost.is_set():
                repo.expire(now=utc_now())
                return 'lost'
            repo.expire(now=utc_now())
            if reason:
                return 'failed' if repo.fail(lease, reason, now=utc_now()) else 'ignored'
            try:
                return 'done' if repo.finish(lease, result, now=utc_now()) else 'ignored'
            except (ValueError, TypeError, AttributeError):
                return 'failed' if repo.fail(lease, 'internal_error', now=utc_now()) else 'ignored'


def register_tasks(app, executor_factory):
    # This factory closes over one runtime/profile. Celery's default shared
    # registration would install it into future apps with another runtime.
    @app.task(name='fortress.analyze', bind=True, ignore_result=True, max_retries=120, shared=False, lazy=False)
    def analyze(self, job_id):
        # Set before loading any ML adapter in the factory.
        for name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
            os.environ[name] = '2'
        try:
            outcome = executor_factory().execute(job_id)
        except PersistenceUnavailable:
            raise self.retry(countdown=2, exc=None)
        if outcome in ('deferred', 'lost'):
            raise self.retry(countdown=2, exc=None)
        return outcome
    return analyze
