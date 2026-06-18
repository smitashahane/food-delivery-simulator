"""
Central prometheus_client metric definitions.

Import from here — never instantiate metrics elsewhere — so every
process sees the same registry and there are no duplicate-registration errors.
"""
from prometheus_client import Counter, Gauge, Histogram

# ── Ingestion ─────────────────────────────────────────────────────────────────

orders_ingested_total = Counter(
    "orders_ingested_total",
    "Total orders accepted by POST /orders",
)

# ── State machine ─────────────────────────────────────────────────────────────

orders_by_status = Gauge(
    "orders_by_status",
    "Current order count by lifecycle status",
    ["status"],
)

order_stage_duration_seconds = Histogram(
    "order_stage_duration_seconds",
    "Time spent in each pipeline stage (wall clock)",
    ["from_status", "to_status"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300],
)

# ── Downstream calls ──────────────────────────────────────────────────────────

downstream_requests_total = Counter(
    "downstream_requests_total",
    "HTTP calls made to downstream simulators",
    ["service", "outcome"],   # outcome: success | error | rate_limited
)

# ── Retry / DLQ ───────────────────────────────────────────────────────────────

retry_attempts_total = Counter(
    "retry_attempts_total",
    "Celery task retry attempts by stage",
    ["stage"],
)

dlq_orders_total = Counter(
    "dlq_orders_total",
    "Orders that exhausted retries and entered the dead-letter queue",
)

# ── Queue depth (written by worker, read by /metrics) ────────────────────────

celery_queue_depth = Gauge(
    "celery_queue_depth",
    "Approximate number of tasks waiting in the pipeline queue",
)
