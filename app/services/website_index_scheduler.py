from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from app.services.website_page_discovery_service import discover_website_pages
from app.services.indexnow_service import DEFAULT_INDEXNOW_ENDPOINT, inspect_google_index_status_by_url_domain, submit_google_indexing_urls, submit_indexnow_urls
from app.services.background_job_service import start_system_background_job, update_system_background_job
from database import (
    get_setting,
    list_due_website_index_submission_urls,
    list_website_index_site_roots,
    list_due_website_index_urls,
    mark_website_index_urls_checking,
    set_setting,
    update_website_index_google_result,
    upsert_website_index_urls,
)
from logger import logger


CHECK_LIMIT = 50
DEFAULT_INTERVAL_SECONDS = 60 * 30
DEFAULT_PAGE_DISCOVERY_INTERVAL_SECONDS = 60 * 60 * 24
DEFAULT_PAGE_DISCOVERY_LIMIT = 1000
PAGE_DISCOVERY_LAST_RUN_SETTING = "website_pages_daily_discovery_last_run"
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
    started_at = time.perf_counter()
    job_id = start_system_background_job("/website-index-dashboard", "Website Index scheduled check starting...")
    try:
        logger.info("Website Index scheduler batch started.")
        phase_started_at = time.perf_counter()
        due_rows = list_due_website_index_urls()
        due_urls = [item["url"] for item in due_rows[:CHECK_LIMIT]]
        logger.info(
            "Website Index scheduler selected due URLs in %.2fs: due_total=%d batch_urls=%d limit=%d",
            time.perf_counter() - phase_started_at,
            len(due_rows),
            len(due_urls),
            CHECK_LIMIT,
        )
        if not due_urls:
            update_system_background_job(job_id, "complete", "Website Index scheduled check complete. No due URLs.", status_code=204)
            logger.info("Website Index scheduler batch complete. No due URLs. elapsed=%.2fs", time.perf_counter() - started_at)
            return 0

        access_token = get_setting("google_oauth_access_token", "")
        service_account_json = get_setting("google_service_account_json", "")
        if not (access_token or service_account_json):
            update_system_background_job(
                job_id,
                "complete",
                "Website Index scheduled check skipped. Google settings are incomplete.",
                status_code=200,
            )
            logger.info("Website Index scheduler skipped Google inspection because Google settings are incomplete. elapsed=%.2fs", time.perf_counter() - started_at)
            return 0

        update_system_background_job(job_id, "running", f"Website Index checking Google indexing for {len(due_urls)} URL(s)...")
        phase_started_at = time.perf_counter()
        mark_website_index_urls_checking(due_urls)
        logger.info("Website Index scheduler marked %d URL(s) checking in %.2fs.", len(due_urls), time.perf_counter() - phase_started_at)
        phase_started_at = time.perf_counter()
        result = inspect_google_index_status_by_url_domain(
            urls=due_urls,
            access_token=access_token,
            service_account_json=service_account_json,
        )
        for item in result.items:
            update_website_index_google_result(item)
        error_items = [item for item in result.items if getattr(item, "status", "") == "error"]
        logger.info(
            "Website Index scheduler Google inspection finished in %.2fs: inspected=%d skipped=%d errors=%d",
            time.perf_counter() - phase_started_at,
            getattr(result, "inspected_count", len(result.items)),
            len(getattr(result, "skipped", [])),
            len(error_items),
        )
        for item in error_items[:20]:
            logger.error(
                "Website Index scheduler Google inspection URL error: url=%s status_code=%s detail=%s",
                item.url,
                item.status_code,
                item.detail,
            )
        if len(error_items) > 20:
            logger.error("Website Index scheduler Google inspection had %d additional URL error(s).", len(error_items) - 20)

        logger.info("Website Index scheduler checked %d URL(s) in %.2fs.", len(due_urls), time.perf_counter() - started_at)
        update_system_background_job(
            job_id,
            "complete",
            f"Website Index checked Google indexing for {len(due_urls)} URL(s).",
            status_code=200,
        )
        return len(due_urls)
    except Exception as exc:
        logger.exception("Website Index scheduler batch failed after %.2fs.", time.perf_counter() - started_at)
        update_system_background_job(job_id, "failed", "Website Index scheduler failed.", error=str(exc), status_code=500)
        raise


