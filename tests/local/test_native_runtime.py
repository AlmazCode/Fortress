"""Real SQLite, OS locks, native pipe decode and protected HTTP, without a model fixture fallback."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import io
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

from contracts.python_ports import AcceptedUpload, CapacityExceeded, ContractError, VideoInfo, validate_contract
from backend.app.api_upload import UploadService
from backend.app.schemas import MissingRelease
from backend.app.storage import IntakeError
from backend.app.tasks import AnalysisFailure, gpu_slot
from backend.local.app import PrototypeUpload, create_app
from backend.local.repository import LocalRepository
from backend.local.runtime import ProcessRunner


def upload(tmp_path):
    path = tmp_path/'native-upload.video'
    path.write_bytes(b'queue-test-only-not-decoded')
    return AcceptedUpload(path, 'a'*64, path.stat().st_size, VideoInfo(1,16,16,2,0,0,1,90,False))


def test_native_queue_admission_reopen_reclaim_and_stale_fence(tmp_path):
    path = tmp_path/'private'/'jobs.sqlite3'
    repo = LocalRepository(path)
    now = datetime.now(timezone.utc)
    original = upload(tmp_path)
    def create(_):
        try:
            return repo.create(original, now=now)
        except CapacityExceeded:
            return None
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(create, range(5)))
    assert sum(value is not None for value in results) == 1
    job = next(value for value in results if value)
    reopened = LocalRepository(path)
    assert reopened.get(job.job_id) == job
    first = repo.claim(job.job_id, 'first', now=now, lease_seconds=1)
    assert repo.claim(job.job_id, 'other', now=now) is None
    second = reopened.claim(job.job_id, 'second', now=now+timedelta(seconds=2))
    assert second.token == first.token+1
    assert not repo.fail(first, 'worker_lost', now=now+timedelta(seconds=2))
    assert repo.fail(second, 'worker_lost', now=now+timedelta(seconds=2))
    assert reopened.get(job.job_id).reason == 'worker_lost'
    assert repo.claim(job.job_id, 'duplicate', now=now+timedelta(seconds=3)) is None
    next_job = repo.create(original, now=now)
    assert repo.expire(now=now+timedelta(seconds=241)) == [next_job.job_id]
    assert repo.get(next_job.job_id).reason == 'deadline_exceeded'


def test_os_gpu_lock_excludes_second_process_and_releases(tmp_path):
    lock = tmp_path/'gpu.lock'
    code = 'from backend.app.tasks import gpu_slot; import sys\nwith gpu_slot(sys.argv[1]) as held: print(int(held))'
    with gpu_slot(lock) as held:
        assert held
        result = subprocess.run([sys.executable, '-B', '-c', code, str(lock)], capture_output=True, text=True, check=True)
        assert result.stdout.strip() == '0'
    result = subprocess.run([sys.executable, '-B', '-c', code, str(lock)], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == '1'


def prototype():
    return {'schema_version':'1.0','status':'prototype','reason':'experimental_model','release_version':'prototype-test',
            'trained':True,'validated':False,'test_only':False,'limitations':['Not production validation.']}


def test_prototype_cannot_open_production_gate():
    class Release:
        def readiness(self): return prototype()
    validate_contract('diagnostics', prototype())
    with pytest.raises(IntakeError):
        UploadService(None,None,None,Release()).check_ready()
    PrototypeUpload(None,None,None,Release()).check_ready()
    invalid = {**prototype(), 'validated': True}
    with pytest.raises(ContractError): validate_contract('diagnostics', invalid)
    invalid = {**prototype(), 'trained': False}
    with pytest.raises(ContractError): validate_contract('diagnostics', invalid)


def test_same_origin_http_auth_not_ready_and_private_data(tmp_path):
    frontend = tmp_path/'public'
    frontend.mkdir()
    (frontend/'index.html').write_text('<html>Fortress test build</html>')
    config = {'runtime_root': str(tmp_path/'runtime'), 'api_key':'test-key-for-native-http-only'}
    app = create_app(config, frontend, release=MissingRelease(), start_worker=False)
    client = TestClient(app)
    assert client.get('/').status_code == 200
    assert client.get('/healthz').json()['production_ready'] is False
    assert client.get('/api/ui/v1/model').status_code == 401
    headers = {'X-API-Key':config['api_key']}
    response = client.get('/api/ui/v1/model', headers=headers)
    assert response.status_code == 200 and response.json()['status'] == 'not_ready'
    assert response.headers['cache-control'] == 'private, no-store'
    assert client.post('/api/v1/analyze', headers=headers, files={'file':('x.mov',b'not-video')}).status_code == 503
    assert client.get('/api/ui/v1/jobs/not-a-uuid/media',headers=headers).status_code == 404
    assert client.get('/../jobs.sqlite3').status_code == 404
    assert client.post('/api/local/v1/shutdown').status_code == 401


def test_windows_pipe_reader_bounds_output_and_deadline():
    from backend.app.video import VideoValidator
    process = subprocess.Popen([sys.executable,'-c','print("x"*200000)'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with pytest.raises(IntakeError):
        VideoValidator._read_windows(process,bytearray(),bytearray(),time.monotonic()+5,1024)
    assert process.poll() is not None
    process.stdout.close(); process.stderr.close()
    process = subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with pytest.raises(IntakeError):
        VideoValidator._read_windows(process,bytearray(),bytearray(),time.monotonic()+.1,1024)
    assert process.poll() is not None
    process.stdout.close(); process.stderr.close()


def test_actual_child_process_timeout_is_killed_and_request_removed(tmp_path,monkeypatch):
    from backend.local import runtime
    real_popen = subprocess.Popen
    children = []
    def sleeper(arguments, **kwargs):
        child = real_popen([sys.executable,'-c','import time; time.sleep(30)'], **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(runtime.subprocess,'Popen',sleeper)
    config = {'runtime_root':str(tmp_path/'runtime'),'bundle_root':str(tmp_path/'unused'),'device':'cpu'}
    repo = LocalRepository(tmp_path/'runtime'/'jobs.sqlite3')
    job = repo.create(upload(tmp_path),now=datetime.now(timezone.utc))
    start = time.monotonic()
    with pytest.raises(AnalysisFailure) as caught:
        ProcessRunner(config,threading.Event()).analyze(job,deadline_monotonic=start+.2)
    assert getattr(caught.value,'reason',None) == 'deadline_exceeded'
    assert time.monotonic()-start < 5
    assert children[0].poll() is not None
    assert not list((tmp_path/'runtime'/'requests').glob('*.json'))


@pytest.mark.skipif(os.name!='nt',reason='Windows parent-death Job Object test')
def test_windows_parent_crash_kills_actual_child():
    import ctypes as c
    from ctypes import wintypes as w
    api=c.WinDLL('kernel32',use_last_error=True)
    api.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD]; api.OpenProcess.restype=w.HANDLE
    api.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD]; api.WaitForSingleObject.restype=w.DWORD
    api.CloseHandle.argtypes=[w.HANDLE]
    code = ('from backend.local.process_guard import ChildGroup; import subprocess,sys,time\n'
            'g=ChildGroup(); p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); '
            'g.attach(p); print(p.pid,flush=True); time.sleep(30)')
    parent=subprocess.Popen([sys.executable,'-B','-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    handle=None
    try:
        pid=int(parent.stdout.readline())
        handle=api.OpenProcess(0x100000,False,pid)
        assert handle
        parent.kill();parent.wait(timeout=5)
        assert api.WaitForSingleObject(handle,5000)==0
    finally:
        if parent.poll() is None: parent.kill()
        parent.communicate()
        if handle:api.CloseHandle(handle)
