"""Native single-host queue: SQLite WAL, one unfinished job, leases and fencing."""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4

from contracts.python_ports import (AcceptedUpload, CapacityExceeded, JobLease, JobRecord,
                                   PersistenceUnavailable, VideoInfo, validate_contract)


def _time(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('UTC-aware clock required')
    return value.timestamp()


def _record(row):
    if row is None:
        return None
    upload = json.loads(row['upload'])
    return JobRecord(row['job_id'], row['state'], datetime.fromtimestamp(row['accepted'], timezone.utc),
                     datetime.fromtimestamp(row['deadline'], timezone.utc),
                     AcceptedUpload(Path(upload['path']), upload['sha256'], upload['size_bytes'], VideoInfo(**upload['video'])),
                     json.loads(row['result']) if row['result'] else None,
                     json.loads(row['diagnostics']) if row['diagnostics'] else None, row['reason'])


class LocalRepository:
    def __init__(self, path):
        self.path = Path(path).resolve()
        if any((p/'.git').exists() for p in [self.path.parent, *self.path.parents]):
            raise ValueError('Private queue must be outside Git')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as con:
            con.execute('PRAGMA journal_mode=WAL')
            con.executescript('''CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY, state TEXT NOT NULL, accepted REAL NOT NULL, deadline REAL NOT NULL,
                upload TEXT NOT NULL, result TEXT, diagnostics TEXT, reason TEXT,
                owner TEXT, token INTEGER NOT NULL DEFAULT 0, lease_until REAL);
                CREATE UNIQUE INDEX IF NOT EXISTS one_unfinished ON jobs((1))
                WHERE state IN ('queued','running');''')

    @contextmanager
    def connection(self):
        con = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            con.execute('PRAGMA synchronous=FULL')
            yield con
        except sqlite3.Error:
            raise PersistenceUnavailable('Local queue unavailable') from None
        finally:
            con.close()

    def create(self, upload, *, now, deadline_seconds=240):
        if not 0 < deadline_seconds <= 240:
            raise ValueError('Bounded deadline required')
        stamp = _time(now)
        data = asdict(upload)
        data['path'] = str(upload.path)
        identity = str(uuid4())
        with self.connection() as con:
            try:
                con.execute('INSERT INTO jobs(job_id,state,accepted,deadline,upload) VALUES(?,?,?,?,?)',
                            (identity, 'queued', stamp, stamp+deadline_seconds, json.dumps(data)))
            except sqlite3.IntegrityError:
                raise CapacityExceeded('One unfinished job already accepted') from None
        return self.get(identity)

    def get(self, job_id):
        try:
            job_id = str(UUID(job_id))
        except (ValueError, TypeError, AttributeError):
            return None
        with self.connection() as con:
            return _record(con.execute('SELECT * FROM jobs WHERE job_id=?', (job_id,)).fetchone())

    def claim(self, job_id, owner, *, now, lease_seconds=30):
        if not owner or not 0 < lease_seconds <= 60:
            raise ValueError('Bounded lease and owner required')
        stamp = _time(now)
        with self.connection() as con:
            row = con.execute('''UPDATE jobs SET state='running',owner=?,token=token+1,
                lease_until=min(deadline,?) WHERE job_id=? AND deadline>?
                AND (state='queued' OR (state='running' AND lease_until<=?)) RETURNING token,lease_until''',
                (owner, stamp+lease_seconds, job_id, stamp, stamp)).fetchone()
        return JobLease(job_id, owner, row['token'], datetime.fromtimestamp(row['lease_until'], timezone.utc)) if row else None

    def renew(self, lease, *, now, lease_seconds=30):
        stamp = _time(now)
        if not 0 < lease_seconds <= 60:
            raise ValueError('Bounded lease required')
        with self.connection() as con:
            row = con.execute('''UPDATE jobs SET lease_until=min(deadline,?) WHERE job_id=?
                AND state='running' AND owner=? AND token=? AND deadline>? AND lease_until>?
                RETURNING lease_until''', (stamp+lease_seconds, lease.job_id, lease.owner, lease.token, stamp, stamp)).fetchone()
        return JobLease(lease.job_id, lease.owner, lease.token, datetime.fromtimestamp(row['lease_until'], timezone.utc)) if row else None

    def _finish(self, lease, *, result=None, reason=None, now):
        # Acquire the write lock before checking fresh wall time; queued lock waits count.
        with self.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            try:
                stamp = max(_time(now), datetime.now(timezone.utc).timestamp())
                changed = con.execute('''UPDATE jobs SET state=?,result=?,diagnostics=?,reason=?
                    WHERE job_id=? AND state='running' AND owner=? AND token=? AND deadline>? AND lease_until>?''',
                    ('done' if result else 'failed', json.dumps(result.public) if result else None,
                     json.dumps(result.diagnostics) if result else None, reason,
                     lease.job_id, lease.owner, lease.token, stamp, stamp)).rowcount
                con.execute('COMMIT')
                return bool(changed)
            except BaseException:
                con.execute('ROLLBACK')
                raise

    def finish(self, lease, result, *, now):
        validate_contract('job', result.public)
        validate_contract('diagnostics', result.diagnostics)
        if result.public['job_id'] != lease.job_id or result.diagnostics['public'] != result.public:
            raise ValueError('Result identity mismatch')
        return self._finish(lease, result=result, now=now)

    def fail(self, lease, reason, *, now):
        from backend.app.tasks import AnalysisFailure
        AnalysisFailure(reason)
        return self._finish(lease, reason=reason, now=now)

    def expire(self, *, now):
        with self.connection() as con:
            rows = con.execute('''UPDATE jobs SET state='failed',reason='deadline_exceeded'
                WHERE state IN ('queued','running') AND deadline<=? RETURNING job_id''', (_time(now),)).fetchall()
        return [row['job_id'] for row in rows]

    def pending(self, *, now):
        with self.connection() as con:
            rows = con.execute('''SELECT job_id FROM jobs WHERE deadline>? AND
                (state='queued' OR (state='running' AND lease_until<=?)) ORDER BY accepted LIMIT 1''',
                (_time(now), _time(now))).fetchall()
        return [row['job_id'] for row in rows]
