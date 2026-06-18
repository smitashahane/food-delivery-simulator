"""
Load generator stub — full burst-mode implementation in Phase 8.
Phase 1: just verifies the service starts and can reach the API.
"""
import asyncio
import os
import random
import signal
import time
import uuid

import aiohttp

TARGET_URL  = os.getenv("TARGET_URL",  "http://api:5000")
RATE        = float(os.getenv("RATE",        "5"))
BURST_RPS   = float(os.getenv("BURST_RPS",  "50"))
BURST_DURATION = float(os.getenv("BURST_DURATION", "60"))
BURST_DELAY    = float(os.getenv("BURST_DELAY",    "30"))

RESTAURANTS = [f"rest-{i:02d}" for i in range(1, 11)]
CUSTOMERS   = [f"cust-{i:04d}" for i in range(1, 101)]
MENU_ITEMS  = ["Burger", "Pizza", "Sushi", "Pasta", "Salad", "Tacos", "Ramen", "Curry"]

sent = 0
failed = 0
_stop = False


def _make_order():
    items = random.sample(MENU_ITEMS, random.randint(1, 4))
    order_items = [{"name": i, "quantity": random.randint(1, 3), "price": round(random.uniform(5, 25), 2)} for i in items]
    total = round(sum(i["price"] * i["quantity"] for i in order_items), 2)
    return {
        "customer_id": random.choice(CUSTOMERS),
        "restaurant_id": random.choice(RESTAURANTS),
        "items": order_items,
        "total_amount": total,
    }


async def _send(session: aiohttp.ClientSession):
    global sent, failed
    try:
        async with session.post(f"{TARGET_URL}/orders", json=_make_order(), timeout=aiohttp.ClientTimeout(total=5)) as r:
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
        start = time.monotonic()
        last_log = start
        burst_active = False

        while not _stop:
            now = time.monotonic()
            elapsed = now - start

            # Determine current rate
            if elapsed >= BURST_DELAY and elapsed < BURST_DELAY + BURST_DURATION:
                if not burst_active:
                    print(f"[loadgen] DINNER RUSH START — {BURST_RPS} orders/sec", flush=True)
                    burst_active = True
                current_rate = BURST_RPS
            else:
                if burst_active:
                    print(f"[loadgen] Dinner rush ended — back to {RATE} orders/sec", flush=True)
                    burst_active = False
                current_rate = RATE

            # Fire a batch of tasks for this second
            interval = 1.0 / current_rate
            tasks = [asyncio.create_task(_send(session))]
            await asyncio.sleep(interval)

            # Periodic log
            if now - last_log >= 10:
                print(
                    f"[loadgen] sent={sent} failed={failed} rate={current_rate}/s"
                    f"{' [RUSH]' if burst_active else ''}",
                    flush=True,
                )
                last_log = now

    print(f"[loadgen] Final: sent={sent} failed={failed}", flush=True)


def _handle_sigterm(*_):
    global _stop
    _stop = True


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)
    print(f"[loadgen] Starting — rate={RATE}/s burst={BURST_RPS}/s after {BURST_DELAY}s for {BURST_DURATION}s", flush=True)
    asyncio.run(run())
