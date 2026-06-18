import logging
import uuid

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from database import get_session
from models import Order, OrderEvent, OrderStatus

logger = logging.getLogger(__name__)
orders_bp = Blueprint("orders", __name__)


@orders_bp.post("/orders")
def place_order():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "JSON body required"}), 400

    missing = [f for f in ("customer_id", "restaurant_id", "items", "total_amount") if f not in body]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    if not isinstance(body["items"], list) or len(body["items"]) == 0:
        return jsonify({"error": "items must be a non-empty list"}), 400

    session = get_session()
    try:
        order = Order(
            id=uuid.UUID(body["order_id"]) if "order_id" in body else uuid.uuid4(),
            customer_id=body["customer_id"],
            restaurant_id=body["restaurant_id"],
            items=body["items"],
            total_amount=body["total_amount"],
            status=OrderStatus.PLACED,
        )
        session.add(order)

        event = OrderEvent(
            order_id=order.id,
            from_status=None,
            to_status=OrderStatus.PLACED,
            worker_id="api",
            reason="Order placed by customer",
        )
        session.add(event)
        session.commit()
        session.refresh(order)

        logger.info(
            '{"order_id":"%s","stage":"placed","worker_id":"api","msg":"Order accepted"}',
            order.id,
        )

        # Track throughput in Redis for the dashboard chart
        from routes.metrics import record_order_placed
        record_order_placed()

        # Enqueue pipeline — imported here to avoid circular import at module load
        from tasks import confirm_order
        confirm_order.apply_async(args=[str(order.id)], queue="pipeline")

        return jsonify({
            "order_id": str(order.id),
            "status": order.status.value,
            "placed_at": order.placed_at.isoformat(),
        }), 202

    except IntegrityError:
        session.rollback()
        return jsonify({"error": "Order already exists"}), 409
    except Exception:
        session.rollback()
        logger.exception("Failed to place order")
        return jsonify({"error": "Internal server error"}), 500


@orders_bp.get("/orders")
def list_orders():
    session = get_session()
    status_filter = request.args.get("status")
    restaurant_filter = request.args.get("restaurant_id")
    page = int(request.args.get("page", 1))
    per_page = min(int(request.args.get("per_page", 50)), 200)

    query = session.query(Order)
    if status_filter:
        try:
            query = query.filter(Order.status == OrderStatus(status_filter))
        except ValueError:
            return jsonify({"error": f"Unknown status: {status_filter}"}), 400
    if restaurant_filter:
        query = query.filter(Order.restaurant_id == restaurant_filter)

    total = query.count()
    orders = (
        query.order_by(Order.placed_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return jsonify({
        "orders": [o.to_dict() for o in orders],
        "total": total,
        "page": page,
        "per_page": per_page,
    })


@orders_bp.get("/orders/<order_id>")
def get_order(order_id):
    session = get_session()
    try:
        oid = uuid.UUID(order_id)
    except ValueError:
        return jsonify({"error": "Invalid order_id format"}), 400

    order = session.query(Order).filter_by(id=oid).first()
    if not order:
        return jsonify({"error": "Order not found"}), 404

    return jsonify(order.to_dict(include_events=True))
