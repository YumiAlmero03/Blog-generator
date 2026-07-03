from __future__ import annotations

import os
import re
from io import BytesIO
from queue import Queue
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import RLock, Thread
from uuid import uuid4

from flask import Flask

from generation_retry_policy import GenerationCancelled
from logger import logger


TERMINAL_STATUSES = {"complete", "failed", "cancelled"}
_JOBS: dict[str, "BackgroundJob"] = {}
_SYSTEM_JOBS: dict[str, "BackgroundJob"] = {}
_PENDING_IDS: list[str] = []
_JOB_QUEUE: Queue[tuple[str, str, dict[str, list[str]], dict[str, list[dict]]]] = Queue()
_LOCK = RLock()
_WORKERS_STARTED = False
_WORKER_APP: Flask | None = None
_TOKEN_JOB_IDS: dict[str, str] = {}


@dataclass
class BackgroundJob:
    id: str
    path: str
    status: str = "queued"
    message: str = "Queued."
    html: str = ""
    status_code: int = 0
    error: str = ""
    repeat_reason: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self, include_html: bool = False) -> dict:
        queue_position = _queue_position(self.id) if self.status == "queued" else 0
        payload = {
            "id": self.id,
            "path": self.path,
            "status": self.status,
            "message": f"Queued. Position {queue_position}." if queue_position > 1 else self.message,
            "queue_position": queue_position,
            "status_code": self.status_code,
            "error": self.error,
            "repeat_reason": self.repeat_reason,
        }
        if include_html:
            payload["html"] = self.html
        return payload


def start_background_post(
    app: Flask,
    path: str,
    form_data: dict[str, list[str]],
    file_data: dict[str, list[dict]] | None = None,
) -> BackgroundJob:
    cleanup_background_jobs()
    _ensure_workers(app)
    job = BackgroundJob(id=uuid4().hex, path=path)
    with _LOCK:
        _JOBS[job.id] = job
        _PENDING_IDS.append(job.id)
        token = _generation_token_from_form(form_data)
        if token:
            _TOKEN_JOB_IDS[token] = job.id
    _JOB_QUEUE.put((job.id, path, form_data, file_data or {}))
    return job


def get_background_job(job_id: str) -> dict | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return None
        return job.to_dict(include_html=job.status in TERMINAL_STATUSES)


def list_background_jobs() -> list[dict]:
    cleanup_background_jobs()
    with _LOCK:
        jobs = sorted(
            [*_JOBS.values(), *_SYSTEM_JOBS.values()],
            key=lambda item: item.created_at,
            reverse=True,
        )
        return [job.to_dict(include_html=False) | _job_times(job) for job in jobs]


def background_job_stats(jobs: list[dict] | None = None) -> dict:
    listed_jobs = jobs if jobs is not None else list_background_jobs()
    return {
        "queued": sum(1 for job in listed_jobs if job.get("status") == "queued"),
        "running": sum(1 for job in listed_jobs if job.get("status") == "running"),
        "complete": sum(1 for job in listed_jobs if job.get("status") == "complete"),
        "failed": sum(1 for job in listed_jobs if job.get("status") == "failed"),
        "cancelled": sum(1 for job in listed_jobs if job.get("status") == "cancelled"),
        "total": len(listed_jobs),
        "slots": background_worker_count(),
    }


def background_worker_count() -> int:
    return _worker_count()


def start_system_background_job(path: str, message: str = "Running...") -> str:
    cleanup_background_jobs()
    job = BackgroundJob(
        id=uuid4().hex,
        path=path,
        status="running",
        message=message,
    )
    with _LOCK:
        _SYSTEM_JOBS[job.id] = job
    return job.id


def update_system_background_job(
    job_id: str,
    status: str,
    message: str = "",
    error: str = "",
    status_code: int = 0,
) -> None:
    _update_job(
        job_id,
        status=status,
        message=message,
        error=error,
        status_code=status_code,
    )


def update_background_job_from_generation_event(token: str = "", payload: dict | None = None) -> None:
    cleaned_token = (token or "").strip()
    if not cleaned_token:
        return

    event_payload = payload or {}
    message = str(event_payload.get("message", "") or "").strip()
    if not message:
        return

    with _LOCK:
        job_id = _TOKEN_JOB_IDS.get(cleaned_token)
        job = _JOBS.get(job_id or "")
        if not job or job.status in TERMINAL_STATUSES:
            return

    changes = {"message": message}
    repeat_reason = _repeat_reason_from_message(message)
    if repeat_reason:
        changes["repeat_reason"] = repeat_reason
    _update_job(job_id, **changes)


def cleanup_background_jobs(max_age_minutes: int = 30) -> None:
    cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)
    with _LOCK:
        expired_ids = [
            job_id
            for job_id, job in _JOBS.items()
            if job.updated_at < cutoff and job.status in TERMINAL_STATUSES
        ]
        for job_id in expired_ids:
            _JOBS.pop(job_id, None)
        active_job_ids = set(_JOBS)
        expired_tokens = [
            token
            for token, job_id in _TOKEN_JOB_IDS.items()
            if job_id not in active_job_ids
        ]
        for token in expired_tokens:
            _TOKEN_JOB_IDS.pop(token, None)
        expired_system_ids = [
            job_id
            for job_id, job in _SYSTEM_JOBS.items()
            if job.updated_at < cutoff and job.status in TERMINAL_STATUSES
        ]
        for job_id in expired_system_ids:
            _SYSTEM_JOBS.pop(job_id, None)


