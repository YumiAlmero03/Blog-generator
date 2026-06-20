from __future__ import annotations

import os
import time
from threading import Lock

from logger import logger


DEFAULT_RETRY_DELAY_SECONDS = 0
DEFAULT_STRICT_ATTEMPTS = 3
DEFAULT_MAX_ATTEMPTS = 8
_CANCELLED_TOKENS: set[str] = set()
_CANCEL_LOCK = Lock()


class GenerationCancelled(ValueError):
    pass


def retry_delay_seconds() -> int:
    return _int_env("GENERATION_RETRY_DELAY_SECONDS", DEFAULT_RETRY_DELAY_SECONDS, minimum=0, maximum=60)


def strict_attempts() -> int:
    return _int_env("GENERATION_STRICT_ATTEMPTS", DEFAULT_STRICT_ATTEMPTS, minimum=1, maximum=20)


def max_generation_attempts() -> int:
    return _int_env("GENERATION_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS, minimum=1, maximum=50)


def wait_before_retry(attempt: int, progress_callback=None, reason: str = "") -> None:
    raise_if_generation_cancelled(progress_callback)
    delay = retry_delay_seconds()
    if attempt < 1 or delay <= 0:
        return
    message = f"Waiting {delay}s before retrying"
    if reason:
        message += f" after {reason}"
    message += "..."
    _publish_progress(progress_callback, message)
    time.sleep(delay)
    raise_if_generation_cancelled(progress_callback)


def can_accept_close_enough(attempt: int) -> bool:
    return attempt >= strict_attempts()


def publish_generation_draft(progress_callback, html: str, message: str = "") -> None:
    cleaned_html = (html or "").strip()
    if not progress_callback or not cleaned_html:
        return
    try:
        progress_callback(cleaned_html, kind="draft")
        if message:
            progress_callback(message)
    except TypeError:
        return
    except Exception:
        logger.exception("generation draft callback failed")


def cancel_generation_token(token: str = "") -> None:
    cleaned_token = (token or "").strip()
    if not cleaned_token:
        return
    with _CANCEL_LOCK:
        _CANCELLED_TOKENS.add(cleaned_token)


def clear_generation_cancel(token: str = "") -> None:
    cleaned_token = (token or "").strip()
    if not cleaned_token:
        return
    with _CANCEL_LOCK:
        _CANCELLED_TOKENS.discard(cleaned_token)


def is_generation_cancelled(progress_callback=None) -> bool:
    token = getattr(progress_callback, "generation_token", "")
    if not token:
        return False
    with _CANCEL_LOCK:
        return token in _CANCELLED_TOKENS


def raise_if_generation_cancelled(progress_callback=None) -> None:
    if is_generation_cancelled(progress_callback):
        raise GenerationCancelled("Generation stopped by user.")


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        return max(minimum, min(maximum, int(raw_value)))
    except ValueError:
        logger.warning("Invalid %s value %r. Using %d.", name, raw_value, default)
        return default


def _publish_progress(progress_callback, message: str) -> None:
    if not progress_callback:
        return
    try:
        progress_callback(message)
    except TypeError:
        progress_callback(message, kind="status")
    except Exception:
        logger.exception("generation retry progress callback failed")
