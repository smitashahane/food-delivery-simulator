"""Tests for the state machine — transitions, idempotency, dead-lettering."""
import uuid
import pytest

from models import Order, OrderStatus, OrderEvent
from pipeline import transition, AlreadyTransitionedError, InvalidTransitionError
from database import get_session


def _create_order(status=OrderStatus.PLACED):
    session = get_session()
    order = Order(
        id=uuid.uuid4(),
        customer_id="cust-test",
        restaurant_id="rest-01",
        items=[{"name": "Burger", "quantity": 1, "price": 12.5}],
        total_amount=12.5,
        status=status,
    )
    event = OrderEvent(order_id=order.id, from_status=None, to_status=status, worker_id="test")
    session.add(order)
    session.add(event)
    session.commit()
    return str(order.id)


def test_valid_transition_succeeds(app):
    with app.app_context():
        oid = _create_order(OrderStatus.PLACED)
        order = transition(oid, OrderStatus.PLACED, OrderStatus.CONFIRMED, "test-worker")
        assert order.status == OrderStatus.CONFIRMED


def test_transition_records_event(app):
    with app.app_context():
        oid = _create_order(OrderStatus.PLACED)
        transition(oid, OrderStatus.PLACED, OrderStatus.CONFIRMED, "test-worker", reason="unit test")
        events = get_session().query(OrderEvent).filter_by(order_id=uuid.UUID(oid)).all()
        last = events[-1]
        assert last.from_status == OrderStatus.PLACED
        assert last.to_status == OrderStatus.CONFIRMED
        assert last.reason == "unit test"


def test_already_transitioned_is_idempotent(app):
    with app.app_context():
        oid = _create_order(OrderStatus.CONFIRMED)
        with pytest.raises(AlreadyTransitionedError):
            transition(oid, OrderStatus.PLACED, OrderStatus.CONFIRMED, "test-worker")


def test_invalid_transition_raises(app):
    with app.app_context():
        oid = _create_order(OrderStatus.PLACED)
        with pytest.raises(InvalidTransitionError):
            transition(oid, OrderStatus.PLACED, OrderStatus.DELIVERED, "test-worker")


def test_failed_to_dead_lettered(app):
    """FAILED → DEAD_LETTERED must be a valid transition."""
    with app.app_context():
        oid = _create_order(OrderStatus.FAILED)
        order = transition(oid, OrderStatus.FAILED, OrderStatus.DEAD_LETTERED, "dlq-processor")
        assert order.status == OrderStatus.DEAD_LETTERED


def test_order_not_found_raises(app):
    with app.app_context():
        with pytest.raises(ValueError):
            transition(str(uuid.uuid4()), OrderStatus.PLACED, OrderStatus.CONFIRMED, "test")
