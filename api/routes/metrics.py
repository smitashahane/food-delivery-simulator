import logging
from datetime import datetime, timezone, timedelta

from flask import Blueprint, Response, jsonify
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy import func

from database import get_session
from models import Order, OrderStatus

logger = logging.getLogger(__name__)
metrics_bp = Blueprint("metrics", __name__)


@metrics_bp.get("/metrics")
def prometheus_metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@metrics_bp.get("/api/stats")
def stats():
    """JSON summary consumed by the React dashboard."""
    session = get_session()

    # Counts per status
    rows = session.query(Order.status, func.count(Order.id)).group_by(Order.status).all()
    counts = {status.value: 0 for status in OrderStatus}
    for status, count in rows:
        counts[status.value] = count

    # Orders placed in last 5 minutes (throughput proxy)
    five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
    recent_total = (
        session.query(func.count(Order.id))
        .filter(Order.placed_at >= five_min_ago)
        .scalar()
    ) or 0
    orders_per_minute = round(recent_total / 5, 2)

    # Error rate: failed orders placed in last 5 min / total placed in last 5 min
    recent_failed = (
        session.query(func.count(Order.id))
        .filter(Order.placed_at >= five_min_ago, Order.status == OrderStatus.FAILED)
        .scalar()
    ) or 0
    error_rate = round(recent_failed / recent_total, 4) if recent_total else 0.0

    return jsonify({
        "counts_by_status": counts,
        "orders_per_minute_last_5": orders_per_minute,
        "error_rate_last_5min": error_rate,
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
    })
