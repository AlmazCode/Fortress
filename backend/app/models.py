"""Database structures shared by the job repository and outbox dispatcher."""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = 'jobs'
    job_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    upload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(64))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_token: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default='0')
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("state IN ('queued', 'running', 'done', 'failed')", name='ck_jobs_state'),
        CheckConstraint('deadline_at > accepted_at', name='ck_jobs_deadline'),
        CheckConstraint('lease_token >= 0', name='ck_jobs_token'),
        CheckConstraint("(state = 'failed') = (reason IS NOT NULL)", name='ck_jobs_reason'),
        CheckConstraint("(state = 'running' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
                        "(state <> 'running' AND lease_owner IS NULL AND lease_expires_at IS NULL)", name='ck_jobs_lease'),
        Index('uq_jobs_one_unfinished', text('(1)'), unique=True,
              postgresql_where=text("state IN ('queued', 'running')")),
    )


class Result(Base):
    __tablename__ = 'results'
    job_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey('jobs.job_id', ondelete='CASCADE'), primary_key=True)
    public: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    diagnostics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Outbox(Base):
    __tablename__ = 'outbox'
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey('jobs.job_id', ondelete='CASCADE'), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
