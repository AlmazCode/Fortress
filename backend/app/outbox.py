"""PostgreSQL repairs missing publications, including Redis data loss."""
from datetime import datetime, timedelta, timezone
import math

from kombu.exceptions import OperationalError
from redis.exceptions import RedisError
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import SQLAlchemyError

from contracts.python_ports import PersistenceUnavailable
from .models import Job, Outbox


def utc_now():
    return datetime.now(timezone.utc)


class BrokerUnavailable(RuntimeError):
    pass


class CeleryPublisher:
    def __init__(self, app):
        self.app = app

    def publish(self, job_id, deadline_at, *, now):
        remaining = (deadline_at-now).total_seconds()
        if remaining <= 0:
            return
        try:
            self.app.send_task('fortress.analyze', args=[job_id], task_id=job_id,
                expires=deadline_at, time_limit=max(1, math.ceil(remaining)),
                soft_time_limit=max(.1, remaining-.5), retry=False,
                argsrepr='(<job-id>,)', kwargsrepr='{}')
        except (OperationalError, RedisError, OSError):
            raise BrokerUnavailable('Broker is unavailable') from None


class OutboxDispatcher:
    def __init__(self, repository, publisher, *, republish_seconds=5):
        if republish_seconds <= 0:
            raise ValueError('Positive repair interval required')
        self.repository, self.publisher = repository, publisher
        self.republish_seconds = republish_seconds

    def tick(self, *, now=None):
        now = now or utc_now()
        expired = self.repository.expire(now=now)
        # Published is an acknowledgement of transport, not of execution.
        # Repair queued or abandoned running jobs after Redis/worker restart.
        try:
            with self.repository.engine.connect() as connection:
                candidates = connection.execute(select(Outbox.id, Outbox.job_id, Job.deadline_at).join(Job).where(
                    Job.deadline_at > now,
                    or_(Job.state == 'queued', and_(Job.state == 'running', Job.lease_expires_at <= now)),
                    or_(Outbox.published_at.is_(None), Outbox.published_at <= now-timedelta(seconds=self.republish_seconds))
                ).order_by(Outbox.id).limit(100)).all()
        except SQLAlchemyError:
            raise PersistenceUnavailable('Outbox lookup is unavailable') from None
        published, unavailable = 0, 0
        for item in candidates:
            try:
                self.publisher.publish(item.job_id, item.deadline_at, now=now)
            except BrokerUnavailable:
                unavailable += 1
                continue
            try:
                with self.repository.engine.begin() as connection:
                    connection.execute(update(Outbox).where(Outbox.id == item.id).values(published_at=now))
            except SQLAlchemyError:
                # A successful send with failed mark is deliberately republished.
                raise PersistenceUnavailable('Outbox acknowledgement is unavailable') from None
            published += 1
        return {'published': published, 'unavailable': unavailable, 'expired': len(expired)}
