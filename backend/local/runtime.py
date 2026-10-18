"""Native worker: durable queue polling, fenced commit and killable model process."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from contracts.python_ports import AnalysisBundle, PersistenceUnavailable
from backend.app.tasks import AnalysisFailure, TaskExecutor
from .process_guard import ChildGroup
from .power import IdleSleepInhibitor


class ProcessRunner:
    def __init__(self, config, stop):
        self.config, self.stop = config, stop

    def analyze(self, job, *, deadline_monotonic):
        directory = Path(self.config['runtime_root'])/'requests'
        directory.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=directory, suffix='.json')
        path = Path(name)
        process = None
        errors = None
        group = None
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                # API key is never passed to the model subprocess.
                subset = {k: self.config[k] for k in ('runtime_root', 'bundle_root', 'device')}
                json.dump({'config': subset, 'job_id': job.job_id}, stream)
            group = ChildGroup()
            logs = Path(self.config['runtime_root'])/'logs'
            logs.mkdir(exist_ok=True)
            errors = (logs/(job.job_id+'.log')).open('wb')
            process = subprocess.Popen([sys.executable, '-B', '-m', 'backend.local.inference', '--request', str(path)],
                cwd=Path(__file__).resolve().parents[2], stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=errors,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            group.attach(process)
            while True:
                if self.stop.is_set():
                    raise AnalysisFailure('worker_lost')
                remaining = deadline_monotonic-time.monotonic()
                if remaining <= 0:
                    raise AnalysisFailure('deadline_exceeded')
                try:
                    output, _ = process.communicate(timeout=min(.25, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode or len(output) > 32*1024*1024:
                raise AnalysisFailure('inference_failed')
            try:
                result = json.loads(output)
                if isinstance(result, dict) and set(result) == {'failure_reason'}:
                    raise AnalysisFailure(result['failure_reason'])
                return AnalysisBundle(**result)
            except (ValueError, TypeError):
                raise AnalysisFailure('inference_failed') from None
        finally:
            if group is not None:
                group.close()
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.communicate()
            if errors is not None:
                errors.close()
            path.unlink(missing_ok=True)


def run_worker(repo, config, stop, sleep_inhibitor=None):
    inhibitor = sleep_inhibitor if sleep_inhibitor is not None else IdleSleepInhibitor()
    with inhibitor:
        _poll_jobs(repo, config, stop)


def _poll_jobs(repo, config, stop):
    executor = TaskExecutor(repo, ProcessRunner(config, stop), Path(config['runtime_root'])/'gpu.lock')
    while not stop.is_set():
        try:
            now = datetime.now(timezone.utc)
            repo.expire(now=now)
            for job_id in repo.pending(now=now):
                executor.execute(job_id)
        except PersistenceUnavailable:
            pass
        stop.wait(.25)
