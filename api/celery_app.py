import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

celery = Celery(
    "food_delivery",
    broker=REDIS_URL,
    backend=RESULT_BACKEND,
    include=["tasks"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,  # one task at a time per worker slot — important for fairness
    task_routes={
        "tasks.confirm_order": {"queue": "pipeline"},
        "tasks.prepare_order": {"queue": "pipeline"},
        "tasks.assign_courier": {"queue": "pipeline"},
        "tasks.complete_delivery": {"queue": "pipeline"},
        "tasks.process_dlq": {"queue": "dlq"},
    },
)
