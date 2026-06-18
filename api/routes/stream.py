import logging
import time

from flask import Blueprint, Response

from events import get_redis, CHANNEL

logger = logging.getLogger(__name__)
stream_bp = Blueprint("stream", __name__)


@stream_bp.get("/stream")
def stream():
    """SSE endpoint — emits an event for every order state change."""
    def event_generator():
        pubsub = get_redis().pubsub()
        pubsub.subscribe(CHANNEL)
        try:
            while True:
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                if message and message["type"] == "message":
                    yield f"data: {message['data']}\n\n"
                else:
                    # Heartbeat keeps the connection alive through proxies / load balancers
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            pass
        finally:
            try:
                pubsub.unsubscribe(CHANNEL)
                pubsub.close()
            except Exception:
                pass

    return Response(
        event_generator(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )
