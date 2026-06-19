from __future__ import annotations

import os
import threading
import time

from app.services.indexnow_service import inspect_google_index_status
from database import (
    get_setting,
    list_due_website_index_urls,
    mark_website_index_urls_checking,
    update_website_index_bing_yahoo_weekly_result,
    update_website_index_google_result,
)
from logger import logger


CHECK_LIMIT = 10
DEFAULT_INTERVAL_SECONDS = 60 * 60 * 24 * 7
_STARTED = False
_LOCK = threading.Lock()


def start_website_index_scheduler() -> None:
    if os.getenv("WEBSITE_INDEX_SCHEDULER", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return

    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True

    thread = threading.Thread(target=_scheduler_loop, name="website-index-scheduler", daemon=True)
    thread.start()
    logger.info("Website Index scheduler started.")


def run_website_index_weekly_batch() -> int:
    due_rows = list_due_website_index_urls()
    due_urls = [item["url"] for item in due_rows[:CHECK_LIMIT]]
    if not due_urls:
        return 0

    mark_website_index_urls_checking(due_urls)
    update_website_index_bing_yahoo_weekly_result(due_urls)

    site_url = get_setting("google_search_console_property", "")
    access_token = get_setting("google_oauth_access_token", "")
    service_account_json = get_setting("google_service_account_json", "")
    if not site_url or not (access_token or service_account_json):
        logger.info("Website Index scheduler marked %d URL(s) for Bing/Yahoo manual review; Google settings are incomplete.", len(due_urls))
        return len(due_urls)

    result = inspect_google_index_status(
        urls=due_urls,
        site_url=site_url,
        access_token=access_token,
        service_account_json=service_account_json,
    )
    for item in result.items:
        update_website_index_google_result(item)

    logger.info("Website Index scheduler checked %d URL(s).", len(due_urls))
    return len(due_urls)


def _scheduler_loop() -> None:
    interval = _interval_seconds()
    time.sleep(_initial_delay_seconds())
    while True:
        try:
            run_website_index_weekly_batch()
        except Exception:
            logger.exception("Website Index scheduler failed.")
        time.sleep(interval)


def _interval_seconds() -> int:
    raw_value = os.getenv("WEBSITE_INDEX_SCHEDULER_INTERVAL_SECONDS", "").strip()
    if not raw_value:
        return DEFAULT_INTERVAL_SECONDS
    try:
        return max(60, int(raw_value))
    except ValueError:
        return DEFAULT_INTERVAL_SECONDS


def _initial_delay_seconds() -> int:
    raw_value = os.getenv("WEBSITE_INDEX_SCHEDULER_INITIAL_DELAY_SECONDS", "30").strip()
    try:
        return max(0, int(raw_value))
    except ValueError:
        return 30
