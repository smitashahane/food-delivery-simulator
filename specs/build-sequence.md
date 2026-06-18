# Build Sequence

Phases are ordered by dependency. Each phase ends with a test gate —
the system must pass the gate before the next phase starts.

---

## Phase 1 — Foundation

**Goal:** Everything starts. Nothing works yet, but all containers are healthy.

### 1.1 docker-compose skeleton
- Define all 11 services with correct networking (`app-network` bridge)
- Add `healthcheck` for postgres, redis, api, restaurant, courier
- Add `depends_on` with `condition: service_healthy`
- Add resource limits (cpu, memory) per NFR7
- Create `.env.example` with all variables and defaults

### 1.2 Postgres schema
- `orders` table with all columns + indexes
- `order_events` table with FK to orders
- `UNIQUE(order_id)` constraint on orders
- Migration script or SQLAlchemy `create_all()` on API startup

### 1.3 Flask app factory
- `app.py`: create_app(), register blueprints (placeholder routes)
- `config.py`: read all config from environment
- `database.py`: SQLAlchemy engine, session, `init_db()`
- `models.py`: Order, OrderEvent, OrderStatus enum

**Test gate:**
```bash
docker compose up postgres redis api
curl http://localhost:5000/health  # → {"status": "ok"}
docker compose ps  # all services healthy
```

---

## Phase 2 — Order Ingestion

**Goal:** Orders can enter the system and be queried.

### 2.1 Order model (complete)
- All fields, relationships, `to_dict()` serializer
- OrderStatus enum with all states

### 2.2 `POST /orders`
- Validate request body (400 on missing fields)
- Insert into DB with `placed` status
- Insert first `order_events` record (`None → placed`)
- Return 202 with order_id
- Return 409 on duplicate order_id (catch IntegrityError)

### 2.3 `GET /orders` and `GET /orders/{id}`
- Paginated list with optional `status` and `restaurant_id` filters
- Single order response includes `events` array from order_events

**Test gate:**
```bash
# place an order
curl -X POST http://localhost:5000/orders \
  -H 'Content-Type: application/json' \
  -d '{"customer_id":"c1","restaurant_id":"r1","items":[{"name":"Burger","quantity":1,"price":10}],"total_amount":10}'
# → 202 {"order_id": "...", "status": "placed"}

# query it
curl http://localhost:5000/orders/<id>
# → order with status=placed and one event

# duplicate
curl -X POST ... same body with same order_id ...
# → 409

# list
curl http://localhost:5000/orders
# → paginated list
```

---

## Phase 3 — State Machine & Pipeline

**Goal:** Orders move through the lifecycle end-to-end (simulators not flaky yet).

### 3.1 `worker/pipeline.py`
- `VALID_TRANSITIONS` map
- `transition(order_id, from_status, to_status, worker_id)` with `SELECT FOR UPDATE`
- Raises `InvalidTransitionError` on bad transition
- Raises `AlreadyTransitionedError` if order is not in `from_status` (idempotency)

### 3.2 Celery setup
- `celery_app.py`: Celery instance with broker + backend URLs
- Worker Dockerfile: same base as api, runs `celery -A tasks worker`
- `acks_late=True`, `reject_on_worker_lost=True` on all tasks

### 3.3 Tasks: confirm_order, prepare_order, assign_courier, complete_delivery
- Each task: acquire lock → call simulator → transition → chain next task
- Simulator calls use `requests` with 30s timeout
- On success: chain next task with `apply_async()`
- On exception: `self.retry(exc=exc, countdown=retry.backoff_delay(self.request.retries))`

### 3.4 Wire POST /orders to enqueue first task
- After DB insert in `POST /orders`: `confirm_order.apply_async(args=[order_id])`

**Test gate (simulators running but set to 0% failure rate):**
```bash
# set simulators to no-failure mode
curl -X POST http://localhost:5001/admin/set-failure-rate -d '{"rate": 0}'
curl -X POST http://localhost:5002/admin/set-failure-rate -d '{"rate": 0}'

# place order
curl -X POST http://localhost:5000/orders ...
ORDER_ID=<returned id>

# watch it flow
watch -n1 "curl -s http://localhost:5000/orders/$ORDER_ID | jq '.status'"
# should progress: placed → confirmed → preparing → ready → out_for_delivery → delivered
```

---

## Phase 4 — Downstream Simulators

**Goal:** Simulators behave realistically — slow, error-prone, sometimes down.

### 4.1 `simulators/chaos.py`
- `random_latency(min_s, max_s)` — blocks for random duration
- `maybe_fail(rate)` — raises SimulatorError (500 or 503) at given rate
- `maybe_rate_limit(rate)` — raises RateLimitError (429) with Retry-After header
- `blackout_check()` — returns 503 if blackout mode is active

