from __future__ import annotations

import json
import queue
import time
from threading import Lock


_STATUSES: dict[str, dict] = {}
_SUBSCRIBERS: dict[str, set[queue.Queue]] = {}
_LOCK = Lock()
_MAX_AGE_SECONDS = 60 * 60
_HEARTBEAT_SECONDS = 15


def publish_generation_status(token: str = "", message: str = "") -> None:
    cleaned_token = (token or "").strip()
    cleaned_message = (message or "").strip()
    if not cleaned_token or not cleaned_message:
        return
    publish_generation_event(cleaned_token, {"message": cleaned_message})


def publish_generation_prompt(token: str = "", prompt: str = "") -> None:
    cleaned_token = (token or "").strip()
    cleaned_prompt = (prompt or "").strip()
    if not cleaned_token or not cleaned_prompt:
        return
    publish_generation_event(cleaned_token, {"prompt": cleaned_prompt})


def publish_generation_event(token: str = "", payload: dict | None = None) -> None:
    cleaned_token = (token or "").strip()
    cleaned_payload = payload or {}
    if not cleaned_token or not cleaned_payload:
        return

    _cleanup_old_statuses()
    event_payload = {**cleaned_payload, "updated_at": time.time()}
    with _LOCK:
        previous = _STATUSES.get(cleaned_token, {})
        _STATUSES[cleaned_token] = {**previous, **event_payload}
        subscribers = list(_SUBSCRIBERS.get(cleaned_token, set()))

    for subscriber in subscribers:
        try:
            subscriber.put_nowait(event_payload)
        except queue.Full:
            pass


def get_generation_status(token: str = "") -> dict:
    cleaned_token = (token or "").strip()
    if not cleaned_token:
        return {"message": ""}
    _cleanup_old_statuses()
    with _LOCK:
        status = _STATUSES.get(cleaned_token, {})
        return {"message": status.get("message", ""), "prompt": status.get("prompt", "")}


def clear_generation_status(token: str = "") -> None:
    cleaned_token = (token or "").strip()
    if not cleaned_token:
        return
    publish_generation_status(cleaned_token, "Generation complete.")
    with _LOCK:
        _STATUSES.pop(cleaned_token, None)


def stream_generation_events(token: str = ""):
    cleaned_token = (token or "").strip()
    subscriber: queue.Queue = queue.Queue(maxsize=20)

    with _LOCK:
        _SUBSCRIBERS.setdefault(cleaned_token, set()).add(subscriber)
        current_status = _STATUSES.get(cleaned_token, {})

    try:
        yield _format_event(
            {
                "message": current_status.get("message", "Connected to generation updates."),
                "prompt": current_status.get("prompt", ""),
            }
        )
        while True:
            try:
                payload = subscriber.get(timeout=_HEARTBEAT_SECONDS)
                yield _format_event(payload)
            except queue.Empty:
                yield ": keep-alive\n\n"
    finally:
        with _LOCK:
            subscribers = _SUBSCRIBERS.get(cleaned_token)
            if subscribers:
                subscribers.discard(subscriber)
                if not subscribers:
                    _SUBSCRIBERS.pop(cleaned_token, None)


def _format_event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _cleanup_old_statuses() -> None:
    cutoff = time.time() - _MAX_AGE_SECONDS
    with _LOCK:
        expired_tokens = [
            token for token, status in _STATUSES.items() if status.get("updated_at", 0) < cutoff
        ]
        for token in expired_tokens:
            _STATUSES.pop(token, None)
