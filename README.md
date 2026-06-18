# Food Delivery Order Pipeline Simulator

A full-stack system that simulates a food-delivery order pipeline — from "Place Order" through to "Delivered" — under real-world conditions: burst traffic, flaky downstream systems, and exactly-once processing guarantees.

## What it demonstrates

- **High-volume ingestion** — place thousands of orders per second; the queue absorbs bursts without dropping anything
- **Order lifecycle** — `placed → confirmed → preparing → ready → out_for_delivery → delivered`
- **Resilience** — restaurant and courier simulators fail randomly; the pipeline retries with exponential backoff and recovers automatically
- **Exactly-once processing** — concurrent workers never double-process an order; crashes never lose one
- **Live dashboard** — React UI updates in real time via Server-Sent Events; no manual refresh needed
- **Dinner rush mode** — one command spikes traffic 10x to simulate peak load

## Prerequisites

| Tool | Version |
|------|---------|
| [Docker Desktop](https://www.docker.com/products/docker-desktop) | 24+ |

That's it. Python, Node, Postgres, Redis — everything runs inside containers.

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

# 4. Wait ~60 seconds for all services to become healthy
docker compose ps
```

All services should show `healthy` or `running`. Open the UIs:

| UI | URL | Credentials |
|----|-----|-------------|
| **Dashboard** (live pipeline view) | http://localhost:8080 | — |
| **Flower** (Celery task monitor) | http://localhost:5555 | — |
| **Grafana** (ops metrics) | http://localhost:3000 | admin / admin |
| **Prometheus** | http://localhost:9090 | — |

## Test the API

**Place an order:**
```bash
curl -X POST http://localhost:5000/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust-001",
    "restaurant_id": "rest-001",
    "items": [{"name": "Burger", "quantity": 1, "price": 12.50}],
    "total_amount": 12.50
  }'
# → 202 {"order_id": "...", "status": "placed", "placed_at": "..."}
```

**Track it:**
```bash
curl http://localhost:5000/orders/<order_id>
```

**List all orders (with optional filters):**
```bash
curl http://localhost:5000/orders
curl "http://localhost:5000/orders?status=delivered"
curl "http://localhost:5000/orders?restaurant_id=rest-001"
```

**Live stats:**
```bash
curl http://localhost:5000/api/stats
```

## Trigger a dinner rush

```bash
# Spike to 50 orders/sec for 60 seconds
make rush

# Custom rate
make rush rate=10 burst=80 duration=90
```

Watch the dashboard at http://localhost:8080 — the "DINNER RUSH" banner lights up and order counts spike in real time.

## Scale workers

```bash
make scale n=4    # run 4 parallel Celery workers
```

## Simulate downstream failures

Force the restaurant simulator to always fail (watch retries and dead-lettering in action):
```bash
# Max failure rate
curl -X POST http://localhost:5001/admin/set-failure-rate \
  -H "Content-Type: application/json" \
  -d '{"rate": 1.0}'

# Restore to default
curl -X POST http://localhost:5001/admin/set-failure-rate \
  -H "Content-Type: application/json" \
  -d '{"rate": 0.2}'
```

Trigger a courier blackout:
```bash
curl -X POST http://localhost:5002/admin/set-blackout \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# Recover
curl -X POST http://localhost:5002/admin/set-blackout \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

## Common commands

```bash
make up                         # start all services
make down                       # stop all services
make logs                       # tail all logs
docker compose logs -f api      # API logs only
docker compose logs -f worker   # worker logs only
make scale n=4                  # run 4 workers
make clean                      # destroy everything including volumes (fresh start)
```

## Architecture

```
Load Generator → Flask API → PostgreSQL (source of truth)
                           → Redis (Celery broker + SSE pub/sub)
                           → Celery Workers (pipeline state machine)
                              → Restaurant Simulator (flaky)
                              → Courier Simulator (flaky)

Flask API /stream → SSE → React Dashboard
Prometheus scrapes /metrics → Grafana
```

| Service | Port | Role |
|---------|------|------|
| Flask API | 5000 | Order ingestion, queries, SSE, /metrics |
| Celery Worker | — | Pipeline processing |
| Flower | 5555 | Celery task monitor |
| PostgreSQL | 5432 | Order state store (internal) |
| Redis | 6379 | Celery broker + SSE pub/sub (internal) |
| Restaurant simulator | 5001 | Flaky restaurant API |
| Courier simulator | 5002 | Flaky courier API |
| React Dashboard | 8080 | Live business view |
| Prometheus | 9090 | Metrics collection |
| Grafana | 3000 | Ops dashboards (pre-provisioned) |

See [specs/architecture.md](specs/architecture.md) for full design rationale and technology tradeoffs.

## Project structure

```
├── api/               Flask API + Celery tasks
├── worker/            Pipeline state machine + retry logic
├── simulators/        Flaky restaurant & courier mocks
├── dashboard/         React frontend (Vite + nginx)
├── loadgen/           Traffic generator
├── infra/             Prometheus config + Grafana dashboards
├── specs/             Full system specifications and build sequence
└── docker-compose.yml
```

## Troubleshooting

**Services not becoming healthy:**
```bash
docker compose logs postgres    # check DB startup
docker compose logs api         # check for import errors
```

**Port already in use:**
```bash
docker compose down             # stop any running instances first
docker compose up -d
```

**Fresh start (wipe all data):**
```bash
make clean
docker compose up -d
```