### 4.2 Restaurant simulator (`simulators/restaurant.py`)
- `POST /confirm` — chaos: latency 1–4s, 20% fail, 5% rate-limit
- `POST /prepare` — chaos: latency 2–8s, 20% fail
- `GET /status/<order_id>` — chaos: latency 0.5s, 10% fail
- `POST /admin/set-failure-rate` — runtime control
- `POST /admin/set-blackout` — enable/disable blackout mode
- State: maintains an in-memory dict of order preparation times

### 4.3 Courier simulator (`simulators/courier.py`)
- `POST /assign` — chaos: latency 1–3s, 15% fail
- `GET /status/<order_id>` — chaos: latency 0.5–2s, 10% fail
- Delivery simulation: courier "arrives" after 5–20s from assignment
- `POST /admin/set-failure-rate` — runtime control
- `POST /admin/set-blackout` — 30s blackout, auto-recovers

**Test gate:**
```bash
# call simulators directly, observe failures
for i in {1..20}; do curl -s -o /dev/null -w "%{http_code}\n" \
  -X POST http://localhost:5001/confirm -d '{"order_id":"test","items":[]}'; done
# should see a mix of 200 and 500

# place 5 orders with simulators at default failure rates
# check that orders eventually reach delivered or failed (not stuck)
```

---

## Phase 5 — Retry & Dead-Letter

**Goal:** Failures are handled gracefully; orders never get stuck or lost.

### 5.1 `worker/retry.py`
- `backoff_delay(attempt)` — returns delay with jitter
- `handle_rate_limit(retry_after)` — delays by Retry-After value
- `send_to_dlq(order_id, stage, last_error)` — transitions to `failed`, enqueues to `dlq` queue

### 5.2 Wire retry into tasks
- Catch `requests.exceptions.RequestException` + HTTP 5xx → `self.retry(...)`
- Catch HTTP 429 → `self.retry(countdown=retry_after)`
- After `max_retries`: call `retry.send_to_dlq()`

### 5.3 Idempotency guards in every task
- On entry: check order status matches expected predecessor
- If already past this stage: log and `return` (do not raise)
- If in unexpected state: log error, `return` (do not retry)

### 5.4 Dead-letter worker
- Separate Celery queue: `dlq`
- `process_dlq_order(order_id)` task: log full order history, emit alert metric

**Test gate:**
```bash
# force restaurant to always fail
curl -X POST http://localhost:5001/admin/set-failure-rate -d '{"rate": 1.0}'

# place an order
curl -X POST http://localhost:5000/orders ...
ORDER_ID=<id>

# wait ~90s for 5 retries to exhaust
# order must end in 'failed' state, not stuck in 'placed'
curl http://localhost:5000/orders/$ORDER_ID | jq '.status'
# → "failed"

# restore simulator
curl -X POST http://localhost:5001/admin/set-failure-rate -d '{"rate": 0.2}'

# verify no orders were duplicated (order_events has exactly one of each expected transition)
```

---

## Phase 6 — Live Dashboard

**Goal:** Operations team has a live view of the pipeline.

### 6.1 Redis pub/sub in `events.py`
- `publish_state_change()` called from `pipeline.transition()` after every commit
- Publishes JSON to `order_events` Redis channel

### 6.2 `GET /stream` SSE endpoint
- Subscribe to `order_events` Redis channel
- Stream each message as `data: <json>\n\n`
- Handle client disconnect (stop iteration)
- Send a heartbeat comment every 15s to keep connection alive: `: heartbeat\n\n`

### 6.3 React scaffold
- Vite project, single-page app
- `useSSE("/stream")` hook with auto-reconnect on error
- Polling `GET /api/stats` every 10s for counts and throughput (SSE only carries events, not full state)

### 6.4 `GET /api/stats` endpoint
- Returns JSON: `{counts_by_status, orders_per_minute_last_5, error_rate_last_5min, downstream_health}`
- `downstream_health`: computed from last 30s of Prometheus counters (or a Redis TTL key set by workers)

### 6.5 Dashboard components
- `StatusCounts` — 7 stat cards, one per status, count from `/api/stats`
- `OrderFeed` — table of last 50 orders, updated on each SSE event
- `ThroughputChart` — simple line chart, polls `/api/stats` every 10s
- `SystemHealth` — green/yellow/red badge per service, from `/api/stats`

**Test gate:**
```bash
docker compose up  # everything running
# open http://localhost:8080
# place 10 orders via curl loop
# confirm: StatusCounts updates without refresh
# confirm: orders appear in OrderFeed as they're placed
# trigger restaurant blackout, confirm SystemHealth turns red
```

---

## Phase 7 — Observability

**Goal:** Engineers can see system health in Grafana; metrics are accurate.

### 7.1 Prometheus metrics in Flask
- Use `prometheus_client`: Counter, Gauge, Histogram
- Instrument `POST /orders`, state transitions (in pipeline.py), downstream calls, retries, DLQ
- `multiprocess_mode=True` for multiple worker processes

