# Architecture

## Overview

```
Load Generator → Flask API → PostgreSQL (source of truth)
                           → Redis (Celery broker + SSE pub/sub)
                           → Celery Workers (pipeline state machine)
                              → Restaurant Simulator (flaky)
                              → Courier Simulator (flaky)

Flask API → SSE /stream → React Dashboard

Prometheus scrapes Flask /metrics
Grafana reads Prometheus
```

## Order Lifecycle

```
placed → confirmed → preparing → ready → out_for_delivery → delivered
                                                          ↘
  any non-terminal state → cancelled
  any state              → failed  (retries exhausted)
  failed / cancelled     → dead_lettered
```

Terminal states: `delivered`, `cancelled`, `dead_lettered`

---

## Technology Decisions

### Message Queue / Task Processing: Celery + Redis

Celery drives the order pipeline — each lifecycle stage is a Celery task.
Workers pick up tasks, call the downstream simulator, update the DB, and
chain the next task on success.

**Why not the alternatives:**

| Option | Verdict | Reason |
|--------|---------|--------|
| Celery + Redis | **Selected** | Retry/backoff/DLQ built-in, Flower UI, large ecosystem |
| RabbitMQ + Celery | Skip | True AMQP broker but heavier to operate; AMQP guarantees not needed on one machine |
| Redis Streams (raw) | Skip | Lighter, but retry/scheduling must be re-implemented manually |
| Kafka | Skip | Designed for distributed clusters; massive overkill for one machine |

**Key config:**
- Broker: `redis://redis:6379/0`
- Result backend: `redis://redis:6379/1`
- Task ID format: `{order_id}:{stage}` — enables idempotency checks on retry
- `acks_late=True` — task is not acknowledged until it completes, so a worker crash re-queues it

---

### Primary State Store: PostgreSQL

Source of truth for every order. State transitions use `SELECT FOR UPDATE`
to acquire a row-level lock before changing state — prevents two concurrent
workers from racing on the same order.

**Why not alternatives:**

| Option | Verdict | Reason |
|--------|---------|--------|
| PostgreSQL | **Selected** | ACID, row-level locks, mature, handles concurrent writes from N workers |
| Redis as state store | Skip | No row-level locking; can't guarantee exactly-once transitions |
| SQLite | Skip | Collapses under concurrent writes from multiple workers |
| MongoDB | Skip | ACID transactions in newer versions but less mature; no benefit over Postgres here |

**Schema approach:**
- `orders` table — current state + metadata
- `order_events` table — append-only audit log of every transition with timestamp
- `UNIQUE(order_id)` on `orders` — rejects duplicate order submissions at DB level

**Exactly-once transition pattern:**
```sql
BEGIN;
SELECT id, status FROM orders WHERE id = $1 FOR UPDATE;
-- assert current status is valid predecessor
UPDATE orders SET status = $2, updated_at = NOW() WHERE id = $1;
INSERT INTO order_events (order_id, from_status, to_status, worker_id, ts) VALUES (...);
COMMIT;
```

---

### Live Updates: Server-Sent Events (SSE)

The pipeline publishes a Redis pub/sub message on every state transition.
The Flask `/stream` endpoint subscribes and forwards events to the browser.
React uses `EventSource`.

**Why not WebSockets:**

| | SSE | WebSockets |
|---|---|---|
| Direction | Server→Client only | Bidirectional |
| Flask support | Native, no extra library | Needs flask-socketio + gevent/eventlet |
| Auto-reconnect | Built into the spec | Manual implementation |
| Need bidirectional? | No — dashboard is read-only | — |

---

### Observability: Prometheus + Grafana + Structured Logs

- `prometheus_client` library exposes `/metrics` on the Flask app
- Prometheus scrapes on 15s interval
- Grafana dashboard pre-provisioned via `grafana/dashboard.json` (no manual import)
- All logs are JSON to stdout — `order_id` present in every line
- Flower (Celery's built-in UI) at `:5555` for task-level debugging

**Key metrics:**
- `orders_ingested_total` — counter
- `orders_by_status` — gauge per status label
- `order_stage_duration_seconds` — histogram per stage label
- `downstream_requests_total{service, status}` — counter
- `downstream_errors_total{service}` — counter
- `celery_queue_depth` — gauge
- `dlq_orders_total` — counter

---

## Docker Compose Services

| Service | Image | Port | Role |
|---------|-------|------|------|
| `api` | python:3.11 | 5000 | Flask API — ingestion, queries, SSE, /metrics |
| `worker` | python:3.11 | — | Celery workers — pipeline processing |
| `flower` | mher/flower | 5555 | Celery task monitor UI |
| `postgres` | postgres:15 | 5432 | Order state store |
| `redis` | redis:7 | 6379 | Celery broker + SSE pub/sub |
| `restaurant` | python:3.11 | 5001 | Flaky restaurant API simulator |
| `courier` | python:3.11 | 5002 | Flaky courier API simulator |
| `prometheus` | prom/prometheus | 9090 | Metrics collection |
| `grafana` | grafana/grafana | 3000 | Ops dashboards |
| `frontend` | node:18 / nginx | 8080 | React dashboard |
| `loadgen` | python:3.11 | — | Order traffic generator |

Workers can be scaled: `docker compose up --scale worker=4`

---

## Failure Handling

### Downstream simulator failures
- 500 errors → Celery catches exception, schedules retry with backoff
- 429 rate-limit → reads `Retry-After` header, delays retry accordingly
- Total blackout → retries continue until max_retries; then order → `failed`

### Retry policy
```
attempt 1: immediate
attempt 2: 2s delay
attempt 3: 4s delay
attempt 4: 8s delay
attempt 5: 16s delay
attempt 6: dead-letter (order marked failed)
```
Jitter (±20%) added to each delay to prevent thundering herd on recovery.

### Worker crash mid-task
`acks_late=True` means the task message is not removed from the queue until
the task function returns. A crashed worker leaves the message unacknowledged;
Redis re-delivers it to the next available worker.

### Redis restart
Celery uses Redis persistence (AOF). In-flight task messages survive restarts.
The result backend (db 1) is separate from the broker (db 0).

### Idempotency on retry
Every task begins with:
```python
order = db.session.query(Order).filter_by(id=order_id).with_for_update().one()
if order.status != expected_predecessor_status:
    return  # already transitioned by a previous attempt; safe to exit
```
