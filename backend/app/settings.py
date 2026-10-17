"""Explicit local runtime configuration. Secrets are never represented/logged."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import tomllib

from sqlalchemy.engine import make_url
from .auth import ApiKeyAuth


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    database_url: str = field(repr=False)
    redis_url: str = field(repr=False)
    runtime_root: Path
    release_root: Path | None = None
    profile: str = 'production'

    def __post_init__(self):
        ApiKeyAuth(self.api_key)
        if make_url(self.database_url).get_backend_name() != 'postgresql':
            raise ValueError('PostgreSQL configuration required')
        if not self.redis_url.startswith(('redis://', 'rediss://', 'redis+socket://')):
            raise ValueError('Redis configuration required')
        if self.profile not in ('production', 'test'):
            raise ValueError('Unknown application profile')
        if not Path(self.runtime_root).is_absolute():
            raise ValueError('Absolute local runtime root required')
        if self.release_root is not None and not Path(self.release_root).is_absolute():
            raise ValueError('Absolute local release root required')

    @classmethod
    def from_env(cls):
        config = {}
        if os.environ.get('FORTRESS_CONFIG'):
            with Path(os.environ['FORTRESS_CONFIG']).open('rb') as source:
                config = tomllib.load(source)
        if os.environ.get('FORTRESS_PROFILE', config.get('profile', 'production')) != 'production':
            raise ValueError('The CLI only starts production; tests require explicit Python injection')
        root = os.environ.get('FORTRESS_RUNTIME_ROOT', config.get('runtime_root', ''))
        if not root:
            raise ValueError('Configure FORTRESS_RUNTIME_ROOT outside the checkout')
        release = os.environ.get('FORTRESS_RELEASE_ROOT', config.get('release_root', ''))
        try:
            return cls(api_key=os.environ['FORTRESS_API_KEY'], database_url=os.environ['DATABASE_URL'],
                       redis_url=os.environ['REDIS_URL'], runtime_root=Path(root),
                       release_root=Path(release) if release else None)
        except KeyError:
            raise ValueError('Configure FORTRESS_API_KEY, DATABASE_URL and REDIS_URL') from None
