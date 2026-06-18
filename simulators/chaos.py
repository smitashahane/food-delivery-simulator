"""
Shared chaos utilities used by both simulator services.
Each simulator has its own process so globals are independent.
"""
import random
import time
import logging

logger = logging.getLogger(__name__)


class SimulatorError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message


class RateLimitError(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after


def random_latency(min_s: float, max_s: float):
    """Block for a random duration to simulate slow downstream systems."""
    time.sleep(random.uniform(min_s, max_s))


def maybe_fail(failure_rate: float):
    """Raise SimulatorError at the given probability (0.0–1.0)."""
    if random.random() < failure_rate:
        code = random.choice([500, 503])
        raise SimulatorError(code, f"Simulated {code} — downstream failure")


def maybe_rate_limit(rate: float, retry_after: int = 10):
    """Raise RateLimitError at the given probability."""
    if random.random() < rate:
        raise RateLimitError(retry_after)
