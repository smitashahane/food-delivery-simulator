.PHONY: up down logs restart scale rush ps clean reset reload loadgen test

# Fail fast with a clear message if .env is missing
check-env:
	@test -f .env || (echo "ERROR: .env file not found. Run: cp .env.example .env" && exit 1)

up: check-env
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

restart:
	docker compose restart $(svc)

# Scale workers: make scale n=4
scale:
	docker compose up -d --scale worker=$(n)

# Trigger a dinner rush via the API: make rush burst=50 duration=60
rush:
	curl -s -X POST http://localhost:5000/api/chaos/loadgen/burst \
	  -H "Content-Type: application/json" \
	  -d '{"burst_rps":$(or $(burst),50),"duration":$(or $(duration),60)}'

ps:
	docker compose ps

# Restart all containers to pick up config changes — keeps existing data
reload:
	docker compose up -d --remove-orphans

# Run backend tests (no running containers needed)
test:
	docker compose exec api python -m pytest tests/ -v

# Start the load generator (auto-places orders at RATE/sec)
loadgen: check-env
	docker compose --profile loadgen up -d loadgen

# Wipe DB + Redis and restart cleanly — use before a demo
reset: check-env
	docker compose --profile loadgen stop worker loadgen api
	docker compose exec postgres psql -U fooddelivery -d fooddelivery -c "TRUNCATE order_events, orders RESTART IDENTITY CASCADE;"
	docker compose exec redis redis-cli FLUSHDB
	docker compose up -d --remove-orphans

# Destroy everything including volumes
clean:
	docker compose down -v --remove-orphans