def run_website_pages_daily_discovery() -> dict:
    started_at = time.perf_counter()
    job_id = start_system_background_job("/website-pages", "Website Pages daily discovery starting...")
    site_roots = list_website_index_site_roots()
    limit = _page_discovery_limit()
    scanned_count = 0
    discovered_count = 0
    saved_count = 0
    error_count = 0
    google_submitted_count = 0
    google_submit_error_count = 0

    try:
        logger.info(
            "Website Pages daily discovery started: domains=%d limit=%d",
            len(site_roots),
            limit,
        )
        if not site_roots:
            set_setting(PAGE_DISCOVERY_LAST_RUN_SETTING, _utc_now_text())
            update_system_background_job(job_id, "complete", "Website Pages daily discovery complete. No saved websites.", status_code=204)
            logger.info("Website Pages daily discovery complete. No saved websites. elapsed=%.2fs", time.perf_counter() - started_at)
            return {"domains": 0, "discovered": 0, "saved": 0, "errors": 0}

        for index, site in enumerate(site_roots, start=1):
            domain = site["domain"]
            base_url = site["base_url"]
            update_system_background_job(
                job_id,
                "running",
                f"Discovering pages for {domain} ({index}/{len(site_roots)})...",
            )
            try:
                result = discover_website_pages(base_url, limit=limit)
                scanned_count += 1
                discovered_count += len(result.pages)
                inserted_count = upsert_website_index_urls(getattr(result, "page_items", None) or result.pages)
                saved_count += inserted_count
                if result.errors:
                    logger.warning(
                        "Website Pages daily discovery completed with sitemap errors: domain=%s errors=%s",
                        domain,
                        "; ".join(result.errors[:5]),
                    )
                logger.info(
                    "Website Pages daily discovery domain finished: domain=%s discovered=%d saved=%d",
                    domain,
                    len(result.pages),
                    inserted_count,
                )
            except Exception as exc:
                error_count += 1
                logger.exception("Website Pages daily discovery domain failed: domain=%s base_url=%s", domain, base_url)

        set_setting(PAGE_DISCOVERY_LAST_RUN_SETTING, _utc_now_text())
        google_submit_result = _submit_not_indexed_urls_to_google()
        google_submitted_count = google_submit_result["submitted"]
        google_submit_error_count = google_submit_result["errors"]
        message = (
            f"Website Pages daily discovery complete. Scanned {scanned_count} website(s), "
            f"saved {saved_count} new URL(s), submitted {google_submitted_count} not-indexed URL(s) to Google."
        )
        update_system_background_job(job_id, "complete", message, status_code=200 if error_count == 0 and google_submit_error_count == 0 else 207)
        logger.info(
            "Website Pages daily discovery finished in %.2fs: domains=%d scanned=%d discovered=%d saved=%d errors=%d google_submitted=%d google_submit_errors=%d",
            time.perf_counter() - started_at,
            len(site_roots),
            scanned_count,
            discovered_count,
            saved_count,
            error_count,
            google_submitted_count,
            google_submit_error_count,
        )
        return {
            "domains": len(site_roots),
            "scanned": scanned_count,
            "discovered": discovered_count,
            "saved": saved_count,
            "errors": error_count,
            "google_submitted": google_submitted_count,
            "google_submit_errors": google_submit_error_count,
        }
    except Exception as exc:
        logger.exception("Website Pages daily discovery failed after %.2fs.", time.perf_counter() - started_at)
        update_system_background_job(job_id, "failed", "Website Pages daily discovery failed.", error=str(exc), status_code=500)
        raise


def _submit_not_indexed_urls_to_google() -> dict:
    access_token = get_setting("google_oauth_access_token", "")
    service_account_json = get_setting("google_service_account_json", "")
    if not (access_token or service_account_json):
        logger.info("Website Pages daily discovery skipped Google submit because Google settings are incomplete.")
        return {"submitted": 0, "skipped": 0, "errors": 0}

    due_rows = list_due_website_index_submission_urls()
    urls = [item["url"] for item in due_rows[:CHECK_LIMIT]]
    if not urls:
        logger.info("Website Pages daily discovery found no not-indexed URLs due for Google submit.")
        return {"submitted": 0, "skipped": 0, "errors": 0}

    phase_started_at = time.perf_counter()
    result = submit_google_indexing_urls(
        urls=urls,
        access_token=access_token,
        service_account_json=service_account_json,
        notification_type="URL_UPDATED",
    )
    error_count = len([item for item in result.items if item.status == "error"])
    logger.info(
        "Website Pages daily discovery Google submit finished in %.2fs: due_total=%d submitted=%d skipped=%d errors=%d",
        time.perf_counter() - phase_started_at,
        len(due_rows),
        result.submitted_count,
        len(result.skipped),
        error_count,
    )
    return {"submitted": result.submitted_count, "skipped": len(result.skipped), "errors": error_count}


def trigger_website_index_batch() -> None:
    thread = threading.Thread(
        target=_triggered_batch_runner,
        name="website-index-manual-trigger",
        daemon=True,
    )
    thread.start()
    logger.info("Website Index manual batch trigger queued.")


