"""
SSE endpoint — streams order state-change events to the browser.

The generator runs an inner reconnect loop so a Redis blip doesn't kill
every open dashboard tab.  A heartbeat comment is sent every 15 s so
proxies and load balancers don't close idle connections.
"""
import logging
import time

from flask import Blueprint, Response

from events import get_redis, CHANNEL

logger = logging.getLogger(__name__)
stream_bp = Blueprint("stream", __name__)


@stream_bp.get("/stream")
def stream():
    def event_generator():
        while True:
            pubsub = None
            try:
                pubsub = get_redis().pubsub()
                pubsub.subscribe(CHANNEL)

                while True:
                    message = pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=15
                    )
                    if message and message["type"] == "message":
                        yield f"data: {message['data']}\n\n"
                    else:
                        # Heartbeat — keeps connection alive through nginx/proxies
                        yield ": heartbeat\n\n"

            except GeneratorExit:
                # Client disconnected — clean exit
                return
            except Exception as exc:
                logger.warning("SSE stream error, reconnecting in 1s: %s", exc)
                yield ": reconnecting\n\n"
                time.sleep(1)
            finally:
                if pubsub:
                    try:
                        pubsub.unsubscribe(CHANNEL)
                        pubsub.close()
                    except Exception:
                        pass

    return Response(
        event_generator(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering":"no",   # disable nginx buffering for SSE
            "Connection":       "keep-alive",
        },
    )
