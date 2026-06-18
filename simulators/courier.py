"""
Courier simulator with realistic chaos.

Default behaviour:
  - Latency:      1–3s per call
  - Failure rate: 15% random 500/503
  - Delivery:     courier takes 10–30s to deliver after /assign
  - Auto-blackout: randomly goes dark for 30s every ~10 minutes

Runtime controls (no restart needed):
  POST /admin/set-failure-rate  {"rate": 0.0–1.0}
  POST /admin/set-latency       {"min_s": 1, "max_s": 3}
  POST /admin/set-blackout      {"enabled": true|false}
  GET  /admin/config            returns current settings
"""
import time
import threading
import random
import logging

from flask import Flask, jsonify, request

from chaos import SimulatorError, RateLimitError, random_latency, maybe_fail

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Runtime-configurable state ────────────────────────────────────────────────
_lock = threading.Lock()
_config = {
    "failure_rate":      0.15,
    "latency_min":       1.0,
    "latency_max":       3.0,
    "blackout":          False,
    "auto_blackout":     True,   # random 30s outages every ~10 min
}

# order_id → unix timestamp when delivery will complete
_delivery_times: dict[str, float] = {}

# Auto-blackout state
_blackout_until: float = 0.0


def _get_config():
    with _lock:
        return dict(_config)


def _is_blacked_out() -> bool:
    cfg = _get_config()
    if cfg["blackout"]:
        return True
    # Auto-blackout: random outage every ~10 minutes, lasting 30s
    global _blackout_until
    with _lock:
        now = time.time()
        if now < _blackout_until:
            return True
        # ~1% chance per request of triggering a 30s blackout
        if cfg["auto_blackout"] and random.random() < 0.01:
            _blackout_until = now + 30
            logger.warning("courier AUTO-BLACKOUT triggered — down for 30s")
            return True
    return False


def _apply_chaos():
    if _is_blacked_out():
        raise SimulatorError(503, "Courier system is down (blackout)")
    cfg = _get_config()
    random_latency(cfg["latency_min"], cfg["latency_max"])
    maybe_fail(cfg["failure_rate"])


def _error_response(exc):
    if isinstance(exc, RateLimitError):
        return jsonify({"error": "rate limited"}), 429, {"Retry-After": "10"}
    if isinstance(exc, SimulatorError):
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"error": str(exc)}), 500


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    cfg = _get_config()
    blacked_out = _is_blacked_out()
    return jsonify({"status": "ok", "service": "courier", "config": cfg, "blacked_out": blacked_out})


# ── Pipeline endpoints ─────────────────────────────────────────────────────────

@app.post("/assign")
def assign():
    """Assign a courier to pick up and deliver the order."""
    order_id = (request.json or {}).get("order_id", "unknown")
    logger.info("courier /assign order_id=%s", order_id)
    try:
        _apply_chaos()
    except (SimulatorError, RateLimitError) as exc:
        logger.warning("courier /assign FAILED order_id=%s", order_id)
        return _error_response(exc)

    # Courier delivers in 10–30 seconds from now
    delivers_at = time.time() + random.uniform(10, 30)
    with _lock:
        _delivery_times[order_id] = delivers_at

    return jsonify({"order_id": order_id, "status": "assigned"})


@app.get("/status/<order_id>")
def status(order_id):
    """Poll whether delivery is complete."""
    if _is_blacked_out():
        return jsonify({"error": "Courier system is down"}), 503

    random_latency(0.2, 1.0)

    with _lock:
        delivers_at = _delivery_times.get(order_id)

    delivered = delivers_at is not None and time.time() >= delivers_at
    return jsonify({"order_id": order_id, "delivered": delivered})


# ── Admin / chaos controls ─────────────────────────────────────────────────────

@app.post("/admin/set-failure-rate")
def set_failure_rate():
    rate = float((request.json or {}).get("rate", 0.15))
    rate = max(0.0, min(1.0, rate))
    with _lock:
        _config["failure_rate"] = rate
    logger.info("courier failure_rate set to %.2f", rate)
    return jsonify({"failure_rate": rate})


@app.post("/admin/set-latency")
def set_latency():
    data = request.json or {}
    min_s = float(data.get("min_s", 1.0))
    max_s = float(data.get("max_s", 3.0))
    with _lock:
        _config["latency_min"] = min_s
        _config["latency_max"] = max_s
    logger.info("courier latency set to %.1f–%.1fs", min_s, max_s)
    return jsonify({"latency_min": min_s, "latency_max": max_s})


@app.post("/admin/set-blackout")
def set_blackout():
    enabled = bool((request.json or {}).get("enabled", False))
    with _lock:
        _config["blackout"] = enabled
        if not enabled:
            global _blackout_until
            _blackout_until = 0.0   # clear auto-blackout too
    logger.info("courier blackout=%s", enabled)
    return jsonify({"blackout": enabled})


@app.post("/admin/set-auto-blackout")
def set_auto_blackout():
    enabled = bool((request.json or {}).get("enabled", True))
    with _lock:
        _config["auto_blackout"] = enabled
    return jsonify({"auto_blackout": enabled})


@app.get("/admin/config")
def get_config():
    return jsonify(_get_config())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, threaded=True)
