"""Alembic CLI uses DATABASE_URL; programmatic upgrades inject a connection."""
import os

from alembic import context

from backend.app.db import create_db_engine
from backend.app.models import Base

config = context.config


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


connection = config.attributes.get('connection')
if connection is not None:
    run(connection)
else:
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise RuntimeError('Set DATABASE_URL for migration')
    engine = create_db_engine(database_url)
    try:
        with engine.connect() as connection:
            run(connection)
    finally:
        engine.dispose()
