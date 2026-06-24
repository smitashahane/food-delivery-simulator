import logging
import time
from datetime import datetime, timezone, timedelta

import os

from flask import Blueprint, Response, jsonify
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry
from prometheus_client.multiprocess import MultiProcessCollector
from sqlalchemy import func

from database import get_session
from events import get_redis
from models import Order, OrderStatus

logger = logging.getLogger(__name__)
metrics_bp = Blueprint("metrics", __name__)


@metrics_bp.get("/metrics")
def prometheus_metrics():
    _sync_redis_to_gauges()
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        MultiProcessCollector(registry)
        return Response(generate_latest(registry), mimetype=CONTENT_TYPE_LATEST)
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


def _sync_redis_to_gauges() -> None:
    """
    Pull Redis-backed counters into prometheus Gauges so Prometheus can scrape them.
    Called on every /metrics scrape — cheap reads, best-effort.
    """
    try:
        from metrics_registry import celery_queue_depth
        r = get_redis()
        depth = r.llen("pipeline") or 0
        celery_queue_depth.set(depth)
    except Exception:
        pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_downstream_health(service: str) -> str:
    """
    Derives health status from Redis keys written by pipeline tasks.

      healthy  — last success < 30s ago and no consecutive errors
      degraded — last success < 30s ago but ≥ 1 consecutive error
      down     — no successful call in last 30s OR ≥ 5 consecutive errors
      unknown  — no data yet (no calls have been made)
    """
    try:
        r = get_redis()
        last_success_raw = r.get(f"health:{service}:last_success")
        consec_errors    = int(r.get(f"health:{service}:consec_errors") or 0)

        if not last_success_raw:
            return "unknown"

        age = time.time() - float(last_success_raw)

        if age > 30 or consec_errors >= 5:
            return "down"
        if consec_errors >= 1:
            return "degraded"
        return "healthy"
    except Exception:
        return "unknown"


def record_order_placed() -> None:
    """
    Increment the current 30-second throughput bucket.
    Called by POST /orders after a successful DB insert.
    Buckets expire after 6 minutes so memory doesn't grow unbounded.
    """
    try:
        bucket = int(time.time() // 30)
        key    = f"throughput:{bucket}"
        r = get_redis()
        r.incr(key)
        r.expire(key, 360)   # 6 min TTL
    except Exception:
        pass


def _throughput_history() -> list[dict]:
    """
    Returns the last 10 × 30s buckets as a time series for the chart.
    Each point: { t: "HH:MM:SS", opm: <orders per minute> }
    """
    try:
        r      = get_redis()
        now    = int(time.time() // 30)
        points = []
        for i in range(9, -1, -1):
            bucket = now - i
            key    = f"throughput:{bucket}"
            count  = int(r.get(key) or 0)
            ts     = datetime.fromtimestamp(bucket * 30, tz=timezone.utc)
            points.append({
                "t":   ts.strftime("%H:%M:%S"),
                "opm": count * 2,   # ×2 converts per-30s to per-minute rate
            })
        return points
    except Exception:
        return []


# ── Endpoints ─────────────────────────────────────────────────────────────────

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

    # Error rate
    recent_failed = (
        session.query(func.count(Order.id))
        .filter(Order.placed_at >= five_min_ago, Order.status == OrderStatus.FAILED)
        .scalar()
    ) or 0
    error_rate = round(recent_failed / recent_total, 4) if recent_total else 0.0

    # Retry + DLQ counters from Redis
    redis = get_redis()
    retry_stages = ["confirm_order", "prepare_order", "assign_courier", "complete_delivery"]
    retry_counts = {}
    for stage in retry_stages:
        val = redis.get(f"metrics:retries:{stage}")
        retry_counts[stage] = int(val) if val else 0
    total_retries = int(redis.get("metrics:retries:total") or 0)
    dlq_total     = int(redis.get("metrics:dlq_total")     or 0)

    return jsonify({
        "counts_by_status":         counts,
        "orders_per_minute_last_5": orders_per_minute,
        "error_rate_last_5min":     error_rate,
        "retries_by_stage":         retry_counts,
        "total_retries":            total_retries,
        "dlq_total":                dlq_total,
        "downstream_health": {
            "restaurant": _compute_downstream_health("restaurant"),
            "courier":    _compute_downstream_health("courier"),
        },
        "throughput_history":       _throughput_history(),
        "snapshot_at":              datetime.now(timezone.utc).isoformat(),
    })
