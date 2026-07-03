from io import BytesIO

from app import create_app
from app.events.generation_events import publish_generation_status
from app.services.background_job_service import (
    BackgroundJob,
    _JOBS,
    _LOCK,
    _TOKEN_JOB_IDS,
    _repeat_reason_from_message,
)


class DummyStartedJob:
    def to_dict(self):
        return {
            "id": "queued-job",
            "path": "/gsc-planner",
            "status": "queued",
            "message": "Queued.",
            "status_code": 0,
            "error": "",
            "repeat_reason": "",
            "queue_position": 1,
        }


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


def test_background_job_preserves_uploaded_files(monkeypatch):
    from app.controllers import background_job_controller

    captured = {}

    def fake_start_background_post(app, path, form_data, file_data=None):
        captured["path"] = path
        captured["form_data"] = form_data
        captured["file_data"] = file_data or {}
        return DummyStartedJob()

    monkeypatch.setattr(background_job_controller, "start_background_post", fake_start_background_post)

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/background-jobs",
        data={
            "_background_path": "/gsc-planner",
            "action": "generate_report",
            "brand": "Example Brand",
            "gsc_screenshot": (BytesIO(b"fake image bytes"), "gsc.png", "image/png"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 202
    assert captured["path"] == "/gsc-planner"
    assert captured["form_data"]["brand"] == ["Example Brand"]
    assert captured["file_data"]["gsc_screenshot"][0]["filename"] == "gsc.png"
    assert captured["file_data"]["gsc_screenshot"][0]["content_type"] == "image/png"
    assert captured["file_data"]["gsc_screenshot"][0]["content"] == b"fake image bytes"


def test_background_job_returns_json_for_large_form_payload():
    app = create_app()
    app.testing = True
    app.config["MAX_FORM_MEMORY_SIZE"] = 128

    response = app.test_client().post(
        "/background-jobs",
        data={
            "_background_path": "/gsc-planner",
            "captured_screenshot_data": "x" * 512,
        },
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 413
    assert "upload is too large" in response.get_json()["error"]


def test_base_layout_includes_floating_background_jobs_widget_on_main_pages():
    app = create_app()
    app.testing = True
    client = app.test_client()
    paths = [
        "/dashboard",
        "/",
        "/news-generator",
        "/page-generator",
        "/simple-page-generator",
        "/blog-rework-generator",
        "/keyword-suggestions",
        "/seo-checker",
        "/website-index-dashboard",
        "/website-pages",
        "/settings",
    ]

    for path in paths:
        response = client.get(path)
        html = response.get_data(as_text=True)
        assert response.status_code == 200, path
        assert "data-background-jobs-widget" in html, path
        assert "background_jobs_widget.js" in html, path


def test_simple_page_generator_single_button_runs_full_sequence(monkeypatch):
    from app.controllers import page_controller

    calls = []

    monkeypatch.setattr(page_controller, "get_provider", lambda: object())
    monkeypatch.setattr(page_controller, "get_brand_context", lambda brand: {})
    monkeypatch.setattr(page_controller, "upsert_brand", lambda brand: None)
    monkeypatch.setattr(page_controller, "get_page_word_limits", lambda: (100, 200))
    monkeypatch.setattr(page_controller, "_record_completed_simple_page", lambda state, selected_meta, min_words, max_words: None)

    def fake_title(*args, **kwargs):
        calls.append("title")
        return "Generated Privacy Policy"

    def fake_meta(*args, **kwargs):
        calls.append("meta")
        return [{"text": "Clear privacy policy meta description for visitors.", "character_count": 51}]

    def fake_content(*args, **kwargs):
        calls.append("content")
        return "<h2>Privacy Policy</h2><p>Generated content.</p>"

    monkeypatch.setattr(page_controller, "generate_simple_page_title", fake_title)
    monkeypatch.setattr(page_controller, "generate_simple_page_meta_descriptions", fake_meta)
    monkeypatch.setattr(page_controller, "generate_simple_page_content", fake_content)

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/simple-page-generator",
        data={
            "action": "generate_simple_page_all",
            "page_title": "Privacy Policy",
            "page_type": "Privacy Policy",
            "language": "English",
        },
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert calls == ["title", "meta", "content"]
    assert "Generated Privacy Policy" in html
    assert "Generated content." in html
    assert "data-inline-loading" in html
    assert "generate_simple_page_all" in html
