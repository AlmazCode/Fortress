"""Durable jobs, exactly one result per job and transactional outbox."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001_jobs_outbox'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('jobs',
        sa.Column('job_id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deadline_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('upload', postgresql.JSONB, nullable=False),
        sa.Column('reason', sa.String(64)),
        sa.Column('lease_owner', sa.String(128)),
        sa.Column('lease_token', sa.BigInteger, nullable=False, server_default='0'),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("state IN ('queued','running','done','failed')", name='ck_jobs_state'),
        sa.CheckConstraint('deadline_at > accepted_at', name='ck_jobs_deadline'),
        sa.CheckConstraint('lease_token >= 0', name='ck_jobs_token'),
        sa.CheckConstraint("(state = 'failed') = (reason IS NOT NULL)", name='ck_jobs_reason'),
        sa.CheckConstraint("(state = 'running' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
                           "(state <> 'running' AND lease_owner IS NULL AND lease_expires_at IS NULL)", name='ck_jobs_lease'))
    op.execute("CREATE UNIQUE INDEX uq_jobs_one_unfinished ON jobs ((1)) WHERE state IN ('queued','running')")
    op.create_table('results',
        sa.Column('job_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('jobs.job_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('public', postgresql.JSONB, nullable=False),
        sa.Column('diagnostics', postgresql.JSONB, nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('outbox',
        sa.Column('id', sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column('job_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('jobs.job_id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True)))


def downgrade():
    op.drop_table('outbox')
    op.drop_table('results')
    op.drop_table('jobs')
