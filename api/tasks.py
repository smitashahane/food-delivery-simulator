"""
Celery task stubs — full implementation in Phase 3.
These stubs exist so the worker container starts without import errors.
"""
import logging
import os

from celery_app import celery
from database import init_db
from events import init_redis

logger = logging.getLogger(__name__)

# Workers need their own DB + Redis connections (separate process from API)
_initialised = False


def _ensure_init():
    global _initialised
    if not _initialised:
        init_db(os.environ["DATABASE_URL"])
        init_redis(os.getenv("REDIS_URL", "redis://redis:6379/0"))
        _initialised = True


@celery.task(
    name="tasks.confirm_order",
    bind=True,
    max_retries=5,
    acks_late=True,
    reject_on_worker_lost=True,
)
def confirm_order(self, order_id: str):
    _ensure_init()
    logger.info('{"order_id":"%s","stage":"confirm","msg":"stub — Phase 3 will implement this"}', order_id)


@celery.task(
    name="tasks.prepare_order",
    bind=True,
    max_retries=5,
    acks_late=True,
    reject_on_worker_lost=True,
)
def prepare_order(self, order_id: str):
    _ensure_init()
    logger.info('{"order_id":"%s","stage":"prepare","msg":"stub"}', order_id)


@celery.task(
    name="tasks.assign_courier",
    bind=True,
    max_retries=5,
    acks_late=True,
    reject_on_worker_lost=True,
)
def assign_courier(self, order_id: str):
    _ensure_init()
    logger.info('{"order_id":"%s","stage":"assign_courier","msg":"stub"}', order_id)


@celery.task(
    name="tasks.complete_delivery",
    bind=True,
    max_retries=5,
    acks_late=True,
    reject_on_worker_lost=True,
)
def complete_delivery(self, order_id: str):
    _ensure_init()
    logger.info('{"order_id":"%s","stage":"complete_delivery","msg":"stub"}', order_id)


@celery.task(
    name="tasks.process_dlq",
    bind=True,
    acks_late=True,
)
def process_dlq(self, order_id: str, stage: str, error: str):
    _ensure_init()
    logger.error(
        '{"order_id":"%s","stage":"%s","msg":"Order in dead-letter queue","error":"%s"}',
        order_id, stage, error,
    )
