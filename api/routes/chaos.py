"""
Chaos control proxy.

The React dashboard can't reach simulators directly (internal Docker network),
so this blueprint proxies chaos commands from the UI through the Flask API.
Also handles dinner-rush burst trigger via a Redis key that loadgen polls.
"""
import logging
import os
import time

import requests
from flask import Blueprint, jsonify, request

from events import get_redis

logger = logging.getLogger(__name__)
chaos_bp = Blueprint("chaos", __name__)

RESTAURANT_URL = os.getenv("RESTAURANT_URL", "http://restaurant:5001")
COURIER_URL    = os.getenv("COURIER_URL",    "http://courier:5002")

BURST_RPS      = float(os.getenv("BURST_RPS",      "50"))
BURST_DURATION = float(os.getenv("BURST_DURATION", "60"))

# Redis key that loadgen watches for burst commands
LOADGEN_BURST_KEY = "loadgen:burst_until"


# ── Config read ────────────────────────────────────────────────────────────────

@chaos_bp.get("/api/chaos/config")
def get_config():
    """Fetch current chaos config from both simulators."""
    results = {}
    for name, base_url in [("restaurant", RESTAURANT_URL), ("courier", COURIER_URL)]:
        try:
            r = requests.get(f"{base_url}/admin/config", timeout=3)
            results[name] = r.json()
        except Exception as exc:
            results[name] = {"error": str(exc)}
    return jsonify(results)


# ── Restaurant controls ────────────────────────────────────────────────────────

@chaos_bp.post("/api/chaos/restaurant/failure-rate")
def restaurant_failure_rate():
    rate = float((request.json or {}).get("rate", 0.2))
    return _proxy_post(RESTAURANT_URL, "/admin/set-failure-rate", {"rate": rate})


@chaos_bp.post("/api/chaos/restaurant/latency")
def restaurant_latency():
    data = request.json or {}
    return _proxy_post(RESTAURANT_URL, "/admin/set-latency", {
        "min_s": float(data.get("min_s", 1)),
        "max_s": float(data.get("max_s", 8)),
    })


@chaos_bp.post("/api/chaos/restaurant/blackout")
def restaurant_blackout():
    enabled = bool((request.json or {}).get("enabled", False))
    return _proxy_post(RESTAURANT_URL, "/admin/set-blackout", {"enabled": enabled})


# ── Courier controls ───────────────────────────────────────────────────────────

@chaos_bp.post("/api/chaos/courier/failure-rate")
def courier_failure_rate():
    rate = float((request.json or {}).get("rate", 0.15))
    return _proxy_post(COURIER_URL, "/admin/set-failure-rate", {"rate": rate})


@chaos_bp.post("/api/chaos/courier/latency")
def courier_latency():
    data = request.json or {}
    return _proxy_post(COURIER_URL, "/admin/set-latency", {
        "min_s": float(data.get("min_s", 1)),
        "max_s": float(data.get("max_s", 3)),
    })


@chaos_bp.post("/api/chaos/courier/blackout")
def courier_blackout():
    enabled = bool((request.json or {}).get("enabled", False))
    return _proxy_post(COURIER_URL, "/admin/set-blackout", {"enabled": enabled})


@chaos_bp.post("/api/chaos/courier/auto-blackout")
def courier_auto_blackout():
    enabled = bool((request.json or {}).get("enabled", True))
    return _proxy_post(COURIER_URL, "/admin/set-auto-blackout", {"enabled": enabled})


# ── Dinner rush trigger ────────────────────────────────────────────────────────

@chaos_bp.post("/api/chaos/loadgen/burst")
def trigger_burst():
    """
    Writes a Redis key with an expiry timestamp.
    The loadgen service polls this key and switches to BURST_RPS while it exists.
    """
    duration = float((request.json or {}).get("duration", BURST_DURATION))
    burst_rps = float((request.json or {}).get("burst_rps", BURST_RPS))
    burst_until = time.time() + duration

    try:
        redis = get_redis()
        redis.set(LOADGEN_BURST_KEY, str(burst_until), ex=int(duration) + 5)
        redis.set("loadgen:burst_rps", str(burst_rps), ex=int(duration) + 5)
        logger.info("Dinner rush triggered: %.0f orders/s for %.0fs", burst_rps, duration)
        return jsonify({
            "status": "burst triggered",
            "burst_rps": burst_rps,
            "duration_s": duration,
            "burst_until": burst_until,
        })
    except Exception as exc:
        logger.exception("Failed to trigger burst")
        return jsonify({"error": str(exc)}), 500


@chaos_bp.post("/api/chaos/loadgen/stop")
def stop_burst():
    """Immediately cancel a dinner rush by deleting the Redis burst keys."""
    try:
        redis = get_redis()
        redis.delete(LOADGEN_BURST_KEY)
        redis.delete("loadgen:burst_rps")
        logger.info("Dinner rush stopped by user")
        return jsonify({"status": "burst stopped"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@chaos_bp.get("/api/chaos/loadgen/status")
def loadgen_status():
    """Returns whether a burst is currently active."""
    try:
        redis = get_redis()
        burst_until = redis.get(LOADGEN_BURST_KEY)
        if burst_until and float(burst_until) > time.time():
            remaining = float(burst_until) - time.time()
            burst_rps = float(redis.get("loadgen:burst_rps") or BURST_RPS)
            return jsonify({"burst_active": True, "remaining_s": round(remaining), "burst_rps": burst_rps})
        return jsonify({"burst_active": False})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Helper ─────────────────────────────────────────────────────────────────────

def _proxy_post(base_url: str, path: str, payload: dict):
    try:
        r = requests.post(f"{base_url}{path}", json=payload, timeout=5)
        return jsonify(r.json()), r.status_code
    except requests.RequestException as exc:
        logger.error("Chaos proxy failed: %s%s — %s", base_url, path, exc)
        return jsonify({"error": f"Simulator unreachable: {exc}"}), 502
