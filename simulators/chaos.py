"""Shared chaos utilities for simulator services."""
import random
import time


def random_latency(min_s: float, max_s: float):
    time.sleep(random.uniform(min_s, max_s))


def maybe_fail(failure_rate: float):
    """Raise SimulatorError at the given rate (0.0–1.0)."""
    if random.random() < failure_rate:
        status = random.choice([500, 503])
        raise SimulatorError(status, "Simulated downstream failure")


def maybe_rate_limit(rate: float, retry_after: int = 10):
    if random.random() < rate:
        raise RateLimitError(retry_after)


class SimulatorError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message


class RateLimitError(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
