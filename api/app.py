import logging
import os

from flask import Flask, jsonify

from config import Config
from database import init_db, remove_session
from events import init_redis


def _seed_status_gauge() -> None:
    """Warm the orders_by_status gauge from current DB counts so Grafana isn't blank on restart."""
    try:
        from sqlalchemy import func
        from database import get_session
        from models import Order, OrderStatus
        from metrics_registry import orders_by_status
        session = get_session()
        rows = session.query(Order.status, func.count(Order.id)).group_by(Order.status).all()
        counts = {s.value: 0 for s in OrderStatus}
        for status, cnt in rows:
            counts[status.value] = cnt
        for status_val, cnt in counts.items():
            orders_by_status.labels(status=status_val).set(cnt)
    except Exception:
        pass  # not fatal — gauge will populate as orders flow through


def create_app() -> Flask:
    logging.basicConfig(
        level=logging.INFO,
        format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
    )

    app = Flask(__name__)
    app.config.from_object(Config)

    init_db(app.config["DATABASE_URL"])
    init_redis(app.config["REDIS_URL"])

    # Seed orders_by_status gauge from current DB state
    _seed_status_gauge()

    # Tear down DB session after each request
    @app.teardown_appcontext
    def shutdown_session(exc):
        remove_session()

    # Register blueprints
    from routes.orders import orders_bp
    from routes.stream import stream_bp
    from routes.metrics import metrics_bp
    from routes.chaos import chaos_bp

    app.register_blueprint(orders_bp)
    app.register_blueprint(stream_bp)
    app.register_blueprint(metrics_bp)
    app.register_blueprint(chaos_bp)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    return app
