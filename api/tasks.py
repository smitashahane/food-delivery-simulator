"""
Celery pipeline tasks — one per lifecycle stage.

Each task follows the same pattern:
  1. Idempotency check via pipeline.transition() (SELECT FOR UPDATE)
  2. HTTP call to the downstream simulator
  3. On success  → chain the next task
  4. On HTTP/network error → self.retry() with exponential backoff
  5. On max retries exhausted → retry.send_to_dlq()
"""
import logging
import os
import socket
import time

import requests

from celery_app import celery
from database import init_db
from events import init_redis
from models import OrderStatus
from pipeline import transition, AlreadyTransitionedError, InvalidTransitionError
import retry as retry_mod

logger = logging.getLogger(__name__)

RESTAURANT_URL = os.getenv("RESTAURANT_URL", "http://restaurant:5001")
COURIER_URL    = os.getenv("COURIER_URL",    "http://courier:5002")
WORKER_ID      = socket.gethostname()

# Workers are separate processes — they need their own DB + Redis connections.
_initialised = False


def _ensure_init():
    global _initialised
    if not _initialised:
        init_db(os.environ["DATABASE_URL"])
        init_redis(os.getenv("REDIS_URL", "redis://redis:6379/0"))
        _initialised = True


# ─── Helpers ────────────────────────────────────────────────────────────────

def _http_post(url: str, payload: dict, timeout: int = 30) -> requests.Response:
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp


def _http_get(url: str, timeout: int = 30) -> requests.Response:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp


def _handle_retry(task, order_id: str, stage: str, exc: Exception) -> None:
    """Retry with backoff or send to DLQ after max retries."""
    attempt = task.request.retries
    if attempt >= task.max_retries:
        retry_mod.send_to_dlq(order_id, stage, str(exc), WORKER_ID)
        return

    # Record retry in Redis so /api/stats can surface it
    retry_mod.record_retry(stage)

    delay = retry_mod.backoff_delay(attempt)
    logger.warning(
        '{"order_id":"%s","stage":"%s","attempt":%d,"max":%d,"delay_s":%.1f,'
        '"msg":"retrying after error","error":"%s"}',
        order_id, stage, attempt + 1, task.max_retries, delay, exc,
    )
    raise task.retry(exc=exc, countdown=delay)


def _handle_rate_limit(task, order_id: str, stage: str, exc: requests.HTTPError) -> None:
    """Respect Retry-After header on 429 responses."""
    retry_after = int(exc.response.headers.get("Retry-After", 10))
    logger.warning(
        '{"order_id":"%s","stage":"%s","msg":"rate limited — retrying after %ds"}',
        order_id, stage, retry_after,
    )
    raise task.retry(exc=exc, countdown=retry_after)


# ─── Stage 1: placed → confirmed ─────────────────────────────────────────────

@celery.task(
    name="tasks.confirm_order",
    bind=True,
    max_retries=5,
    acks_late=True,
    reject_on_worker_lost=True,
)
def confirm_order(self, order_id: str):
    _ensure_init()
    stage = "confirm_order"

    try:
        transition(order_id, OrderStatus.PLACED, OrderStatus.CONFIRMED, WORKER_ID)
    except AlreadyTransitionedError:
        # Previous attempt already did this — chain forward and exit
        prepare_order.apply_async(args=[order_id], queue="pipeline")
        return
    except InvalidTransitionError as exc:
        logger.error('{"order_id":"%s","stage":"%s","msg":"invalid transition","error":"%s"}',
                     order_id, stage, exc)
        return

    try:
        _http_post(f"{RESTAURANT_URL}/confirm", {"order_id": order_id})
        logger.info('{"order_id":"%s","stage":"%s","msg":"restaurant confirmed"}', order_id, stage)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 429:
            _handle_rate_limit(self, order_id, stage, exc)
        _handle_retry(self, order_id, stage, exc)
        return
    except requests.RequestException as exc:
        _handle_retry(self, order_id, stage, exc)
        return

    prepare_order.apply_async(args=[order_id], queue="pipeline")


# ─── Stage 2: confirmed → preparing → ready ──────────────────────────────────

