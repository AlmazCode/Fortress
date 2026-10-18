"""Power requests must follow the lifetime of the worker, including failures."""
import threading

import pytest

from backend.local import power, runtime


def test_request_restores_prior_thread_state_after_failure(monkeypatch):
    calls = []
    prior = power.ES_CONTINUOUS | 0x2  # Preserve an existing display request.
    def setter(flags):
        calls.append((threading.get_ident(), flags))
        return prior
    monkeypatch.setattr(power, '_execution_state_setter', lambda: setter)
    inhibitor = power.IdleSleepInhibitor()
    with pytest.raises(RuntimeError), inhibitor:
        assert inhibitor.active
        raise RuntimeError('Worker failed')
    assert not inhibitor.active
    assert calls == [(threading.get_ident(), 0x80000001), (threading.get_ident(), prior)]


@pytest.mark.parametrize('setter', [None, lambda flags: 0])
def test_unsupported_or_rejected_request_is_not_reported_as_active(monkeypatch, setter):
    monkeypatch.setattr(power, '_execution_state_setter', lambda: setter)
    with power.IdleSleepInhibitor() as inhibitor:
        assert not inhibitor.active
    assert not inhibitor.active


def test_worker_holds_request_while_idle_and_releases_on_stop(tmp_path, monkeypatch):
    calls = []
    def setter(flags):
        calls.append(flags)
        return power.ES_CONTINUOUS
    monkeypatch.setattr(power, '_execution_state_setter', lambda: setter)
    stop = threading.Event()
    inhibitor = power.IdleSleepInhibitor()
    class Repository:
        def expire(self, *, now):
            assert inhibitor.active
            stop.set()
        def pending(self, *, now):
            return []
    runtime.run_worker(Repository(), {'runtime_root': str(tmp_path)}, stop, inhibitor)
    assert not inhibitor.active
    assert calls == [0x80000001, 0x80000000]
