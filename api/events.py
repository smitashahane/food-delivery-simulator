import json
import logging
import redis as redis_lib

logger = logging.getLogger(__name__)

_redis_client = None
CHANNEL = "order_events"


def init_redis(redis_url: str):
    global _redis_client
    _redis_client = redis_lib.from_url(redis_url, decode_responses=True)


def get_redis():
    if _redis_client is None:
        raise RuntimeError("Redis not initialised — call init_redis() first")
    return _redis_client


def publish_state_change(order_id: str, from_status, to_status, timestamp: str):
    payload = json.dumps({
        "order_id": order_id,
        "from": from_status.value if hasattr(from_status, "value") else from_status,
        "to": to_status.value if hasattr(to_status, "value") else to_status,
        "ts": timestamp,
    })
    try:
        get_redis().publish(CHANNEL, payload)
    except Exception:
        logger.exception("Failed to publish state change event for order %s", order_id)
