.PHONY: up down logs restart scale rush ps clean

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

# Destroy everything including volumes
clean:
	docker compose down -v --remove-orphans
