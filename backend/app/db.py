"""PostgreSQL engine and explicit schema migration entry points."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL, make_url


def create_db_engine(url: str | URL) -> Engine:
    parsed = make_url(url)
    if parsed.get_backend_name() != 'postgresql':
        raise ValueError('Fortress persistence requires PostgreSQL')
    return create_engine(parsed.set(drivername='postgresql+psycopg'), pool_pre_ping=True,
                         pool_size=5, max_overflow=10, pool_timeout=5, echo=False,
                         hide_parameters=True, connect_args={'connect_timeout': 3})


def migrate(engine: Engine) -> None:
    """Run the committed migration chain; never create tables from live models."""
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / 'alembic.ini'))
    config.set_main_option('script_location', str(root / 'migrations'))
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')
