"""Shared integration fixtures keep real services explicit and disposable."""
from test_persistence import database
from test_outbox import redis_runtime
from test_upload_decode import clip
