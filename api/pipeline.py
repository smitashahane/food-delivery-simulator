"""
Order state machine.

transition() is the single entry point for all state changes. It:
  1. Acquires a row-level lock (SELECT FOR UPDATE) so concurrent workers
     can never race on the same order.
  2. Validates the current status is the expected predecessor.
  3. Writes the new status + audit event atomically in one transaction.
  4. Publishes an SSE event so the dashboard updates in real time.
"""
import logging
import time
import uuid

from sqlalchemy.exc import SQLAlchemyError

from database import get_session
from events import publish_state_change
from models import Order, OrderEvent, OrderStatus
from metrics_registry import orders_by_status, order_stage_duration_seconds

logger = logging.getLogger(__name__)

# Every permitted forward transition. Anything not listed is illegal.
VALID_TRANSITIONS: dict[OrderStatus, list[OrderStatus]] = {
    OrderStatus.PLACED:           [OrderStatus.CONFIRMED,        OrderStatus.CANCELLED, OrderStatus.FAILED],
    OrderStatus.CONFIRMED:        [OrderStatus.PREPARING,        OrderStatus.CANCELLED, OrderStatus.FAILED],
    OrderStatus.PREPARING:        [OrderStatus.READY,            OrderStatus.CANCELLED, OrderStatus.FAILED],
    OrderStatus.READY:            [OrderStatus.OUT_FOR_DELIVERY, OrderStatus.CANCELLED, OrderStatus.FAILED],
    OrderStatus.OUT_FOR_DELIVERY: [OrderStatus.DELIVERED,        OrderStatus.FAILED],
}


class InvalidTransitionError(Exception):
    """Attempted a transition that isn't in VALID_TRANSITIONS."""


class AlreadyTransitionedError(Exception):
    """Order is already past this stage — safe to treat as a no-op on retry."""


def transition(
    order_id: str,
    from_status: OrderStatus,
    to_status: OrderStatus,
    worker_id: str,
    reason: str | None = None,
) -> Order:
    """
    Atomically move order from from_status → to_status.

    Raises:
        AlreadyTransitionedError  if the order is already at to_status (idempotent retry)
        InvalidTransitionError    if the current status is neither from_status nor to_status
        ValueError                if the order doesn't exist
    """
    session = get_session()
    try:
        oid = uuid.UUID(order_id) if isinstance(order_id, str) else order_id
        order = (
            session.query(Order)
            .filter(Order.id == oid)
            .with_for_update()          # row-level lock — blocks concurrent workers
            .one_or_none()
        )

        if order is None:
            raise ValueError(f"Order {order_id} not found")

        # Idempotency: a previous attempt already completed this transition
        if order.status == to_status:
            logger.info(
                '{"order_id":"%s","from":"%s","to":"%s","worker_id":"%s",'
                '"msg":"transition already applied — skipping"}',
                order_id, from_status.value, to_status.value, worker_id,
            )
            raise AlreadyTransitionedError(
                f"Order {order_id} already at {to_status.value}"
            )

        # Guard: order must be in the expected predecessor state
        if order.status != from_status:
            raise InvalidTransitionError(
                f"Order {order_id}: expected status={from_status.value} "
                f"but found {order.status.value} — refusing transition to {to_status.value}"
            )

        # Guard: transition must be declared in the map
        allowed = VALID_TRANSITIONS.get(from_status, [])
        if to_status not in allowed:
            raise InvalidTransitionError(
                f"Transition {from_status.value} → {to_status.value} is not permitted"
            )

        _stage_start = time.time()
        order.status = to_status

        event = OrderEvent(
            order_id=order.id,
            from_status=from_status,
            to_status=to_status,
            worker_id=worker_id,
            reason=reason,
        )
        session.add(event)
        session.commit()
        session.refresh(event)

        logger.info(
            '{"order_id":"%s","from":"%s","to":"%s","worker_id":"%s","msg":"state transition"}',
            order_id, from_status.value, to_status.value, worker_id,
        )

        # Record metrics after commit
        order_stage_duration_seconds.labels(
            from_status=from_status.value, to_status=to_status.value
        ).observe(time.time() - _stage_start)
        orders_by_status.labels(status=to_status.value).inc()
        orders_by_status.labels(status=from_status.value).dec()

        # Publish after commit so the dashboard never sees a rolled-back state
        publish_state_change(
            order_id=str(order.id),
            from_status=from_status,
            to_status=to_status,
            timestamp=event.created_at.isoformat(),
        )

        return order

    except (AlreadyTransitionedError, InvalidTransitionError, ValueError):
        session.rollback()
        raise
    except SQLAlchemyError:
        session.rollback()
        logger.exception(
            '{"order_id":"%s","msg":"DB error during transition %s→%s"}',
            order_id, from_status.value, to_status.value,
        )
        raise
