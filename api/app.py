import logging
import os

from flask import Flask, jsonify

from config import Config
from database import init_db, remove_session
from events import init_redis


def create_app() -> Flask:
    logging.basicConfig(
        level=logging.INFO,
        format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
    )

    app = Flask(__name__)
    app.config.from_object(Config)

    init_db(app.config["DATABASE_URL"])
    init_redis(app.config["REDIS_URL"])

    # Tear down DB session after each request
    @app.teardown_appcontext
    def shutdown_session(exc):
        remove_session()

    # Register blueprints
    from routes.orders import orders_bp
    from routes.stream import stream_bp
    from routes.metrics import metrics_bp

    app.register_blueprint(orders_bp)
    app.register_blueprint(stream_bp)
    app.register_blueprint(metrics_bp)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    return app
