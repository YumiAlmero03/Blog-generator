from app.events.generation_events import publish_generation_status
from app.services.background_job_service import (
    BackgroundJob,
    _JOBS,
    _LOCK,
    _TOKEN_JOB_IDS,
    _repeat_reason_from_message,
)


def test_repeat_reason_from_retry_message():
    message = "Page content attempt 1: 783 words, content must be more than 900. Retrying..."

    assert _repeat_reason_from_message(message) == "783 words, content must be more than 900"


def test_generation_status_updates_background_job_message_and_repeat_reason():
    job = BackgroundJob(id="test-job", path="/page-generator", status="running")
    token = "test-token"
    with _LOCK:
        _JOBS[job.id] = job
        _TOKEN_JOB_IDS[token] = job.id

    try:
        publish_generation_status(
            token,
            "Page content attempt 2: repeated sentence detected. Retrying...",
        )

        with _LOCK:
            updated_job = _JOBS[job.id]
            assert updated_job.message == "Page content attempt 2: repeated sentence detected. Retrying..."
            assert updated_job.repeat_reason == "repeated sentence detected"
    finally:
        with _LOCK:
            _JOBS.pop(job.id, None)
            _TOKEN_JOB_IDS.pop(token, None)
