"""
Load generator — sends randomised orders to the Flask API.

Modes:
  Steady   : RATE orders/sec continuously
  Burst    : triggered by Redis key (set via dashboard Dinner Rush button)
             or automatically after BURST_DELAY seconds if BURST_RPS is set

Redis key: loadgen:burst_until  (unix timestamp)
           loadgen:burst_rps    (target RPS during burst)
"""
import asyncio
import os
import random
import signal
import time

import aiohttp
import redis as redis_lib

TARGET_URL     = os.getenv("TARGET_URL",     "http://api:5000")
RATE           = float(os.getenv("RATE",           "0.033"))  # ~2 orders/min
BURST_RPS      = float(os.getenv("BURST_RPS",     "20"))
BURST_DURATION = float(os.getenv("BURST_DURATION","60"))
BURST_DELAY    = float(os.getenv("BURST_DELAY",   "0"))   # 0 = no auto burst
REDIS_URL      = os.getenv("REDIS_URL", "redis://redis:6379/0")

RESTAURANTS = [f"rest-{i:02d}" for i in range(1, 11)]
CUSTOMERS   = [f"cust-{i:04d}" for i in range(1, 101)]
MENU_ITEMS  = ["Burger", "Pizza", "Sushi", "Pasta", "Salad", "Tacos", "Ramen", "Curry", "Wrap", "Steak"]

sent   = 0
failed = 0
_stop  = False

# Redis client for reading burst commands from dashboard
_redis = None


def _get_redis():
    global _redis
    if _redis is None:
        try:
            _redis = redis_lib.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
        except Exception:
            pass
    return _redis


def _check_redis_burst() -> tuple[bool, float]:
    """Returns (burst_active, burst_rps)."""
    r = _get_redis()
    if not r:
        return False, BURST_RPS
    try:
        burst_until = r.get("loadgen:burst_until")
        if burst_until and float(burst_until) > time.time():
            burst_rps = float(r.get("loadgen:burst_rps") or BURST_RPS)
            return True, burst_rps
    except Exception:
        pass
    return False, BURST_RPS


def _make_order() -> dict:
    items = random.sample(MENU_ITEMS, random.randint(1, 4))
    order_items = [
        {"name": i, "quantity": random.randint(1, 3), "price": round(random.uniform(5, 25), 2)}
        for i in items
    ]
    total = round(sum(i["price"] * i["quantity"] for i in order_items), 2)
    return {
        "customer_id":   random.choice(CUSTOMERS),
        "restaurant_id": random.choice(RESTAURANTS),
        "items":         order_items,
        "total_amount":  total,
    }


async def _send(session: aiohttp.ClientSession):
    global sent, failed
    try:
        async with session.post(
            f"{TARGET_URL}/orders",
            json=_make_order(),
            timeout=aiohttp.ClientTimeout(total=5),
        ) as r:
            if r.status == 202:
                sent += 1
            else:
                failed += 1
    except Exception:
        failed += 1


async def run():
    global _stop
    connector = aiohttp.TCPConnector(limit=200)
    async with aiohttp.ClientSession(connector=connector) as session:
        start      = time.monotonic()
        last_log   = start
        burst_active_prev = False

        while not _stop:
            now     = time.monotonic()
            elapsed = now - start

            # Check Redis for dashboard-triggered burst first
            redis_burst, redis_burst_rps = _check_redis_burst()

            # Auto-burst from env vars (if configured)
            auto_burst = (
                BURST_DELAY > 0
                and elapsed >= BURST_DELAY
                and elapsed < BURST_DELAY + BURST_DURATION
            )

            if redis_burst:
                burst_active = True
                current_rate = redis_burst_rps
            elif auto_burst:
                burst_active = True
                current_rate = BURST_RPS
            else:
                burst_active = False
                current_rate = RATE

            if burst_active and not burst_active_prev:
                print(f"[loadgen] 🚀 DINNER RUSH — {current_rate:.0f} orders/sec", flush=True)
            elif not burst_active and burst_active_prev:
                print(f"[loadgen] Rush ended — back to {RATE:.0f} orders/sec", flush=True)
            burst_active_prev = burst_active

            # Fire one order per interval slot
            interval = 1.0 / max(current_rate, 0.1)
            asyncio.create_task(_send(session))
            await asyncio.sleep(interval)

            if now - last_log >= 10:
                print(
                    f"[loadgen] sent={sent} failed={failed} "
                    f"rate={current_rate:.0f}/s{' [RUSH]' if burst_active else ''}",
                    flush=True,
                )
                last_log = now

    print(f"[loadgen] Final: sent={sent} failed={failed}", flush=True)


def _handle_stop(*_):
    global _stop
    _stop = True


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT,  _handle_stop)
    print(
        f"[loadgen] Starting — steady={RATE}/s  burst={BURST_RPS}/s  "
        f"burst_delay={BURST_DELAY}s  duration={BURST_DURATION}s",
        flush=True,
    )
    asyncio.run(run())
