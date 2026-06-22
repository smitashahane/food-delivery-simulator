.PHONY: up down logs restart scale rush ps clean reset reload

up:
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

# Wipe DB + Redis and restart cleanly — use before a demo
reset:
	docker compose stop worker loadgen api
	docker exec practicals-postgres-1 psql -U fooddelivery -d fooddelivery -c "TRUNCATE order_events, orders RESTART IDENTITY CASCADE;"
	docker exec practicals-redis-1 redis-cli FLUSHDB
	docker compose up -d --remove-orphans

# Destroy everything including volumes
clean:
	docker compose down -v --remove-orphans
