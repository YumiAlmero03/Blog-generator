from __future__ import annotations

import json
import os
import queue
from threading import Lock, Thread
from urllib.parse import urlparse

from websockets.exceptions import ConnectionClosed
from websockets.sync.server import serve

from app.events.generation_events import subscribe_generation_events, unsubscribe_generation_events
from logger import logger


_LOCK = Lock()
_STARTED = False


def start_websocket_status_server() -> None:
    if not _enabled():
        return
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True

    thread = Thread(target=_serve_forever, name="generation-websocket-status", daemon=True)
    thread.start()


def websocket_status_port() -> int:
    raw_port = os.getenv("GENERATION_WEBSOCKET_PORT", "").strip()
    if raw_port:
        try:
            return max(1, min(65535, int(raw_port)))
        except ValueError:
            logger.warning("Invalid GENERATION_WEBSOCKET_PORT value %r. Using default.", raw_port)
    try:
        return max(1, min(65535, int(os.getenv("APP_PORT", "3444")) + 1))
    except ValueError:
        return 3445


def _serve_forever() -> None:
    host = os.getenv("GENERATION_WEBSOCKET_HOST", os.getenv("APP_HOST", "127.0.0.1")).strip() or "127.0.0.1"
    port = websocket_status_port()
    try:
        with serve(_handle_connection, host, port) as server:
            logger.info("Generation WebSocket status server started on ws://%s:%d", host, port)
            server.serve_forever()
    except OSError:
        logger.exception("Generation WebSocket status server could not start on %s:%d", host, port)
    except Exception:
        logger.exception("Generation WebSocket status server stopped unexpectedly")


def _handle_connection(connection) -> None:
    token = _token_from_connection(connection)
    subscriber = None
    cleaned_token = ""
    try:
        if not token:
            raw_message = connection.recv(timeout=10)
            token = _token_from_message(raw_message)
        if not token:
            connection.send(json.dumps({"error": "Missing generation token."}))
            return
        cleaned_token, subscriber, current_status = subscribe_generation_events(token)
        connection.send(json.dumps(current_status))
        while True:
            try:
                payload = subscriber.get(timeout=20)
                connection.send(json.dumps(payload))
            except queue.Empty:
                connection.send(json.dumps({"type": "keep-alive"}))
    except ConnectionClosed:
        return
    except Exception:
        logger.exception("Generation WebSocket connection failed")
    finally:
        unsubscribe_generation_events(cleaned_token, subscriber)


def _token_from_connection(connection) -> str:
    request = getattr(connection, "request", None)
    path = getattr(request, "path", "") if request else ""
    if not path:
        return ""
    parsed = urlparse(path)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 3 and parts[0] == "events" and parts[1] == "generation":
        return parts[2].strip()
    return ""


def _token_from_message(raw_message) -> str:
    try:
        data = json.loads(raw_message or "{}")
    except (TypeError, ValueError):
        return ""
    return str(data.get("token", "")).strip()


def _enabled() -> bool:
    return os.getenv("GENERATION_WEBSOCKET_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
