"""Monotonic compute budget, including elapsed upload/queue time.

The production prefork task executes on its process main thread, where SIGALRM
can interrupt a Python runner that ignores the deadline. Celery additionally
kills the task at its hard limit. Threaded harnesses retain post-return checks;
that mode is not the production hard-timeout mechanism.
"""
from contextlib import contextmanager
import signal
import threading
import time

from .tasks import AnalysisFailure


class DeadlineExceeded(TimeoutError):
    pass


@contextmanager
def deadline_guard(deadline_monotonic):
    remaining = deadline_monotonic-time.monotonic()
    if remaining <= 0:
        raise DeadlineExceeded
    main = threading.current_thread() is threading.main_thread()
    if not main:
        yield
        if time.monotonic() >= deadline_monotonic:
            raise DeadlineExceeded
        return
    def expired(signum, frame):
        raise DeadlineExceeded
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    signal.signal(signal.SIGALRM, expired)
    # Never postpone an already-active outer deadline.
    timer = min(remaining, previous_timer[0]) if previous_timer[0] else remaining
    signal.setitimer(signal.ITIMER_REAL, timer)
    try:
        yield
        if time.monotonic() >= deadline_monotonic:
            raise DeadlineExceeded
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0]:
            signal.setitimer(signal.ITIMER_REAL, max(.000001, previous_timer[0]-(time.monotonic()-started)), previous_timer[1])


class DeadlineRunner:
    def __init__(self, runner):
        self.runner = runner

    def analyze(self, job, *, deadline_monotonic):
        try:
            with deadline_guard(deadline_monotonic):
                return self.runner.analyze(job, deadline_monotonic=deadline_monotonic)
        except DeadlineExceeded:
            raise AnalysisFailure('deadline_exceeded') from None
