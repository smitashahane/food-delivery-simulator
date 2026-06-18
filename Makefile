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

# Trigger a dinner rush: make rush rate=5 burst=50 duration=60
rush:
	RATE=$(or $(rate),5) BURST_RPS=$(or $(burst),50) BURST_DURATION=$(or $(duration),60) BURST_DELAY=5 \
	docker compose --profile loadgen up loadgen

ps:
	docker compose ps

# Destroy everything including volumes
clean:
	docker compose down -v --remove-orphans
