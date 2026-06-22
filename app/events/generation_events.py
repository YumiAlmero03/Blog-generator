from __future__ import annotations

import json
import queue
import time
from threading import Lock

from generation_retry_policy import cancel_generation_token, clear_generation_cancel


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


def publish_generation_draft(token: str = "", html: str = "", message: str = "") -> None:
    cleaned_token = (token or "").strip()
    cleaned_html = (html or "").strip()
    if not cleaned_token or not cleaned_html:
        return
    payload = {"draft_html": cleaned_html}
    cleaned_message = (message or "").strip()
    if cleaned_message:
        payload["message"] = cleaned_message
    publish_generation_event(cleaned_token, payload)


def cancel_generation(token: str = "") -> None:
    cleaned_token = (token or "").strip()
    if not cleaned_token:
        return
    cancel_generation_token(cleaned_token)
    publish_generation_event(cleaned_token, {"cancelled": True, "message": "Skipping current generation..."})


def is_generation_cancelled(token: str = "") -> bool:
    cleaned_token = (token or "").strip()
    if not cleaned_token:
        return False
    with _LOCK:
        return bool(_STATUSES.get(cleaned_token, {}).get("cancelled"))


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

    try:
        from app.services.background_job_service import update_background_job_from_generation_event

        update_background_job_from_generation_event(cleaned_token, event_payload)
    except Exception:
        pass


def get_generation_status(token: str = "") -> dict:
    cleaned_token = (token or "").strip()
    if not cleaned_token:
        return {"message": ""}
    _cleanup_old_statuses()
    with _LOCK:
        status = _STATUSES.get(cleaned_token, {})
        return {
            "message": status.get("message", ""),
            "prompt": status.get("prompt", ""),
            "draft_html": status.get("draft_html", ""),
            "cancelled": bool(status.get("cancelled")),
        }


def subscribe_generation_events(token: str = "") -> tuple[str, queue.Queue, dict]:
    cleaned_token = (token or "").strip()
    subscriber: queue.Queue = queue.Queue(maxsize=20)
    with _LOCK:
        _SUBSCRIBERS.setdefault(cleaned_token, set()).add(subscriber)
        current_status = _STATUSES.get(cleaned_token, {})
    return cleaned_token, subscriber, {
        "message": current_status.get("message", "Connected to generation updates."),
        "prompt": current_status.get("prompt", ""),
        "draft_html": current_status.get("draft_html", ""),
        "cancelled": bool(current_status.get("cancelled")),
    }


def unsubscribe_generation_events(token: str = "", subscriber: queue.Queue | None = None) -> None:
    cleaned_token = (token or "").strip()
    if not cleaned_token or subscriber is None:
        return
    with _LOCK:
        subscribers = _SUBSCRIBERS.get(cleaned_token)
        if subscribers:
            subscribers.discard(subscriber)
            if not subscribers:
                _SUBSCRIBERS.pop(cleaned_token, None)


def clear_generation_status(token: str = "") -> None:
    cleaned_token = (token or "").strip()
    if not cleaned_token:
        return
    clear_generation_cancel(cleaned_token)
    publish_generation_status(cleaned_token, "Generation complete.")
    with _LOCK:
        _STATUSES.pop(cleaned_token, None)


def stream_generation_events(token: str = ""):
    cleaned_token, subscriber, current_status = subscribe_generation_events(token)

    try:
        yield _format_event(current_status)
        while True:
            try:
                payload = subscriber.get(timeout=_HEARTBEAT_SECONDS)
                yield _format_event(payload)
            except queue.Empty:
                yield ": keep-alive\n\n"
    finally:
        unsubscribe_generation_events(cleaned_token, subscriber)


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
