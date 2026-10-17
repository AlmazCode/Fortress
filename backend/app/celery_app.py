"""Bounded single-process analysis configuration; no fixture/production fallback."""
from celery import Celery


def create_celery(broker_url: str):
    if not broker_url.startswith(('redis://', 'rediss://', 'redis+socket://')):
        raise ValueError('A local Redis broker URL is required')
    app = Celery('fortress', broker=broker_url)
    app.conf.update(
        task_default_queue='fortress', task_serializer='json', accept_content=['json'],
        result_serializer='json', task_ignore_result=True, result_backend=None,
        worker_concurrency=1, worker_prefetch_multiplier=1, worker_pool='prefork',
        task_acks_late=True, task_reject_on_worker_lost=True,
        task_acks_on_failure_or_timeout=True, task_track_started=False,
        task_soft_time_limit=239, task_time_limit=240,
        broker_connection_timeout=1, broker_pool_limit=1,
        broker_transport_options={'visibility_timeout': 300, 'socket_timeout': 1,
                                  'socket_connect_timeout': 1, 'max_retries': 0},
        broker_connection_retry_on_startup=True,
        worker_send_task_events=False, task_send_sent_event=False,
        worker_redirect_stdouts=False, worker_hijack_root_logger=False,
        worker_enable_remote_control=False, enable_utc=True,
    )
    return app
