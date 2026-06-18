# Food Delivery Order Pipeline — Specifications

System that takes a customer order from "Place Order" through to "Delivered",
handling burst traffic, flaky downstream systems, and exactly-once processing.

## Documents

| File | Contents |
|------|----------|
| [architecture.md](architecture.md) | System design, technology choices, tradeoffs |
| [functional-requirements.md](functional-requirements.md) | What the system must do (FR1–FR10) |
| [non-functional-requirements.md](non-functional-requirements.md) | Correctness, throughput, fault tolerance (NFR1–NFR7) |
| [modules.md](modules.md) | Building blocks, folder structure, module responsibilities |
| [build-sequence.md](build-sequence.md) | Ordered phases, dependencies, test gates per phase |

## Stack

- **Backend:** Python 3.11, Flask
- **Task queue:** Celery + Redis
- **Database:** PostgreSQL
- **Frontend:** React (Vite)
- **Observability:** Prometheus + Grafana + structured JSON logs
- **Runtime:** docker-compose (single machine)

## Quick Start (once built)

```bash
docker compose up          # start everything
docker compose up --scale worker=4   # scale workers
```

Load generator controls:
```bash
RATE=5 docker compose up loadgen              # 5 orders/sec steady
RATE=5 BURST_RPS=50 BURST_DURATION=60 docker compose up loadgen  # dinner rush
```

## Ports

| Service | Port |
|---------|------|
| React dashboard | 8080 |
| Flask API | 5000 |
| Flower (Celery monitor) | 5555 |
| Grafana | 3000 |
| Prometheus | 9090 |
| Restaurant simulator | 5001 |
| Courier simulator | 5002 |
