from __future__ import annotations

import os
from queue import Queue
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import RLock, Thread
from uuid import uuid4

from flask import Flask

from logger import logger


TERMINAL_STATUSES = {"complete", "failed"}
_JOBS: dict[str, "BackgroundJob"] = {}
_PENDING_IDS: list[str] = []
_JOB_QUEUE: Queue[tuple[str, str, dict[str, list[str]]]] = Queue()
_LOCK = RLock()
_WORKERS_STARTED = False
_WORKER_APP: Flask | None = None


@dataclass
class BackgroundJob:
    id: str
    path: str
    status: str = "queued"
    message: str = "Queued."
    html: str = ""
    status_code: int = 0
    error: str = ""
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
        }
        if include_html:
            payload["html"] = self.html
        return payload


def start_background_post(app: Flask, path: str, form_data: dict[str, list[str]]) -> BackgroundJob:
    cleanup_background_jobs()
    _ensure_workers(app)
    job = BackgroundJob(id=uuid4().hex, path=path)
    with _LOCK:
        _JOBS[job.id] = job
        _PENDING_IDS.append(job.id)
    _JOB_QUEUE.put((job.id, path, form_data))
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
        jobs = sorted(_JOBS.values(), key=lambda item: item.created_at, reverse=True)
        return [job.to_dict(include_html=False) | _job_times(job) for job in jobs]


def background_worker_count() -> int:
    return _worker_count()


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
        job_id, path, form_data = _JOB_QUEUE.get()
        try:
            app = _WORKER_APP
            if app is None:
                _update_job(job_id, status="failed", message="Generation failed.", error="Worker app is not ready.", status_code=500)
                continue
            _run_background_post(app, job_id, path, form_data)
        finally:
            _JOB_QUEUE.task_done()


def _run_background_post(app: Flask, job_id: str, path: str, form_data: dict[str, list[str]]) -> None:
    with _LOCK:
        if job_id in _PENDING_IDS:
            _PENDING_IDS.remove(job_id)
    _update_job(job_id, status="running", message="Generating...")
    try:
        with app.test_client() as client:
            response = client.post(path, data=form_data)
            html = response.get_data(as_text=True)
            _update_job(
                job_id,
                status="complete",
                message="Generation complete.",
                html=html,
                status_code=response.status_code,
            )
    except Exception as exc:
        logger.exception("background generation job failed")
        _update_job(
            job_id,
            status="failed",
            message="Generation failed.",
            error=str(exc) or "Background generation failed.",
            status_code=500,
        )


def _update_job(job_id: str, **changes) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        for key, value in changes.items():
            setattr(job, key, value)
        job.updated_at = datetime.utcnow()


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
