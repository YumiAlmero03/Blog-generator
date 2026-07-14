from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from app.services import image_tool_cleanup_scheduler, website_index_scheduler
from database import get_setting


def list_scheduled_jobs(now: datetime | None = None) -> list[dict]:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    return [
        _website_pages_discovery_job(current_time),
        _website_index_check_job(current_time),
        _image_tool_cleanup_job(current_time),
    ]


def _website_pages_discovery_job(now: datetime) -> dict:
    enabled = _env_enabled("WEBSITE_INDEX_SCHEDULER", True)
    interval_seconds = website_index_scheduler._page_discovery_interval_seconds()
    check_interval_seconds = website_index_scheduler._interval_seconds()
    last_run_raw = get_setting(website_index_scheduler.PAGE_DISCOVERY_LAST_RUN_SETTING, "").strip()
    last_run = _parse_datetime(last_run_raw)
    due = last_run is None or now - last_run >= timedelta(seconds=interval_seconds)
    next_trigger_at = now if due else last_run + timedelta(seconds=interval_seconds)
    return {
        "name": "Website Pages Daily Discovery",
        "status": "enabled" if enabled else "disabled",
        "trigger": f"Due every {_duration(interval_seconds)}; checked by Website Index scheduler every {_duration(check_interval_seconds)}.",
        "next_trigger_at": _format_datetime(next_trigger_at) if enabled else "-",
        "next_trigger_label": "Due on next scheduler loop" if enabled and due else "",
        "last_trigger_at": _format_datetime(last_run) if last_run else "Never",
        "notes": "Discovers saved website roots, adds new URLs to Website Index, and submits due not-indexed URLs to Google.",
    }


def _website_index_check_job(now: datetime) -> dict:
    enabled = _env_enabled("WEBSITE_INDEX_SCHEDULER", True)
    interval_seconds = website_index_scheduler._interval_seconds()
    initial_delay_seconds = website_index_scheduler._initial_delay_seconds()
    next_trigger_at = now + timedelta(seconds=interval_seconds)
    return {
        "name": "Website Index Scheduled Check",
        "status": "enabled" if enabled else "disabled",
        "trigger": f"Runs every {_duration(interval_seconds)} after an initial {_duration(initial_delay_seconds)} app-start delay.",
        "next_trigger_at": _format_datetime(next_trigger_at) if enabled else "-",
        "next_trigger_label": "Approximate; loop timing resets when the app restarts." if enabled else "",
        "last_trigger_at": "Tracked in Background Jobs history",
        "notes": "Checks Google indexing status for due URLs when Google credentials are configured.",
    }


def _image_tool_cleanup_job(now: datetime) -> dict:
    enabled = _env_enabled("IMAGE_TOOL_CLEANUP_SCHEDULER", True)
    interval_seconds = image_tool_cleanup_scheduler._interval_seconds()
    initial_delay_seconds = image_tool_cleanup_scheduler._initial_delay_seconds()
    max_age_days = image_tool_cleanup_scheduler._max_age_days()
    next_trigger_at = now + timedelta(seconds=interval_seconds)
    return {
        "name": "Image Tool Cleanup",
        "status": "enabled" if enabled else "disabled",
        "trigger": f"Runs every {_duration(interval_seconds)} after an initial {_duration(initial_delay_seconds)} app-start delay.",
        "next_trigger_at": _format_datetime(next_trigger_at) if enabled else "-",
        "next_trigger_label": "Approximate; loop timing resets when the app restarts." if enabled else "",
        "last_trigger_at": "Not persisted",
        "notes": f"Deletes Image Tools uploads older than {max_age_days} day(s).",
    }


def _env_enabled(key: str, default: bool) -> bool:
    raw_value = os.getenv(key, "true" if default else "false").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_datetime(value: datetime | None) -> str:
    if not value:
        return "-"
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _duration(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    if seconds % 86400 == 0 and seconds >= 86400:
        days = seconds // 86400
        return f"{days} day" + ("" if days == 1 else "s")
    if seconds % 3600 == 0 and seconds >= 3600:
        hours = seconds // 3600
        return f"{hours} hour" + ("" if hours == 1 else "s")
    if seconds % 60 == 0 and seconds >= 60:
        minutes = seconds // 60
        return f"{minutes} minute" + ("" if minutes == 1 else "s")
    return f"{seconds} second" + ("" if seconds == 1 else "s")