def _ensure_workers(app: Flask) -> None:
    global _WORKERS_STARTED, _WORKER_APP
    with _LOCK:
        if _WORKERS_STARTED:
            return
        _WORKERS_STARTED = True
        _WORKER_APP = app
        worker_count = _worker_count()

    for index in range(worker_count):
        worker = Thread(
            target=_worker_loop,
            name=f"background-generation-worker-{index + 1}",
            daemon=True,
        )
        worker.start()
    logger.info("Background generation queue started with %d worker(s).", worker_count)


def _worker_loop() -> None:
    while True:
        job_id, path, form_data, file_data = _JOB_QUEUE.get()
        try:
            app = _WORKER_APP
            if app is None:
                _update_job(job_id, status="failed", message="Generation failed.", error="Worker app is not ready.", status_code=500)
                continue
            _run_background_post(app, job_id, path, form_data, file_data)
        finally:
            _JOB_QUEUE.task_done()


def _run_background_post(
    app: Flask,
    job_id: str,
    path: str,
    form_data: dict[str, list[str]],
    file_data: dict[str, list[dict]] | None = None,
) -> None:
    generation_token = _generation_token_from_form(form_data)
    with _LOCK:
        if job_id in _PENDING_IDS:
            _PENDING_IDS.remove(job_id)
    _update_job(job_id, status="running", message=_initial_background_message(path))
    try:
        with app.test_client() as client:
            response = client.post(path, data=_background_post_data(form_data, file_data or {}))
            html = response.get_data(as_text=True)
            _update_job(
                job_id,
                status="complete",
                message="Generation complete.",
                html=html,
                status_code=response.status_code,
            )
    except Exception as exc:
        if isinstance(exc, GenerationCancelled):
            _update_job(
                job_id,
                status="cancelled",
                message="Generation skipped.",
                error=str(exc) or "Generation skipped by user.",
                status_code=499,
            )
            return
        logger.exception("background generation job failed")
        _update_job(
            job_id,
            status="failed",
            message="Generation failed.",
            error=str(exc) or "Background generation failed.",
            status_code=500,
        )
    finally:
        if generation_token:
            with _LOCK:
                if _TOKEN_JOB_IDS.get(generation_token) == job_id:
                    _TOKEN_JOB_IDS.pop(generation_token, None)


def _update_job(job_id: str, **changes) -> None:
    with _LOCK:
        job = _JOBS.get(job_id) or _SYSTEM_JOBS.get(job_id)
        if not job:
            return
        for key, value in changes.items():
            setattr(job, key, value)
        job.updated_at = datetime.utcnow()


def _background_post_data(form_data: dict[str, list[str]], file_data: dict[str, list[dict]]) -> dict:
    data = {key: values for key, values in form_data.items()}
    for field_name, files in (file_data or {}).items():
        prepared_files = []
        for file_info in files:
            prepared_files.append(
                (
                    BytesIO(file_info.get("content", b"")),
                    file_info.get("filename", ""),
                    file_info.get("content_type", "application/octet-stream"),
                )
            )
        if not prepared_files:
            continue
        data[field_name] = prepared_files[0] if len(prepared_files) == 1 else prepared_files
    return data


def _queue_position(job_id: str) -> int:
    with _LOCK:
        try:
            return _PENDING_IDS.index(job_id) + 1
        except ValueError:
            return 0


def _job_times(job: BackgroundJob) -> dict:
    return {
        "created_at": job.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": job.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        "age_seconds": max(0, int((datetime.utcnow() - job.created_at).total_seconds())),
    }


def _worker_count() -> int:
    raw_value = os.getenv("BACKGROUND_JOB_WORKERS", "3").strip()
    try:
        return max(1, min(4, int(raw_value)))
    except ValueError:
        return 1


def _generation_token_from_form(form_data: dict[str, list[str]]) -> str:
    raw_value = form_data.get("generation_status_token", "")
    if isinstance(raw_value, list):
        raw_value = raw_value[0] if raw_value else ""
    return str(raw_value or "").strip()


def _initial_background_message(path: str) -> str:
    cleaned_path = (path or "").lower()
    if "seo-checker" in cleaned_path:
        return "Running website SEO check..."
    if "page-generator" in cleaned_path:
        return "Generating page..."
    if "simple-page" in cleaned_path:
        return "Generating simple page..."
    if "news-generator" in cleaned_path:
        return "Generating news content..."
    if "blog-rework-generator" in cleaned_path:
        return "Reworking source blog..."
    if "blog-generator" in cleaned_path:
        return "Generating blog content..."
    if "keyword-suggestions" in cleaned_path:
        return "Generating keyword suggestions..."
    return "Starting background job..."


def _repeat_reason_from_message(message: str = "") -> str:
    cleaned_message = " ".join(str(message or "").split())
    if not cleaned_message:
        return ""

    lowered = cleaned_message.lower()
    if "retry" not in lowered and "attempt" not in lowered:
        return ""

    reason = cleaned_message
    if ": " in reason:
        reason = reason.split(": ", 1)[1]

    reason = re.sub(r"\s*retrying\.\.\.$", "", reason, flags=re.IGNORECASE).strip()
    reason = re.sub(
        r"^waiting\s+\d+s\s+before\s+retrying\s+after\s+",
        "",
        reason,
        flags=re.IGNORECASE,
    ).strip()
    reason = reason.rstrip(".").strip()
    if not reason:
        return ""
    return reason[:180] + ("..." if len(reason) > 180 else "")
