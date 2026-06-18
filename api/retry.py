"""
Retry policy and dead-letter queue logic.

backoff_delay()  — returns the next retry delay with ±20% jitter
send_to_dlq()    — marks an order failed and enqueues it to the DLQ queue
"""
import logging
import random
import uuid

logger = logging.getLogger(__name__)

# Seconds to wait before each retry attempt (attempt index = 0-based)
_BACKOFF_SECONDS = [2, 4, 8, 16, 32]


def backoff_delay(attempt: int) -> float:
    """Exponential backoff with ±20% jitter to avoid thundering herd."""
    base = _BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)]
    return base * random.uniform(0.8, 1.2)


def send_to_dlq(order_id: str, stage: str, last_error: str, worker_id: str) -> None:
    """
    Called after max retries are exhausted.

    1. Transitions the order to FAILED (if not already there).
    2. Enqueues a process_dlq task for logging / alerting.
    """
    from database import get_session
    from models import Order, OrderStatus, OrderEvent
    from events import publish_state_change

    session = get_session()
    try:
        oid = uuid.UUID(order_id)
        order = session.query(Order).filter(Order.id == oid).with_for_update().one_or_none()

        if order is None:
            logger.error('{"order_id":"%s","msg":"DLQ: order not found"}', order_id)
            return

        # Only transition if not already in a terminal state
        terminal = {OrderStatus.DELIVERED, OrderStatus.FAILED, OrderStatus.CANCELLED, OrderStatus.DEAD_LETTERED}
        if order.status not in terminal:
            previous_status = order.status
            order.status = OrderStatus.FAILED
            event = OrderEvent(
                order_id=order.id,
                from_status=previous_status,
                to_status=OrderStatus.FAILED,
                worker_id=worker_id,
                reason=f"Exhausted retries at stage={stage}: {last_error}",
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
            '"msg":"max retries exhausted — sending to DLQ","error":"%s"}',
            order_id, stage, worker_id, last_error,
        )

    except Exception:
        session.rollback()
        logger.exception('{"order_id":"%s","msg":"DLQ transition failed"}', order_id)

    finally:
        # Always enqueue the DLQ task regardless of transition outcome
        from tasks import process_dlq
        process_dlq.apply_async(args=[order_id, stage, last_error], queue="dlq")
