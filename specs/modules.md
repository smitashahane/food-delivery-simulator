# Modules & Building Blocks

## Folder Structure

```
food-delivery/
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py                  # Flask app factory + blueprint registration
│   ├── config.py               # Config from environment variables
│   ├── models.py               # SQLAlchemy models: Order, OrderEvent
│   ├── database.py             # DB session, engine, init_db()
│   ├── tasks.py                # Celery app + all pipeline task definitions
│   ├── events.py               # Redis pub/sub publisher (publish_state_change)
│   └── routes/
│       ├── orders.py           # POST /orders, GET /orders, GET /orders/<id>
│       ├── stream.py           # GET /stream (SSE endpoint)
│       └── metrics.py          # GET /metrics, GET /api/stats
│
├── worker/
│   ├── Dockerfile              # Same base image as api; imports tasks.py
│   ├── pipeline.py             # State machine: VALID_TRANSITIONS, transition()
│   ├── retry.py                # Backoff policy, jitter, dead-letter logic
│   └── celery_app.py           # Celery instance config (imported by tasks.py)
│
├── simulators/
│   ├── Dockerfile              # Shared by both simulators
│   ├── restaurant.py           # Flask app: /confirm /prepare /status /admin/*
│   ├── courier.py              # Flask app: /assign /status /admin/*
│   └── chaos.py                # Shared: random_latency(), random_failure(), blackout_check()
│
├── dashboard/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── api.js              # fetch wrappers for /api/stats, /orders
│       ├── hooks/
│       │   └── useSSE.js       # EventSource wrapper with auto-reconnect
│       └── components/
│           ├── StatusCounts.jsx     # Cards: count per order status
│           ├── OrderFeed.jsx        # Live scrolling list of recent orders
│           ├── ThroughputChart.jsx  # Orders/min line chart (last 5 min)
│           └── SystemHealth.jsx     # Restaurant / courier health indicators
│
├── loadgen/
│   ├── Dockerfile
│   └── generator.py            # Configurable rate, burst mode, random order data
│
├── infra/
│   ├── prometheus.yml          # Scrape config
│   └── grafana/
│       ├── provisioning/
│       │   ├── datasources/datasource.yml
│       │   └── dashboards/dashboard.yml
│       └── dashboards/
│           └── pipeline.json   # Pre-built ops dashboard
│
├── docker-compose.yml
├── .env.example
└── Makefile                    # Convenience targets: up, down, logs, rush, scale
```

---

## Module Responsibilities

### `api/app.py` — Flask App Factory
- Creates Flask app instance
- Registers blueprints: `orders`, `stream`, `metrics`
- Initialises DB connection and runs `init_db()` on startup
- Registers Prometheus metrics on app startup

### `api/models.py` — Data Models
```python
class Order:
    id: UUID (PK)
    customer_id: str
    restaurant_id: str
    items: JSON
    total_amount: Decimal
    status: Enum(OrderStatus)
    placed_at: datetime
    updated_at: datetime

class OrderEvent:
    id: UUID (PK)
    order_id: UUID (FK → orders.id)
    from_status: Enum(OrderStatus) | None
    to_status: Enum(OrderStatus)
    worker_id: str | None
    reason: str | None
    created_at: datetime
```

Indexes:
- `orders.status` — for filtered queries and gauge metrics
- `orders.placed_at` — for sorted pagination
- `order_events.order_id` — for history lookups

### `api/tasks.py` — Celery Tasks
One task per pipeline stage. Each task:
1. Acquires row lock via `pipeline.transition(order_id, expected_from, to, ...)`
2. Calls downstream simulator
3. On success: commits transition, publishes SSE event, chains next task
4. On failure: raises exception → Celery retry via `retry.py` policy

```
confirm_order(order_id)       placed → confirmed
prepare_order(order_id)       confirmed → preparing → ready
assign_courier(order_id)      ready → out_for_delivery
complete_delivery(order_id)   out_for_delivery → delivered
```

### `worker/pipeline.py` — State Machine
```python
VALID_TRANSITIONS = {
    "placed":           ["confirmed", "cancelled", "failed"],
    "confirmed":        ["preparing", "cancelled", "failed"],
    "preparing":        ["ready", "cancelled", "failed"],
    "ready":            ["out_for_delivery", "cancelled", "failed"],
    "out_for_delivery": ["delivered", "failed"],
}

def transition(order_id, from_status, to_status, worker_id, reason=None):
    # SELECT FOR UPDATE, validate, UPDATE + INSERT event, COMMIT
```

### `worker/retry.py` — Retry & Dead-Letter Policy
```python
BACKOFF_DELAYS = [2, 4, 8, 16, 32]  # seconds, with ±20% jitter applied
MAX_RETRIES = 5

def backoff_delay(attempt: int) -> float:
    base = BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS) - 1)]
    return base * random.uniform(0.8, 1.2)

def handle_max_retries(order_id, stage, last_error):
    # transition order → failed
    # enqueue to dlq Celery queue
    # publish failure SSE event
```

### `api/events.py` — SSE Publisher
```python
def publish_state_change(order_id, from_status, to_status, timestamp):
    payload = json.dumps({
        "order_id": order_id,
        "from": from_status,
        "to": to_status,
        "ts": timestamp
    })
    redis_client.publish("order_events", payload)
```

### `api/routes/stream.py` — SSE Endpoint
```python
@stream_bp.route("/stream")
def stream():
    def event_generator():
        pubsub = redis_client.pubsub()
        pubsub.subscribe("order_events")
        for message in pubsub.listen():
            if message["type"] == "message":
                yield f"data: {message['data']}\n\n"
    return Response(event_generator(), mimetype="text/event-stream")
```

### `simulators/chaos.py` — Shared Chaos Logic
```python
def random_latency(min_s, max_s):
    time.sleep(random.uniform(min_s, max_s))

def maybe_fail(failure_rate):
    if random.random() < failure_rate:
        raise SimulatorError(random.choice([500, 503]))

def maybe_rate_limit(rate_limit_rate, retry_after=10):
    if random.random() < rate_limit_rate:
        raise RateLimitError(retry_after=retry_after)
```

### `loadgen/generator.py` — Load Generator
```python
# Reads from env: RATE, BURST_RPS, BURST_DURATION, BURST_DELAY, TARGET_URL
# Steady mode: send RATE orders/sec using asyncio + aiohttp
# Burst mode: after BURST_DELAY seconds, ramp to BURST_RPS for BURST_DURATION seconds
# Logs: every 10s print current RPS, total sent, total failed
```

### `dashboard/hooks/useSSE.js` — SSE React Hook
```javascript
function useSSE(url) {
    const [events, setEvents] = useState([]);
    useEffect(() => {
        const es = new EventSource(url);
        es.onmessage = (e) => setEvents(prev => [JSON.parse(e.data), ...prev].slice(0, 100));
        es.onerror = () => { es.close(); /* reconnect after 2s */ };
        return () => es.close();
    }, [url]);
    return events;
}
```

---

## Inter-Module Dependencies

```
routes/orders.py  →  models.py, tasks.py, database.py
routes/stream.py  →  events.py (Redis client)
routes/metrics.py →  models.py, database.py

tasks.py  →  pipeline.py, retry.py, events.py
             restaurant client (HTTP)
             courier client (HTTP)

pipeline.py  →  models.py, database.py

dashboard components → useSSE.js (for live updates)
                     → api.js (for initial load + stats polling)
```

No circular dependencies. `models.py` and `database.py` are leaves with no internal imports.
