from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from pathlib import Path

from app.services.image_service import ALLOWED_IMAGE_EXTENSIONS, IMAGE_TOOL_DIR
from logger import logger


DEFAULT_MAX_AGE_DAYS = 15
DEFAULT_INTERVAL_SECONDS = 60 * 60 * 24
_STARTED = False
_LOCK = threading.Lock()


def start_image_tool_cleanup_scheduler() -> None:
    if os.getenv("IMAGE_TOOL_CLEANUP_SCHEDULER", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return

    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True

    thread = threading.Thread(target=_scheduler_loop, name="image-tool-cleanup-scheduler", daemon=True)
    thread.start()
    logger.info("Image Tool cleanup scheduler started.")


def cleanup_old_image_tool_files(
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    image_tool_dir: Path = IMAGE_TOOL_DIR,
) -> int:
    cutoff = datetime.now().timestamp() - (max(1, int(max_age_days)) * 24 * 60 * 60)
    deleted_count = 0
    image_tool_dir.mkdir(parents=True, exist_ok=True)

    for path in image_tool_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
            continue
        try:
            if path.stat().st_mtime <= cutoff:
                path.unlink()
                deleted_count += 1
        except FileNotFoundError:
            continue
        except Exception:
            logger.exception("Could not delete old image tool file: %s", path)

    if deleted_count:
        logger.info("Image Tool cleanup deleted %d old file(s).", deleted_count)
    return deleted_count


def _scheduler_loop() -> None:
    time.sleep(_initial_delay_seconds())
    while True:
        try:
            cleanup_old_image_tool_files(max_age_days=_max_age_days())
        except Exception:
            logger.exception("Image Tool cleanup scheduler failed.")
        time.sleep(_interval_seconds())


def _max_age_days() -> int:
    raw_value = os.getenv("IMAGE_TOOL_CLEANUP_MAX_AGE_DAYS", str(DEFAULT_MAX_AGE_DAYS)).strip()
    try:
        return max(1, int(raw_value))
    except ValueError:
        return DEFAULT_MAX_AGE_DAYS


def _interval_seconds() -> int:
    raw_value = os.getenv("IMAGE_TOOL_CLEANUP_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS)).strip()
    try:
        return max(60, int(raw_value))
    except ValueError:
        return DEFAULT_INTERVAL_SECONDS


def _initial_delay_seconds() -> int:
    raw_value = os.getenv("IMAGE_TOOL_CLEANUP_INITIAL_DELAY_SECONDS", "30").strip()
    try:
        return max(0, int(raw_value))
    except ValueError:
        return 30