@celery.task(
    name="tasks.prepare_order",
    bind=True,
    max_retries=5,
    acks_late=True,
    reject_on_worker_lost=True,
)
def prepare_order(self, order_id: str):
    _ensure_init()
    stage = "prepare_order"

    # confirmed → preparing
    try:
        transition(order_id, OrderStatus.CONFIRMED, OrderStatus.PREPARING, WORKER_ID)
    except AlreadyTransitionedError:
        pass  # already preparing or further — fall through to poll
    except InvalidTransitionError as exc:
        logger.error('{"order_id":"%s","stage":"%s","msg":"invalid transition","error":"%s"}',
                     order_id, stage, exc)
        return

    # Signal restaurant to start preparing
    try:
        _http_post(f"{RESTAURANT_URL}/prepare", {"order_id": order_id})
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 429:
            _handle_rate_limit(self, order_id, stage, exc)
        _handle_retry(self, order_id, stage, exc)
        return
    except requests.RequestException as exc:
        _handle_retry(self, order_id, stage, exc)
        return

    # Poll until food is ready (max 60 polls × 2s = 2 minutes)
    for poll in range(60):
        try:
            resp = _http_get(f"{RESTAURANT_URL}/status/{order_id}")
            if resp.json().get("ready"):
                break
        except requests.RequestException as exc:
            _handle_retry(self, order_id, stage, exc)
            return
        time.sleep(2)
    else:
        exc = TimeoutError("Restaurant did not mark order ready within timeout")
        _handle_retry(self, order_id, stage, exc)
        return

    # preparing → ready
    try:
        transition(order_id, OrderStatus.PREPARING, OrderStatus.READY, WORKER_ID,
                   reason="Food ready for pickup")
    except AlreadyTransitionedError:
        pass
    except InvalidTransitionError as exc:
        logger.error('{"order_id":"%s","stage":"%s","msg":"invalid transition","error":"%s"}',
                     order_id, stage, exc)
        return

    logger.info('{"order_id":"%s","stage":"%s","msg":"food ready"}', order_id, stage)
    assign_courier.apply_async(args=[order_id], queue="pipeline")


# ─── Stage 3: ready → out_for_delivery ───────────────────────────────────────

@celery.task(
    name="tasks.assign_courier",
    bind=True,
    max_retries=5,
    acks_late=True,
    reject_on_worker_lost=True,
)
def assign_courier(self, order_id: str):
    _ensure_init()
    stage = "assign_courier"

    try:
        _http_post(f"{COURIER_URL}/assign", {"order_id": order_id})
        logger.info('{"order_id":"%s","stage":"%s","msg":"courier assigned"}', order_id, stage)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 429:
            _handle_rate_limit(self, order_id, stage, exc)
        _handle_retry(self, order_id, stage, exc)
        return
    except requests.RequestException as exc:
        _handle_retry(self, order_id, stage, exc)
        return

    try:
        transition(order_id, OrderStatus.READY, OrderStatus.OUT_FOR_DELIVERY, WORKER_ID,
                   reason="Courier assigned and picked up")
    except AlreadyTransitionedError:
        pass
    except InvalidTransitionError as exc:
        logger.error('{"order_id":"%s","stage":"%s","msg":"invalid transition","error":"%s"}',
                     order_id, stage, exc)
        return

    complete_delivery.apply_async(args=[order_id], queue="pipeline")


# ─── Stage 4: out_for_delivery → delivered ────────────────────────────────────

@celery.task(
    name="tasks.complete_delivery",
    bind=True,
    max_retries=5,
    acks_late=True,
    reject_on_worker_lost=True,
)
def complete_delivery(self, order_id: str):
    _ensure_init()
    stage = "complete_delivery"

    # Poll courier until delivered (max 90 polls × 5s = 7.5 minutes)
    for poll in range(90):
        try:
            resp = _http_get(f"{COURIER_URL}/status/{order_id}")
            if resp.json().get("delivered"):
                break
        except requests.RequestException as exc:
            _handle_retry(self, order_id, stage, exc)
            return
        time.sleep(5)
    else:
        exc = TimeoutError("Courier did not confirm delivery within timeout")
        _handle_retry(self, order_id, stage, exc)
        return

    try:
        transition(order_id, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED, WORKER_ID,
                   reason="Delivery confirmed by courier")
    except AlreadyTransitionedError:
        return
    except InvalidTransitionError as exc:
        logger.error('{"order_id":"%s","stage":"%s","msg":"invalid transition","error":"%s"}',
                     order_id, stage, exc)
        return

    logger.info('{"order_id":"%s","stage":"%s","msg":"order delivered"}', order_id, stage)


# ─── Dead-letter processor ────────────────────────────────────────────────────

@celery.task(
    name="tasks.process_dlq",
    bind=True,
    acks_late=True,
)
def process_dlq(self, order_id: str, stage: str, error: str):
    """
    Final step for failed orders.
    Logs the failure then transitions failed → dead_lettered so the
    dashboard shows a clear terminal state distinct from transient failures.
    """
    _ensure_init()
    logger.error(
        '{"order_id":"%s","stage":"%s","worker_id":"%s",'
        '"msg":"ORDER IN DEAD-LETTER QUEUE","error":"%s"}',
        order_id, stage, WORKER_ID, error,
    )

    from pipeline import transition, AlreadyTransitionedError, InvalidTransitionError
    from models import OrderStatus
    try:
        transition(
            order_id,
            OrderStatus.FAILED,
            OrderStatus.DEAD_LETTERED,
            worker_id=f"dlq-processor@{WORKER_ID}",
            reason=f"Processed by DLQ handler. Original failure at stage={stage}: {error}",
        )
    except AlreadyTransitionedError:
        pass  # already dead_lettered from a previous run
    except InvalidTransitionError:
        pass  # order may have been manually resolved
