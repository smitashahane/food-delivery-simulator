"""
Restaurant simulator with realistic chaos.

Default behaviour:
  - Latency:      1–8s per call
  - Failure rate: 20% random 500/503
  - Rate limit:   5% chance of 429 with Retry-After: 10
  - Preparation:  food takes 5–15s to become ready after /prepare is called

Runtime controls (no restart needed):
  POST /admin/set-failure-rate  {"rate": 0.0–1.0}
  POST /admin/set-latency       {"min_s": 1, "max_s": 8}
  POST /admin/set-blackout      {"enabled": true|false}
  GET  /admin/config            returns current settings
"""
import time
import threading
import random
import logging

from flask import Flask, jsonify, request

from chaos import SimulatorError, RateLimitError, random_latency, maybe_fail, maybe_rate_limit

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Runtime-configurable state (protected by a lock for thread safety) ────────
_lock = threading.Lock()
_config = {
    "failure_rate":    0.20,
    "rate_limit_rate": 0.05,
    "latency_min":     1.0,
    "latency_max":     8.0,
    "blackout":        False,
}

# order_id → unix timestamp when food will be ready
_preparation_times: dict[str, float] = {}


def _get_config():
    with _lock:
        return dict(_config)


def _apply_chaos():
    """Apply blackout → latency → failure → rate-limit in that order."""
    cfg = _get_config()
    if cfg["blackout"]:
        raise SimulatorError(503, "Restaurant system is down (blackout mode)")
    random_latency(cfg["latency_min"], cfg["latency_max"])
    maybe_fail(cfg["failure_rate"])
    maybe_rate_limit(cfg["rate_limit_rate"])


def _error_response(exc):
    if isinstance(exc, RateLimitError):
        return jsonify({"error": "rate limited"}), 429, {"Retry-After": str(exc.retry_after)}
    if isinstance(exc, SimulatorError):
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"error": str(exc)}), 500


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    cfg = _get_config()
    return jsonify({"status": "ok", "service": "restaurant", "config": cfg})


# ── Pipeline endpoints ─────────────────────────────────────────────────────────

@app.post("/confirm")
def confirm():
    """Restaurant acknowledges the order."""
    order_id = (request.json or {}).get("order_id", "unknown")
    logger.info("restaurant /confirm order_id=%s", order_id)
    try:
        _apply_chaos()
    except (SimulatorError, RateLimitError) as exc:
        logger.warning("restaurant /confirm FAILED order_id=%s", order_id)
        return _error_response(exc)
    return jsonify({"order_id": order_id, "status": "confirmed"})


@app.post("/prepare")
def prepare():
    """Restaurant starts preparing the food. Records when it will be ready."""
    order_id = (request.json or {}).get("order_id", "unknown")
    logger.info("restaurant /prepare order_id=%s", order_id)
    try:
        _apply_chaos()
    except (SimulatorError, RateLimitError) as exc:
        logger.warning("restaurant /prepare FAILED order_id=%s", order_id)
        return _error_response(exc)

    # Food takes 5–15 seconds to be ready from now
    ready_at = time.time() + random.uniform(5, 15)
    with _lock:
        _preparation_times[order_id] = ready_at

    return jsonify({"order_id": order_id, "status": "preparing"})


@app.get("/status/<order_id>")
def status(order_id):
    """Poll whether food is ready for pickup."""
    cfg = _get_config()
    if cfg["blackout"]:
        return jsonify({"error": "Restaurant system is down"}), 503

    # Light latency on status polls (don't apply full chaos — just simulate network)
    random_latency(0.2, 0.8)

    with _lock:
        ready_at = _preparation_times.get(order_id)

    ready = ready_at is not None and time.time() >= ready_at
    return jsonify({"order_id": order_id, "ready": ready})


# ── Admin / chaos controls ─────────────────────────────────────────────────────

@app.post("/admin/set-failure-rate")
def set_failure_rate():
    rate = float((request.json or {}).get("rate", 0.2))
    rate = max(0.0, min(1.0, rate))
    with _lock:
        _config["failure_rate"] = rate
    logger.info("restaurant failure_rate set to %.2f", rate)
    return jsonify({"failure_rate": rate})


@app.post("/admin/set-latency")
def set_latency():
    data = request.json or {}
    min_s = float(data.get("min_s", 1.0))
    max_s = float(data.get("max_s", 8.0))
    with _lock:
        _config["latency_min"] = min_s
        _config["latency_max"] = max_s
    logger.info("restaurant latency set to %.1f–%.1fs", min_s, max_s)
    return jsonify({"latency_min": min_s, "latency_max": max_s})


@app.post("/admin/set-blackout")
def set_blackout():
    enabled = bool((request.json or {}).get("enabled", False))
    with _lock:
        _config["blackout"] = enabled
    logger.info("restaurant blackout=%s", enabled)
    return jsonify({"blackout": enabled})


@app.get("/admin/config")
def get_config():
    return jsonify(_get_config())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, threaded=True)
