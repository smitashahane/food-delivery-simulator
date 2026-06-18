"""
Retry policy and dead-letter queue logic.

backoff_delay()  — exponential backoff with ±20% jitter
send_to_dlq()    — transitions order to FAILED, increments Redis counters,
                   enqueues process_dlq task
"""
import logging
import random
import uuid

logger = logging.getLogger(__name__)

_BACKOFF_SECONDS = [2, 4, 8, 16, 32]


def backoff_delay(attempt: int) -> float:
    """Exponential backoff with ±20% jitter to avoid thundering herd on recovery."""
    base = _BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)]
    return base * random.uniform(0.8, 1.2)


def record_retry(stage: str) -> None:
    """Increment Redis retry counter for this stage. Best-effort — never raises."""
    try:
        from events import get_redis
        get_redis().incr(f"metrics:retries:{stage}")
        get_redis().incr("metrics:retries:total")
    except Exception:
        pass


def send_to_dlq(order_id: str, stage: str, last_error: str, worker_id: str) -> None:
    """
    Called after max retries are exhausted.

    1. Transitions the order to FAILED (if not already terminal).
    2. Increments Redis DLQ counter.
    3. Enqueues process_dlq task which will then move it to DEAD_LETTERED.
    """
    from database import get_session
    from models import Order, OrderStatus, OrderEvent
    from events import publish_state_change, get_redis

    session = get_session()
    try:
        oid = uuid.UUID(order_id)
        order = (
            session.query(Order)
            .filter(Order.id == oid)
            .with_for_update()
            .one_or_none()
        )

        if order is None:
            logger.error('{"order_id":"%s","msg":"DLQ: order not found"}', order_id)
            return

        terminal = {
            OrderStatus.DELIVERED, OrderStatus.FAILED,
            OrderStatus.CANCELLED,  OrderStatus.DEAD_LETTERED,
        }
        if order.status not in terminal:
            previous_status = order.status
            order.status = OrderStatus.FAILED
            event = OrderEvent(
                order_id=order.id,
                from_status=previous_status,
                to_status=OrderStatus.FAILED,
                worker_id=worker_id,
                reason=f"Retries exhausted at stage={stage}: {last_error}",
            )
            session.add(event)
            session.commit()
            session.refresh(event)

            publish_state_change(
                order_id=order_id,
                from_status=previous_status,
                to_status=OrderStatus.FAILED,
                timestamp=event.created_at.isoformat(),
            )

        logger.error(
            '{"order_id":"%s","stage":"%s","worker_id":"%s",'
            '"msg":"retries exhausted — moving to DLQ","error":"%s"}',
            order_id, stage, worker_id, last_error,
        )

        # Increment DLQ counter in Redis (visible in /api/stats)
        try:
            get_redis().incr("metrics:dlq_total")
        except Exception:
            pass

    except Exception:
        session.rollback()
        logger.exception('{"order_id":"%s","msg":"DLQ transition failed"}', order_id)
    finally:
        from tasks import process_dlq
        process_dlq.apply_async(args=[order_id, stage, last_error], queue="dlq")
