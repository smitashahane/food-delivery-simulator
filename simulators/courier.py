"""
Courier simulator — stub for Phase 1 (healthcheck only).
Full chaos behaviour implemented in Phase 4.
"""
from flask import Flask, jsonify

app = Flask(__name__)

_failure_rate = 0.15
_blackout = False


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "courier"})


@app.post("/assign")
def assign():
    return jsonify({"status": "assigned"}), 200


@app.get("/status/<order_id>")
def status(order_id):
    return jsonify({"order_id": order_id, "delivered": True}), 200


@app.post("/admin/set-failure-rate")
def set_failure_rate():
    from flask import request
    global _failure_rate
    _failure_rate = float(request.json.get("rate", _failure_rate))
    return jsonify({"failure_rate": _failure_rate})


@app.post("/admin/set-blackout")
def set_blackout():
    from flask import request
    global _blackout
    _blackout = bool(request.json.get("enabled", False))
    return jsonify({"blackout": _blackout})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