### 7.2 Prometheus config (`infra/prometheus.yml`)
```yaml
scrape_configs:
  - job_name: api
    static_configs:
      - targets: ['api:5000']
    metrics_path: /metrics
    scrape_interval: 15s
```

### 7.3 Grafana provisioning
- `infra/grafana/provisioning/datasources/datasource.yml` — points at Prometheus
- `infra/grafana/provisioning/dashboards/dashboard.yml` — auto-loads JSON
- `infra/grafana/dashboards/pipeline.json` — pre-built dashboard with all panels

### 7.4 `ThroughputChart` in dashboard
- Pulls from `/api/stats` (which reads from DB/Redis, not Prometheus directly)
- Shows last 5 minutes at 30s resolution

**Test gate:**
```bash
# open http://localhost:3000  (admin/admin)
# dashboard "Food Delivery Pipeline" exists and shows data
# run loadgen for 2 minutes
RATE=10 docker compose up loadgen
# Grafana graphs show non-zero throughput, stage latencies, etc.
```

---

## Phase 8 — Load Generator

**Goal:** We can cause a dinner rush on demand.

### 8.1 `loadgen/generator.py`
- `asyncio` + `aiohttp` for high-throughput HTTP
- Generates random: customer_id, restaurant_id (from pool of 10), items (1–5), total_amount
- Steady-rate loop: send `RATE` orders/sec
- Burst mode: after `BURST_DELAY` seconds, switch to `BURST_RPS` for `BURST_DURATION` seconds, then back
- Every 10s: log `{ts, sent, failed, current_rps}`
- On SIGTERM: log final summary, exit

**Test gate:**
```bash
# steady load
RATE=10 docker compose run loadgen
# observe dashboard: ~10 orders/sec flowing

# dinner rush
RATE=5 BURST_RPS=50 BURST_DURATION=60 BURST_DELAY=10 docker compose run loadgen
# after 10s: throughput spikes to ~50/sec on dashboard
# after 70s: drops back to ~5/sec
# no orders dropped (all reach terminal state eventually)
```

---

## Phase 9 — Hardening

**Goal:** System behaves correctly under adversarial conditions.

### 9.1 Concurrent workers — no duplicates
```bash
docker compose up --scale worker=4
RATE=20 docker compose run loadgen  # 20 orders/sec, 4 workers
# after 5 min: SELECT count(*) FROM order_events WHERE to_status = 'confirmed'
# must equal SELECT count(*) FROM orders WHERE status != 'placed'
# no order has more than one 'confirmed' event
```

### 9.2 Worker crash mid-task
```bash
# start load, then kill a worker
RATE=10 docker compose run loadgen &
docker compose kill --signal SIGKILL worker  # hard kill, no SIGTERM
docker compose up -d worker  # restart
# all orders in pipeline must eventually reach terminal state
# no order stuck in non-terminal state after 5 minutes
```

### 9.3 Simulator blackout during dinner rush
```bash
RATE=20 docker compose run loadgen &
sleep 30
curl -X POST http://localhost:5001/admin/set-blackout -d '{"enabled": true}'
sleep 30  # orders accumulate retries
curl -X POST http://localhost:5001/admin/set-blackout -d '{"enabled": false}'
# orders must recover and continue flowing — no manual intervention
```

### 9.4 Redis restart
```bash
RATE=10 docker compose run loadgen &
sleep 20
docker compose restart redis
# tasks in flight must re-queue and complete
# SSE reconnects and dashboard resumes updates
```

### 9.5 Full dinner rush scenario (demo)
```bash
# start everything fresh
docker compose down -v && docker compose up -d

# wait for healthy state, then:
RATE=5 BURST_RPS=60 BURST_DURATION=120 BURST_DELAY=20 \
  docker compose run loadgen

# demonstrate on dashboard:
# 1. Steady flow at 5/sec
# 2. Rush hits: counts spike, queue depth rises
# 3. Simulators struggle (some failures, retries visible)
# 4. Rush ends: queue drains, system recovers
# 5. Grafana shows the spike and recovery curve
```

---

## Summary Table

| Phase | Deliverable | Test gate |
|-------|-------------|-----------|
| 1 | docker-compose + schema + Flask skeleton | `GET /health` returns 200 |
| 2 | Order ingestion (POST/GET) | CRUD operations work |
| 3 | State machine + Celery pipeline | Order flows placed→delivered |
| 4 | Flaky simulators | Simulators return realistic errors |
| 5 | Retry + dead-letter | Failed orders land in `failed` state |
| 6 | Live dashboard (SSE + React) | UI updates without refresh |
| 7 | Prometheus + Grafana | Grafana shows live metrics |
| 8 | Load generator + burst mode | Dinner rush visible on dashboard |
| 9 | Hardening under adversarial conditions | All correctness properties hold |
