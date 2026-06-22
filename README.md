# Food Delivery Order Pipeline Simulator

A full-stack system that simulates a food-delivery order pipeline — from "Place Order" through to "Delivered" — under real-world conditions: burst traffic, flaky downstream systems, and exactly-once processing guarantees.

## What it demonstrates

- **Order lifecycle** — `placed → confirmed → preparing → ready → out_for_delivery → delivered`
- **Resilience** — restaurant and courier simulators fail randomly; the pipeline retries with exponential backoff and recovers automatically
- **Exactly-once processing** — concurrent workers never double-process an order; crashes never lose one
- **Live dashboard** — React UI updates in real time via Server-Sent Events; no manual refresh needed
- **Chaos engineering** — control failure rates, latency, and blackouts from the UI at runtime
- **Dinner rush mode** — spike traffic to simulate peak load, cancel it early if needed
- **Observability** — Prometheus metrics + pre-provisioned Grafana dashboard

## Prerequisites

| Tool | Version |
|------|---------|
| [Docker Desktop](https://www.docker.com/products/docker-desktop) | 24+ |

Everything else (Python, Node, Postgres, Redis) runs inside containers.

```bash
docker --version        # should be 24+
docker compose version  # should be v2+
```

## Quick start

```bash
# 1. Clone
git clone https://github.com/smitashahane/food-delivery-simulator.git
cd food-delivery-simulator

# 2. Configure (defaults work out of the box)
cp .env.example .env

# 3. Start everything
docker compose up -d

# 4. Wait ~30 seconds for services to become healthy
docker compose ps
```

Open the UIs:

| UI | URL | Credentials |
|----|-----|-------------|
| **Dashboard** (live pipeline view) | http://localhost:8080 | — |
| **Grafana** (ops metrics) | http://localhost:3000 | admin / admin |
| **Prometheus** | http://localhost:9090 | — |

## Placing orders

Use the **API Explorer** tab in the dashboard at http://localhost:8080 — select a restaurant, add items, and click Place Order. The order ID and audit trail appear in real time.

Or via curl:

```bash
curl -X POST http://localhost:5000/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust-001",
    "restaurant_id": "rest-01",
    "items": [{"name": "Burger", "quantity": 1, "price": 12.50}],
    "total_amount": 12.50
  }'
# → 202 {"order_id": "...", "status": "placed", "placed_at": "..."}
```

Track an order:
```bash
curl http://localhost:5000/orders/<order_id>
```

List orders with optional filters:
```bash
curl http://localhost:5000/orders
curl "http://localhost:5000/orders?status=delivered"
curl "http://localhost:5000/orders?restaurant_id=rest-01"
```

## Simulating chaos

All chaos controls are available in the **Chaos Controls** section of the dashboard — no curl commands needed:

- **Failure rate** — percentage of calls that return 500/503
- **Max latency** — how slow each downstream call can be
- **Blackout** — total outage toggle (all calls fail immediately)
- **Courier auto-blackout** — random 30s outages every ~10 minutes (toggle on/off)

To watch retries and dead-lettering in action, push the restaurant failure rate to 100% and place a few orders.

## Dinner rush (load generator)

The load generator is opt-in — it doesn't run by default. Start it when you want automated traffic:

```bash
make loadgen    # starts at 2 orders/sec steady rate
```

Then trigger a burst from the **Chaos Controls → Dinner Rush** panel in the dashboard, or via:

```bash
make rush                          # 50 orders/sec for 60s
make rush burst=80 duration=90     # custom rate and duration
```

Stop a rush early using the **Stop Rush** button in the dashboard.

## Common commands

```bash
make up            # start all services
make down          # stop all services
make reload        # restart to pick up config changes (keeps data)
make reset         # wipe DB + Redis and restart clean (use before a demo)
make loadgen       # start the load generator (opt-in)
make rush          # trigger a dinner rush burst via the API
make scale n=4     # run 4 parallel Celery workers
make logs          # tail all logs
make clean         # destroy everything including volumes
```

## Architecture

```
[Orders via UI / curl / loadgen]
        ↓
   Flask API  ──→  PostgreSQL  (source of truth)
        ↓          Redis       (Celery broker + SSE pub/sub + metrics counters)
   Celery Worker
        ├──→  Restaurant Simulator  (flaky — configurable chaos)
        └──→  Courier Simulator     (flaky — configurable chaos)

Flask API /stream ──→ SSE ──→ React Dashboard
Prometheus scrapes /metrics ──→ Grafana
```

| Service | Port | Role |
|---------|------|------|
| Flask API | 5000 | Order ingestion, queries, SSE, /metrics |
| Celery Worker | — | Pipeline processing |
| PostgreSQL | 5432 | Order state store (internal) |
| Redis | 6379 | Celery broker + SSE pub/sub (internal) |
| Restaurant simulator | 5001 | Flaky restaurant API |
| Courier simulator | 5002 | Flaky courier API |
| React Dashboard | 8080 | Live operations view |
| Prometheus | 9090 | Metrics collection |
| Grafana | 3000 | Ops dashboards (pre-provisioned) |

## Order states

```
placed → confirmed → preparing → ready → out_for_delivery → delivered
                                                          ↘
                                     (any stage) → failed → dead_lettered
```

- **failed** — pipeline exhausted all 5 retries
- **dead_lettered** — confirmed unrecoverable; needs manual intervention in a real system (refund, alert, replay)

## Project structure

```
├── api/               Flask API, Celery tasks, pipeline state machine
├── simulators/        Flaky restaurant & courier simulators
├── dashboard/         React frontend (Vite + nginx)
├── loadgen/           Traffic generator (opt-in)
├── infra/             Prometheus config + Grafana dashboard JSON
├── specs/             System specifications
└── docker-compose.yml
```

## Troubleshooting

**Services not becoming healthy:**
```bash
docker compose logs postgres
docker compose logs api
```

**Port already in use:**
```bash
docker compose down
docker compose up -d
```

**Wipe everything and start fresh:**
```bash
make clean
docker compose up -d
```
