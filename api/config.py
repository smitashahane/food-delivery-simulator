import os


class Config:
    DATABASE_URL = os.environ["DATABASE_URL"]
    REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
    RESTAURANT_URL = os.getenv("RESTAURANT_URL", "http://restaurant:5001")
    COURIER_URL = os.getenv("COURIER_URL", "http://courier:5002")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
