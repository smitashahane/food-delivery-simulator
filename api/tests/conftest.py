"""
Pytest fixtures — in-memory SQLite DB, no Redis, no Celery.
Tests cover the state machine and HTTP layer only.
"""
import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL",    "redis://localhost:6379/0")

# Stub out Celery task enqueueing so tests don't need a broker
import unittest.mock as mock
import celery_app  # noqa: F401 — must import before app to patch
celery_patcher = mock.patch("celery_app.celery.send_task")
celery_patcher.start()


@pytest.fixture(scope="session")
def app():
    from app import create_app
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_db(app):
    """Wipe all orders between tests."""
    with app.app_context():
        from database import get_session
        from models import Order, OrderEvent
        s = get_session()
        s.query(OrderEvent).delete()
        s.query(Order).delete()
        s.commit()
