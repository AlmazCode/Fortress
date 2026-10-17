"""A1 checks against a disposable, real PostgreSQL database."""
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest
import psycopg
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime.now(timezone.utc)


@pytest.fixture
def database():
    admin_url = os.environ.get('FORTRESS_TEST_DATABASE_URL')
    if not admin_url:
        pytest.skip('Real PostgreSQL required: set FORTRESS_TEST_DATABASE_URL')
    from backend.app.db import create_db_engine, migrate
    from backend.app.jobs import JobRepository
    url = make_url(admin_url).set(drivername='postgresql')
    name = 'fortress_test_a1_' + uuid4().hex
    with psycopg.connect(url.render_as_string(hide_password=False), autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    engine = create_db_engine(url.set(drivername='postgresql+psycopg', database=name))
    migrate(engine)
    try:
        yield engine, JobRepository(engine)
    finally:
        engine.dispose()
        with psycopg.connect(url.render_as_string(hide_password=False), autocommit=True) as admin:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


def upload(tmp_path):
    from contracts.python_ports import AcceptedUpload, VideoInfo
    path = tmp_path / 'already-validated.mp4'
    path.write_bytes(b'validated-upload-placeholder-not-used-for-decoding')
    return AcceptedUpload(path.resolve(), 'a' * 64, path.stat().st_size,
                          VideoInfo(1, 16, 16, 2, 0, 90, 1, 90, False))


def bundle(job_id):
    from contracts.python_ports import AnalysisBundle
    cases = json.loads((ROOT / 'contracts/fixtures.json').read_text())['cases']
    diagnostics = copy.deepcopy(next(x['payload'] for x in cases if x['name'] == 'ui_diagnostics'))
    public = {'job_id': job_id, 'status': 'done', 'verdict': 'no_violation', 'violations': []}
    diagnostics.update(job_id=job_id, public=public, stage='done', coverage='partial', timeline=None)
    return AnalysisBundle(public, diagnostics)


def test_migration_idempotence_and_durable_create(database, tmp_path):
    from backend.app.db import migrate
    from backend.app.jobs import JobRepository, public_job
    engine, repo = database
    job = repo.create(upload(tmp_path), now=NOW)
    migrate(engine)
    engine.dispose()
    other = JobRepository(engine)
    stored = other.get(job.job_id)
    assert stored.upload == job.upload and stored.accepted_at == NOW
    assert public_job(stored) == {'job_id': job.job_id, 'status': 'processing'}
    assert [x.job_id for x in other.pending_outbox()] == [job.job_id]
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM alembic_version')) == 1


def test_restart_preserves_job_result_and_outbox(database, tmp_path):
    from backend.app.jobs import JobRepository
    engine, repo = database
    control = os.environ.get('FORTRESS_TEST_PG_CTL')
    data = os.environ.get('FORTRESS_TEST_PGDATA')
    log = os.environ.get('FORTRESS_TEST_PGLOG')
    if not all([control, data, log]):
        pytest.skip('Dedicated test PostgreSQL control paths required for restart check')
    job = repo.create(upload(tmp_path), now=NOW)
    lease = repo.claim(job.job_id, 'worker', now=NOW)
    assert repo.finish(lease, bundle(job.job_id), now=NOW + timedelta(seconds=1))
    engine.dispose()
    subprocess.run([control, '-D', data, '-l', log, '-m', 'fast', 'restart', '-w'],
                   check=True, timeout=30, capture_output=True)
    restored = JobRepository(engine).get(job.job_id)
    assert restored.state == 'done' and restored.result == bundle(job.job_id).public
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM outbox')) == 1


def test_concurrent_intake_has_one_atomic_capacity_slot(database, tmp_path):
    from contracts.python_ports import CapacityExceeded
    _, repo = database
    original = upload(tmp_path)
    def accept(_):
        try:
            return repo.create(original, now=NOW).job_id
        except CapacityExceeded:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(accept, range(8)))
    assert sum(x is not None for x in results) == 1
    assert len(repo.pending_outbox()) == 1


def test_concurrent_claim_and_renewal_are_fenced(database, tmp_path):
    _, repo = database
    job = repo.create(upload(tmp_path), now=NOW)
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda n: repo.claim(job.job_id, str(n), now=NOW), range(8)))
    valid = [x for x in claims if x is not None]
    assert len(valid) == 1
    first = valid[0]
    renewed = repo.renew(first, now=NOW + timedelta(seconds=10))
    assert renewed.token == first.token and renewed.expires_at > first.expires_at
    assert repo.claim(job.job_id, 'other', now=NOW + timedelta(seconds=31)) is None
    second = repo.claim(job.job_id, 'replacement', now=NOW + timedelta(seconds=41))
    assert second.token > first.token
    assert not repo.finish(first, bundle(job.job_id), now=NOW + timedelta(seconds=42))
    assert not repo.fail(first, 'worker_lost', now=NOW + timedelta(seconds=42))
    assert repo.renew(first, now=NOW + timedelta(seconds=42)) is None
    assert repo.finish(second, bundle(job.job_id), now=NOW + timedelta(seconds=42))
    assert not repo.finish(second, bundle(job.job_id), now=NOW + timedelta(seconds=43))


