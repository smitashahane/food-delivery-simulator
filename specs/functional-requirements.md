# Functional Requirements

## FR1 — Order Ingestion

- Accept `POST /orders` with: `customer_id`, `restaurant_id`, `items` (list), `total_amount`
- Generate a UUID `order_id` and `placed_at` timestamp on receipt
- Return `409 Conflict` if an order with the same `order_id` already exists
- Return `202 Accepted` with the `order_id` immediately — do not wait for processing
- Enqueue the order into the Celery pipeline synchronously before returning 202
- Validate required fields; return `400 Bad Request` on missing/malformed input

**Request shape:**
```json
{
  "customer_id": "cust-abc",
  "restaurant_id": "rest-xyz",
  "items": [
    { "name": "Burger", "quantity": 1, "price": 12.50 }
  ],
  "total_amount": 12.50
}
```

**Response (202):**
```json
{
  "order_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "placed",
  "placed_at": "2024-01-15T18:30:00Z"
}
```

---

## FR2 — Order Lifecycle State Machine

Valid states:
- `placed` — order received by the platform
- `confirmed` — restaurant has accepted the order
- `preparing` — restaurant is preparing the food
- `ready` — food is ready for pickup
- `out_for_delivery` — courier has picked up and is en route
- `delivered` — order handed to customer (terminal)
- `cancelled` — order cancelled before delivery (terminal)
- `failed` — pipeline exhausted retries (terminal)
- `dead_lettered` — moved to DLQ after failure (terminal)

Valid transitions (no skipping allowed):
```
placed          → confirmed, cancelled, failed
confirmed       → preparing, cancelled, failed
preparing       → ready, cancelled, failed
ready           → out_for_delivery, cancelled, failed
out_for_delivery → delivered, failed
delivered       → (none — terminal)
cancelled       → dead_lettered
failed          → dead_lettered
dead_lettered   → (none — terminal)
```

- Any transition not in the above map must be rejected with a logged error
- Every transition must be recorded in `order_events` with: `from_status`, `to_status`, `worker_id`, `timestamp`, `reason` (optional)
- State change must be atomic — DB update and event log in the same transaction

---

## FR3 — Restaurant Integration

- On `placed`: POST to restaurant simulator `/confirm` with order details
  - Success → transition to `confirmed`
  - Failure → retry per policy (FR5)
- On `confirmed`: POST to restaurant simulator `/prepare`
  - Success → transition to `preparing`
- Poll or receive response when food is ready
  - Success → transition to `ready`
- The restaurant simulator is the authority on when food is ready

---

## FR4 — Courier Integration

- On `ready`: POST to courier simulator `/assign` with order and restaurant location
  - Success → transition to `out_for_delivery`
  - Failure → retry per policy (FR5)
- Poll or receive delivery confirmation from courier simulator
  - Success → transition to `delivered`

---

## FR5 — Failure Handling & Retry

- Retry any failed downstream call (5xx, network error, timeout) up to **5 times**
- Retry schedule (with ±20% jitter):

  | Attempt | Delay before retry |
  |---------|-------------------|
  | 1 → 2  | 2s |
  | 2 → 3  | 4s |
  | 3 → 4  | 8s |
  | 4 → 5  | 16s |
  | 5 → DLQ | — |

- On HTTP 429 (rate limit): read `Retry-After` header and delay accordingly
- After 5 failed attempts: set order status to `failed`, publish failure event, enqueue to dead-letter queue
- Every retry attempt must be logged with: `order_id`, `stage`, `attempt_number`, `error_reason`
- Failed orders must remain queryable via `GET /orders/{id}` — they must not be deleted

---

## FR6 — Exactly-Once Processing

- Duplicate `POST /orders` (same `order_id`) returns `409` — enforced by DB unique constraint
- Before each state transition, acquire a row-level lock (`SELECT FOR UPDATE`) on the order
- Before acting, verify the order's current status is the expected predecessor:
  - If already transitioned (e.g., from a previous retry): log and exit cleanly
  - If in an unexpected state: log error, do not proceed
- Celery task IDs keyed as `{order_id}:{stage}` prevent duplicate task submission
- `acks_late=True` on all pipeline tasks — task re-queues if worker crashes before completion

---

## FR7 — Order Queries

| Endpoint | Description |
|----------|-------------|
| `GET /orders` | Paginated list, 50 per page, sorted by `placed_at` desc |
| `GET /orders?status=failed` | Filter by status |
| `GET /orders?restaurant_id=xyz` | Filter by restaurant |
| `GET /orders/{id}` | Single order with full `order_events` audit history |
| `GET /metrics` | Prometheus-format metrics |
| `GET /api/stats` | JSON summary: counts per status, throughput, error rate (for dashboard) |
| `GET /stream` | SSE endpoint — emits events on every state transition |

---

## FR8 — Live Business Dashboard

The dashboard updates itself — no manual refresh required.

**Panels:**
1. **Status counts** — live count of orders in each state (placed, confirmed, preparing, ready, out_for_delivery, delivered, failed)
2. **Order feed** — scrolling list of most recent 50 orders with: order ID (truncated), status badge, restaurant, elapsed time in current state
3. **Throughput** — orders/minute over the last 5 minutes (line chart)
4. **System health** — indicator per downstream system (restaurant, courier): green = healthy, yellow = degraded (elevated error rate), red = down (no successful calls in last 30s)
5. **Error rate** — failed orders / total orders in last 5 minutes

Dashboard must show a "dinner rush in progress" indicator when throughput exceeds 2x the 5-minute average.

---

## FR9 — Load Generator

- Standalone service, configured entirely via environment variables
- Generates random but realistic order data (random customer, restaurant, 1–5 items)

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `TARGET_URL` | `http://api:5000` | Flask API base URL |
| `RATE` | `5` | Orders per second (steady state) |
| `BURST_RPS` | `50` | Orders per second during dinner rush |
| `BURST_DURATION` | `60` | Seconds to sustain the burst |
| `BURST_DELAY` | `30` | Seconds after start before burst begins |

- Load generator logs orders sent, success/failure counts, and current RPS every 10 seconds
- On `SIGTERM`, log a final summary and exit cleanly

---

## FR10 — Downstream Simulators

Both simulators are Flask services with configurable failure behaviour.

### Restaurant Simulator (`:5001`)

| Endpoint | Description |
|----------|-------------|
| `POST /confirm` | Confirm order — returns 200 or random failure |
| `POST /prepare` | Start preparation — returns 200 or random failure |
| `GET /status/{order_id}` | Check if food is ready |
| `POST /admin/set-failure-rate` | Runtime control for testing |
| `POST /admin/set-blackout` | Enable/disable total blackout |

**Default behaviour:**
- Mean latency: 1–8s (random per call, normally distributed)
- Random 500 error rate: 20%
- Random 429 rate-limit: 5% (Retry-After: 10)
- Blackout mode: off by default

### Courier Simulator (`:5002`)

| Endpoint | Description |
|----------|-------------|
| `POST /assign` | Assign courier — returns 200 or random failure |
| `GET /status/{order_id}` | Check delivery status |
| `POST /admin/set-failure-rate` | Runtime control for testing |
| `POST /admin/set-blackout` | Enable/disable total blackout |

**Default behaviour:**
- Mean latency: 5–20s (random per call)
- Random 500 error rate: 15%
- Occasional total blackout: 30s outage every ~10 minutes (random)
