"""Durable jobs with atomic admission, leases, fencing and terminal writes."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from contracts.python_ports import (AcceptedUpload, AnalysisBundle, CapacityExceeded,
                                   JobLease, JobRecord, OutboxItem, PersistenceUnavailable,
                                   VideoInfo, validate_contract)
from .models import Job, Outbox, Result


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('UTC-aware timestamp required')
    return value.astimezone(timezone.utc)


def _record(job: Job, result: Result | None) -> JobRecord:
    data = job.upload
    original = AcceptedUpload(Path(data['path']), data['sha256'], data['size_bytes'], VideoInfo(**data['video']))
    return JobRecord(job.job_id, job.state, job.accepted_at, job.deadline_at, original,
                     result.public if result else None, result.diagnostics if result else None, job.reason)


def public_job(record: JobRecord) -> dict:
    if record.state in ('queued', 'running'):
        value = {'job_id': record.job_id, 'status': 'processing'}
    elif record.state == 'failed':
        value = {'job_id': record.job_id, 'status': 'failed', 'reason': record.reason}
    else:
        if record.result is None:
            raise PersistenceUnavailable('Terminal result is unavailable')
        value = record.result
    validate_contract('job', value)
    return value


class JobRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def create(self, upload: AcceptedUpload, *, now: datetime, deadline_seconds: int = 240) -> JobRecord:
        now = _utc(now)
        if not 0 < deadline_seconds <= 240:
            raise ValueError('Deadline must be within 240 seconds')
        data = asdict(upload)
        data['path'] = str(upload.path)
        job = Job(job_id=str(uuid4()), state='queued', accepted_at=now,
                  deadline_at=now + timedelta(seconds=deadline_seconds), upload=data,
                  lease_token=0)
        try:
            with Session(self.engine, expire_on_commit=False) as session, session.begin():
                session.add(job)
                session.flush()
                session.add(Outbox(job_id=job.job_id, created_at=now))
                session.flush()
            return _record(job, None)
        except IntegrityError as error:
            if getattr(getattr(error.orig, 'diag', None), 'constraint_name', None) == 'uq_jobs_one_unfinished':
                raise CapacityExceeded('Unfinished job capacity occupied') from None
            raise PersistenceUnavailable('Durable acceptance failed') from error
        except SQLAlchemyError as error:
            raise PersistenceUnavailable('Durable acceptance failed') from error

    def get(self, job_id: str) -> JobRecord | None:
        try:
            job_id = str(UUID(job_id))
        except (ValueError, TypeError, AttributeError):
            return None
        try:
            with Session(self.engine) as session:
                row = session.execute(select(Job, Result).outerjoin(Result).where(Job.job_id == job_id)).first()
                return _record(*row) if row else None
        except SQLAlchemyError as error:
            raise PersistenceUnavailable('Job state unavailable') from error

    @staticmethod
    def _current(lease: JobLease, now: datetime):
        return and_(Job.job_id == lease.job_id, Job.state == 'running', Job.lease_owner == lease.owner,
                    Job.lease_token == lease.token, Job.lease_expires_at > now, Job.deadline_at > now)

    def claim(self, job_id: str, owner: str, *, now: datetime, lease_seconds: int = 30) -> JobLease | None:
        now = _utc(now)
        if not owner or len(owner) > 128 or lease_seconds <= 0:
            raise ValueError('Valid owner and positive lease duration required')
        statement = update(Job).where(Job.job_id == job_id, Job.deadline_at > now,
            or_(Job.state == 'queued', and_(Job.state == 'running', Job.lease_expires_at <= now))).values(
                state='running', lease_owner=owner, lease_token=Job.lease_token + 1,
                lease_expires_at=func.least(Job.deadline_at, now + timedelta(seconds=lease_seconds)))
        try:
            with self.engine.begin() as connection:
                row = connection.execute(statement.returning(Job.job_id, Job.lease_token, Job.lease_expires_at)).first()
                return JobLease(row.job_id, owner, row.lease_token, row.lease_expires_at) if row else None
        except SQLAlchemyError as error:
            raise PersistenceUnavailable('Lease claim failed') from error

    def renew(self, lease: JobLease, *, now: datetime, lease_seconds: int = 30) -> JobLease | None:
        now = _utc(now)
        if lease_seconds <= 0:
            raise ValueError('Positive lease duration required')
        statement = update(Job).where(self._current(lease, now)).values(
            lease_expires_at=func.least(Job.deadline_at, now + timedelta(seconds=lease_seconds)))
        try:
            with self.engine.begin() as connection:
                expires = connection.scalar(statement.returning(Job.lease_expires_at))
                return JobLease(lease.job_id, lease.owner, lease.token, expires) if expires else None
        except SQLAlchemyError as error:
            raise PersistenceUnavailable('Lease renewal failed') from error

    def finish(self, lease: JobLease, result: AnalysisBundle, *, now: datetime) -> bool:
        now = _utc(now)
        validate_contract('job', result.public)
        validate_contract('diagnostics', result.diagnostics)
        if (result.public.get('status') != 'done' or result.public['job_id'] != lease.job_id
                or result.diagnostics.get('job_id') != lease.job_id
                or result.diagnostics.get('public') != result.public):
            raise ValueError('Result must match this job and its diagnostics')
        try:
            with Session(self.engine) as session, session.begin():
                job = session.scalar(select(Job).where(self._current(lease, now)).with_for_update())
                if job is None:
                    return False
                # A caller timestamp can become stale while waiting for a row
                # lock. PostgreSQL transaction_timestamp is stale too; use its
                # wall clock after acquiring the lock and after flushing IO.
                cutoff = min(job.deadline_at, job.lease_expires_at)
                completed = max(now, session.scalar(select(func.clock_timestamp())))
                if completed >= cutoff:
                    return False
                job.state, job.lease_owner, job.lease_expires_at = 'done', None, None
                stored = Result(job_id=lease.job_id, public=result.public,
                                diagnostics=result.diagnostics, completed_at=completed)
                session.add(stored)
                session.flush()
                if max(now, session.scalar(select(func.clock_timestamp()))) >= cutoff:
                    session.rollback()
                    return False
            return True
        except SQLAlchemyError as error:
            raise PersistenceUnavailable('Result commit failed') from error

    def fail(self, lease: JobLease, reason: str, *, now: datetime) -> bool:
        now = _utc(now)
        validate_contract('job', {'job_id': lease.job_id, 'status': 'failed', 'reason': reason})
        try:
            with self.engine.begin() as connection:
                return connection.scalar(update(Job).where(self._current(lease, now)).values(
                    state='failed', reason=reason, lease_owner=None, lease_expires_at=None).returning(Job.job_id)) is not None
        except SQLAlchemyError as error:
            raise PersistenceUnavailable('Failure state commit failed') from error

    def expire(self, *, now: datetime) -> list[str]:
        now = _utc(now)
        try:
            with self.engine.begin() as connection:
                return list(connection.scalars(update(Job).where(Job.state.in_(['queued', 'running']),
                    Job.deadline_at <= now).values(state='failed', reason='deadline_exceeded',
                    lease_owner=None, lease_expires_at=None).returning(Job.job_id)))
        except SQLAlchemyError as error:
            raise PersistenceUnavailable('Deadline state commit failed') from error

    def pending_outbox(self, *, limit: int = 100) -> list[OutboxItem]:
        if not 1 <= limit <= 1000:
            raise ValueError('Outbox batch limit must be between 1 and 1000')
        try:
            with Session(self.engine) as session:
                rows = session.scalars(select(Outbox).join(Job).where(Outbox.published_at.is_(None),
                    Job.state.in_(['queued', 'running'])).order_by(Outbox.id).limit(limit))
                return [OutboxItem(row.id, row.job_id, row.created_at) for row in rows]
        except SQLAlchemyError as error:
            raise PersistenceUnavailable('Outbox unavailable') from error

    def mark_published(self, outbox_id: int, *, now: datetime) -> None:
        now = _utc(now)
        try:
            with self.engine.begin() as connection:
                connection.execute(update(Outbox).where(Outbox.id == outbox_id,
                    Outbox.published_at.is_(None)).values(published_at=now))
        except SQLAlchemyError as error:
            raise PersistenceUnavailable('Outbox publish state failed') from error