def test_bad_result_never_becomes_visible_and_terminal_state_releases_capacity(database, tmp_path):
    from backend.app.jobs import public_job
    _, repo = database
    job = repo.create(upload(tmp_path), now=NOW)
    lease = repo.claim(job.job_id, 'worker', now=NOW)
    assert public_job(repo.get(job.job_id))['status'] == 'processing'
    invalid = bundle(job.job_id)
    invalid.public['verdict'] = 'violation'
    with pytest.raises(ValueError):
        repo.finish(lease, invalid, now=NOW + timedelta(seconds=1))
    assert repo.get(job.job_id).result is None
    assert repo.fail(lease, 'inference_failed', now=NOW + timedelta(seconds=2))
    assert public_job(repo.get(job.job_id)) == {'job_id': job.job_id, 'status': 'failed', 'reason': 'inference_failed'}
    assert repo.create(upload(tmp_path), now=NOW + timedelta(seconds=3)).state == 'queued'


def test_result_must_match_job_and_diagnostics(database, tmp_path):
    _, repo = database
    job = repo.create(upload(tmp_path), now=NOW)
    lease = repo.claim(job.job_id, 'worker', now=NOW)
    with pytest.raises(ValueError):
        repo.finish(lease, bundle(str(uuid4())), now=NOW)
    value = bundle(job.job_id)
    value.diagnostics['public'] = {'job_id': job.job_id, 'status': 'processing'}
    with pytest.raises(ValueError):
        repo.finish(lease, value, now=NOW)
    assert repo.get(job.job_id).state == 'running'


def test_database_rollback_cannot_leave_accepted_job(database, tmp_path):
    from contracts.python_ports import PersistenceUnavailable
    engine, repo = database
    with engine.begin() as connection:
        connection.execute(text("CREATE FUNCTION reject_outbox() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected test rollback'; END $$"))
        connection.execute(text('CREATE TRIGGER reject_outbox BEFORE INSERT ON outbox FOR EACH ROW EXECUTE FUNCTION reject_outbox()'))
    with pytest.raises(PersistenceUnavailable):
        repo.create(upload(tmp_path), now=NOW)
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM jobs')) == 0
        assert connection.scalar(text('SELECT count(*) FROM outbox')) == 0


def test_finish_transaction_rolls_back_state_if_result_write_fails(database, tmp_path):
    from contracts.python_ports import PersistenceUnavailable
    engine, repo = database
    job = repo.create(upload(tmp_path), now=NOW)
    lease = repo.claim(job.job_id, 'worker', now=NOW)
    with engine.begin() as connection:
        connection.execute(text("CREATE FUNCTION reject_result() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected test rollback'; END $$"))
        connection.execute(text('CREATE TRIGGER reject_result BEFORE INSERT ON results FOR EACH ROW EXECUTE FUNCTION reject_result()'))
    with pytest.raises(PersistenceUnavailable):
        repo.finish(lease, bundle(job.job_id), now=NOW)
    stored = repo.get(job.job_id)
    assert stored.state == 'running' and stored.result is None


def test_database_outage_has_no_success_response(database, tmp_path):
    from backend.app.db import create_db_engine
    from backend.app.jobs import JobRepository
    from contracts.python_ports import PersistenceUnavailable
    engine, _ = database
    offline = create_db_engine(engine.url.update_query_dict({'host': '/definitely/missing/fortress/socket'}))
    try:
        with pytest.raises(PersistenceUnavailable):
            JobRepository(offline).create(upload(tmp_path), now=NOW)
    finally:
        offline.dispose()


def test_deadline_and_outbox_idempotence(database, tmp_path):
    from backend.app.jobs import public_job
    _, repo = database
    job = repo.create(upload(tmp_path), now=NOW, deadline_seconds=20)
    lease = repo.claim(job.job_id, 'worker', now=NOW, lease_seconds=30)
    assert lease.expires_at == job.deadline_at
    outbox = repo.pending_outbox()[0]
    repo.mark_published(outbox.id, now=NOW)
    repo.mark_published(outbox.id, now=NOW + timedelta(seconds=1))
    assert repo.pending_outbox() == []
    assert not repo.finish(lease, bundle(job.job_id), now=job.deadline_at)
    assert repo.expire(now=job.deadline_at) == [job.job_id]
    assert repo.expire(now=job.deadline_at) == []
    assert public_job(repo.get(job.job_id))['reason'] == 'deadline_exceeded'
