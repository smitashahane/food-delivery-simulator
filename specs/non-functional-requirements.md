# Non-Functional Requirements

## NFR1 — Correctness (highest priority)

- **Zero order loss**: an order that has been accepted (202 returned) must eventually reach a terminal state (`delivered`, `cancelled`, `dead_lettered`). It must never silently disappear.
- **Zero duplicate processing**: an order must never be transitioned into the same state twice, even if a worker crashes and retries.
- **Strict ordering**: state transitions must only move forward in the defined lifecycle. An order cannot go from `preparing` back to `confirmed`, or skip `ready` to go directly to `out_for_delivery`.
- **Audit completeness**: every state transition must produce an `order_events` record. The full history of any order must be reconstructable from that table alone.

---

## NFR2 — Throughput

- **Steady state**: sustain **20 orders/second** on a single developer machine (4-core, 16 GB RAM) without dropping orders.
- **Burst**: handle a **10x spike (200 orders/second)** for up to 60 seconds.
  - Orders may queue during the spike — they must not be dropped or return errors.
  - Queue depth must drain back to zero within 5 minutes of the burst ending.
- **POST /orders latency**: must respond in **< 100ms** (enqueue and return; do not block on pipeline processing).

---

## NFR3 — Latency

- `POST /orders` p99 < 100ms at steady state
- `GET /orders/{id}` p99 < 200ms
- Dashboard state-change lag: a state transition must appear in the UI within **2 seconds** of occurring
- SSE connection must deliver events with < 500ms end-to-end delay under steady state load

---

## NFR4 — Fault Tolerance

| Failure scenario | Expected behaviour |
|------------------|--------------------|
| Downstream simulator returns 5xx | Retry with exponential backoff; pipeline continues |
| Downstream simulator rate-limits (429) | Respect Retry-After header; retry after delay |
| Downstream simulator total blackout | Retries accumulate; orders fail gracefully after max retries |
| Celery worker process crashes mid-task | Task re-queues (acks_late); next worker picks it up |
| Redis restarts | In-flight tasks survive (AOF persistence); broker reconnects automatically |
| Postgres restarts | SQLAlchemy connection pool retries; no order data lost |
| API container restarts | Stateless; restarts instantly; load generator retries failed POSTs |
| Duplicate POST /orders | Rejected with 409; no duplicate row created |

No failure scenario above should require manual operator intervention to recover.

---

## NFR5 — Observability

### Logging
- All logs are structured JSON to stdout
- Every log line emitted during order processing must include:
  - `order_id`
  - `stage` (current pipeline stage)
  - `worker_id` (Celery worker hostname)
  - `timestamp` (ISO 8601)
  - `level` (`info` / `warning` / `error`)
- A single order's full journey must be traceable with: `docker logs worker | grep <order_id>`

### Metrics (Prometheus)
All exposed at `GET /metrics` in Prometheus text format.

| Metric | Type | Labels |
|--------|------|--------|
| `orders_ingested_total` | Counter | — |
| `orders_by_status` | Gauge | `status` |
| `order_stage_duration_seconds` | Histogram | `stage` |
| `downstream_requests_total` | Counter | `service`, `http_status` |
| `downstream_errors_total` | Counter | `service`, `error_type` |
| `celery_queue_depth` | Gauge | `queue` |
| `dlq_orders_total` | Counter | — |
| `retry_attempts_total` | Counter | `stage` |

### Dashboards
- Prometheus pre-configured to scrape `api:5000/metrics` every 15 seconds
- Grafana pre-provisioned with:
  - Orders ingested/sec (rate over 1m)
  - Active orders per status (stacked area)
  - Stage latency percentiles (p50, p95, p99)
  - Downstream error rate per service
  - Dead-letter queue depth
  - Celery worker count and queue depth
- No manual dashboard import required — everything loads on `docker compose up`

---

## NFR6 — Operability

- `docker compose up` starts the entire system with zero additional configuration
- `docker compose up --scale worker=4` scales Celery workers without any config changes
- Load generator is controlled entirely via environment variables — no container restart needed to change rate (reads env on startup)
- Grafana dashboard is pre-provisioned — no manual JSON import
- All services must pass their docker-compose `healthcheck` before dependent services start
- `.env.example` documents every environment variable with its default

---

## NFR7 — Resource Isolation

Each service in docker-compose has resource limits to prevent one service starving others:

| Service | CPU limit | Memory limit |
|---------|-----------|-------------|
| api | 0.5 | 512 MB |
| worker (per instance) | 1.0 | 512 MB |
| postgres | 1.0 | 1 GB |
| redis | 0.5 | 256 MB |
| restaurant | 0.25 | 128 MB |
| courier | 0.25 | 128 MB |
| prometheus | 0.25 | 256 MB |
| grafana | 0.25 | 256 MB |
| frontend | 0.25 | 128 MB |
| loadgen | 0.25 | 128 MB |

---

## NFR8 — Security (minimal, local-only system)

- No authentication required (local development system)
- No secrets in docker-compose.yml — all credentials in `.env` (gitignored)
- Postgres not exposed on host by default (internal Docker network only)
- Redis not exposed on host by default
- Only ports 5000, 8080, 3000, 9090, 5555 exposed to host
