from datetime import datetime, timezone

from app import create_app
from app.services import scheduled_job_service


def test_list_scheduled_jobs_includes_trigger_details(monkeypatch):
    monkeypatch.setattr(scheduled_job_service, "get_setting", lambda key, default="": "2026-07-10T00:00:00+00:00")
    now = datetime(2026, 7, 11, 0, 30, tzinfo=timezone.utc)

    jobs = scheduled_job_service.list_scheduled_jobs(now=now)

    names = [job["name"] for job in jobs]
    assert names == [
        "Website Pages Daily Discovery",
        "Website Index Scheduled Check",
        "Image Tool Cleanup",
    ]
    assert jobs[0]["next_trigger_label"] == "Due on next scheduler loop"
    assert "every 30 minutes" in jobs[1]["trigger"]
    assert "older than 15 day(s)" in jobs[2]["notes"]


def test_background_jobs_dashboard_lists_auto_jobs(monkeypatch):
    monkeypatch.setenv("WEBSITE_INDEX_SCHEDULER", "false")
    monkeypatch.setenv("IMAGE_TOOL_CLEANUP_SCHEDULER", "false")
    app = create_app()
    app.testing = True

    response = app.test_client().get("/background-jobs-dashboard")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Auto Jobs" in html
    assert "Website Index Scheduled Check" in html
    assert "Image Tool Cleanup" in html