def submit_website_index_urls_to_indexnow(
    urls: list[str],
    key: str | None = None,
    key_location: str | None = None,
    endpoint: str | None = None,
) -> dict:
    key = (get_setting("indexnow_key", "") if key is None else key).strip()
    if not key:
        logger.info("Website Index skipped IndexNow submit because indexnow_key is empty.")
        return {"hosts": 0, "submitted": 0, "skipped": len(urls), "errors": ["IndexNow key is missing."]}

    endpoint = (get_setting("indexnow_endpoint", DEFAULT_INDEXNOW_ENDPOINT) if endpoint is None else endpoint).strip() or DEFAULT_INDEXNOW_ENDPOINT
    key_location = (get_setting("indexnow_key_location", "") if key_location is None else key_location).strip()
    grouped_urls = _group_urls_by_host(urls)
    submitted_count = 0
    skipped_count = len(urls) - sum(len(host_urls) for host_urls in grouped_urls.values())
    errors: list[str] = []

    for host, host_urls in grouped_urls.items():
        try:
            result = submit_indexnow_urls(
                urls=host_urls,
                key=key,
                host=host,
                key_location=_key_location_for_host(key_location, host),
                endpoint=endpoint,
            )
        except Exception as exc:
            errors.append(f"{host}: {exc}")
            logger.warning("Website Index IndexNow submit failed: host=%s urls=%d error=%s", host, len(host_urls), exc)
            continue

        submitted_count += result.submitted_count
        skipped_count += len(result.skipped)
        for batch in result.batches:
            if batch.status == "error":
                errors.append(f"{host}: HTTP {batch.status_code or 'n/a'} - {batch.detail}")
                logger.warning(
                    "Website Index IndexNow batch failed: host=%s batch=%d status_code=%s detail=%s",
                    host,
                    batch.batch_number,
                    batch.status_code,
                    batch.detail,
                )
        logger.info(
            "Website Index IndexNow host submitted: host=%s submitted=%d skipped=%d batches=%d ok=%s",
            result.host,
            result.submitted_count,
            len(result.skipped),
            len(result.batches),
            result.ok,
        )

    return {
        "hosts": len(grouped_urls),
        "submitted": submitted_count,
        "skipped": skipped_count,
        "errors": errors,
    }


def _group_urls_by_host(urls: list[str]) -> dict[str, list[str]]:
    grouped_urls: dict[str, list[str]] = {}
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        host = parsed.netloc.lower()
        grouped_urls.setdefault(host, []).append(url)
    return grouped_urls


def _key_location_for_host(key_location: str, host: str) -> str:
    if not key_location:
        return ""
    parsed = urlparse(key_location)
    if not parsed.netloc:
        return key_location
    if parsed.netloc.lower() == host.lower():
        return key_location
    return ""


def _scheduler_loop() -> None:
    interval = _interval_seconds()
    time.sleep(_initial_delay_seconds())
    while True:
        try:
            if _page_discovery_is_due():
                run_website_pages_daily_discovery()
            run_website_index_weekly_batch()
        except Exception:
            logger.exception("Website Index scheduler failed.")
        time.sleep(interval)


def _triggered_batch_runner() -> None:
    try:
        run_website_index_weekly_batch()
    except Exception:
        logger.exception("Website Index manually triggered batch failed.")


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


def _page_discovery_is_due() -> bool:
    last_run = get_setting(PAGE_DISCOVERY_LAST_RUN_SETTING, "").strip()
    if not last_run:
        return True
    try:
        last_run_at = datetime.fromisoformat(last_run)
    except ValueError:
        return True
    if last_run_at.tzinfo is None:
        last_run_at = last_run_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last_run_at >= timedelta(seconds=_page_discovery_interval_seconds())


def _page_discovery_interval_seconds() -> int:
    raw_value = os.getenv("WEBSITE_PAGES_DISCOVERY_INTERVAL_SECONDS", "").strip()
    if not raw_value:
        return DEFAULT_PAGE_DISCOVERY_INTERVAL_SECONDS
    try:
        return max(60, int(raw_value))
    except ValueError:
        return DEFAULT_PAGE_DISCOVERY_INTERVAL_SECONDS


def _page_discovery_limit() -> int:
    raw_value = os.getenv("WEBSITE_PAGES_DISCOVERY_LIMIT", "").strip()
    if not raw_value:
        return DEFAULT_PAGE_DISCOVERY_LIMIT
    try:
        return max(1, min(DEFAULT_PAGE_DISCOVERY_LIMIT, int(raw_value)))
    except ValueError:
        return DEFAULT_PAGE_DISCOVERY_LIMIT


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
