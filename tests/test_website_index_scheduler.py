from datetime import datetime, timezone

from app.services import website_index_scheduler


def test_submit_due_urls_to_indexnow_groups_urls_by_host(monkeypatch):
    calls = []

    class Result:
        def __init__(self, host, submitted_count):
            self.host = host
            self.submitted_count = submitted_count
            self.skipped = []
            self.batches = []
            self.ok = True

    monkeypatch.setattr(
        website_index_scheduler,
        "get_setting",
        lambda key, default="": {
            "indexnow_key": "abc12345",
            "indexnow_key_location": "https://example.com/abc12345.txt",
            "indexnow_endpoint": "https://api.indexnow.org/indexnow",
        }.get(key, default),
    )

    def fake_submit_indexnow_urls(**kwargs):
        calls.append(kwargs)
        return Result(kwargs["host"], len(kwargs["urls"]))

    monkeypatch.setattr(website_index_scheduler, "submit_indexnow_urls", fake_submit_indexnow_urls)

    result = website_index_scheduler.submit_website_index_urls_to_indexnow(
        [
            "https://example.com/a",
            "https://example.com/a",
            "https://other.com/b",
            "not-a-url",
        ]
    )

    assert result == {"hosts": 2, "submitted": 2, "skipped": 2, "errors": []}
    assert calls[0]["host"] == "example.com"
    assert calls[0]["urls"] == ["https://example.com/a"]
    assert calls[0]["key_location"] == "https://example.com/abc12345.txt"
    assert calls[1]["host"] == "other.com"
    assert calls[1]["urls"] == ["https://other.com/b"]
    assert calls[1]["key_location"] == ""


def test_submit_due_urls_to_indexnow_skips_when_key_missing(monkeypatch):
    monkeypatch.setattr(website_index_scheduler, "get_setting", lambda key, default="": "")

    result = website_index_scheduler.submit_website_index_urls_to_indexnow(["https://example.com/a"])

    assert result["submitted"] == 0
    assert result["skipped"] == 1
    assert result["errors"] == ["IndexNow key is missing."]


def test_scheduler_batch_skips_when_google_settings_missing(monkeypatch):
    calls = {}
    due_rows = [{"url": f"https://example.com/{index}"} for index in range(52)]

    monkeypatch.setattr(
        website_index_scheduler,
        "list_due_website_index_urls",
        lambda: due_rows,
    )
    monkeypatch.setattr(website_index_scheduler, "get_setting", lambda key, default="": "")
    monkeypatch.setattr(website_index_scheduler, "mark_website_index_urls_checking", lambda urls: calls.setdefault("checking", urls))

    checked_count = website_index_scheduler.run_website_index_weekly_batch()

    assert checked_count == 0
    assert "checking" not in calls


def test_scheduler_batch_updates_google_results_when_configured(monkeypatch):
    calls = {}

    class Result:
        items = ["item-1", "item-2"]

    monkeypatch.setattr(
        website_index_scheduler,
        "list_due_website_index_urls",
        lambda: [{"url": "https://example.com/a"}, {"url": "https://example.com/b"}],
    )
    monkeypatch.setattr(
        website_index_scheduler,
        "get_setting",
        lambda key, default="": {
            "google_oauth_access_token": "token",
            "google_service_account_json": "",
        }.get(key, default),
    )
    monkeypatch.setattr(website_index_scheduler, "mark_website_index_urls_checking", lambda urls: calls.setdefault("checking", urls))
    def fake_inspect(**kwargs):
        calls["google_kwargs"] = kwargs
        return Result()

    monkeypatch.setattr(website_index_scheduler, "inspect_google_index_status_by_url_domain", fake_inspect)
    monkeypatch.setattr(website_index_scheduler, "update_website_index_google_result", lambda item: calls.setdefault("google_items", []).append(item))

    checked_count = website_index_scheduler.run_website_index_weekly_batch()

    assert checked_count == 2
    assert calls["checking"] == ["https://example.com/a", "https://example.com/b"]
    assert calls["google_kwargs"]["urls"] == ["https://example.com/a", "https://example.com/b"]
    assert "site_url" not in calls["google_kwargs"]
    assert calls["google_items"] == ["item-1", "item-2"]


def test_daily_page_discovery_saves_new_pages(monkeypatch):
    calls = {"settings": []}

    class Result:
        pages = ["https://example.com/a", "https://example.com/b"]
        errors = []

    monkeypatch.setattr(
        website_index_scheduler,
        "list_website_index_site_roots",
        lambda: [{"domain": "example.com", "base_url": "https://example.com"}],
    )

    def fake_discover(base_url, limit):
        calls["discover"] = {"base_url": base_url, "limit": limit}
        return Result()

    monkeypatch.setattr(website_index_scheduler, "discover_website_pages", fake_discover)

    def fake_upsert(urls):
        calls["upsert"] = urls
        return 2

    monkeypatch.setattr(website_index_scheduler, "upsert_website_index_urls", fake_upsert)
    monkeypatch.setattr(website_index_scheduler, "set_setting", lambda key, value: calls["settings"].append((key, value)))
    monkeypatch.setattr(
        website_index_scheduler,
        "get_setting",
        lambda key, default="": {
            "google_oauth_access_token": "token",
            "google_service_account_json": "",
        }.get(key, default),
    )
    monkeypatch.setattr(
        website_index_scheduler,
        "list_due_website_index_submission_urls",
        lambda: [{"url": "https://example.com/not-indexed-a"}, {"url": "https://example.com/not-indexed-b"}],
    )

    class SubmitResult:
        submitted_count = 2
        skipped = []
        items = [
            type("Item", (), {"status": "ok"})(),
        ]

    def fake_google_submit(**kwargs):
        calls["google_submit"] = kwargs
        return SubmitResult()

    monkeypatch.setattr(website_index_scheduler, "submit_google_indexing_urls", fake_google_submit)

    result = website_index_scheduler.run_website_pages_daily_discovery()

    assert result["domains"] == 1
    assert result["discovered"] == 2
    assert result["saved"] == 2
    assert result["google_submitted"] == 2
    assert calls["discover"] == {"base_url": "https://example.com", "limit": 1000}
    assert calls["upsert"] == ["https://example.com/a", "https://example.com/b"]
    assert calls["google_submit"]["urls"] == ["https://example.com/not-indexed-a", "https://example.com/not-indexed-b"]
    assert calls["google_submit"]["notification_type"] == "URL_UPDATED"
    assert calls["settings"][0][0] == website_index_scheduler.PAGE_DISCOVERY_LAST_RUN_SETTING


def test_daily_page_discovery_due_uses_24_hour_window(monkeypatch):
    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 29, 0, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(website_index_scheduler, "datetime", FakeDateTime)
    monkeypatch.setattr(website_index_scheduler, "get_setting", lambda key, default="": "2026-06-28T00:00:00+00:00")

    assert website_index_scheduler._page_discovery_is_due() is True

    monkeypatch.setattr(website_index_scheduler, "get_setting", lambda key, default="": "2026-06-28T23:59:00+00:00")

    assert website_index_scheduler._page_discovery_is_due() is False


def test_scheduler_default_interval_is_30_minutes(monkeypatch):
    monkeypatch.delenv("WEBSITE_INDEX_SCHEDULER_INTERVAL_SECONDS", raising=False)

    assert website_index_scheduler._interval_seconds() == 60 * 30


def test_trigger_website_index_batch_starts_thread(monkeypatch):
    calls = {}

    class FakeThread:
        def __init__(self, target, name, daemon):
            calls["target"] = target
            calls["name"] = name
            calls["daemon"] = daemon

        def start(self):
            calls["started"] = True

    monkeypatch.setattr(website_index_scheduler.threading, "Thread", FakeThread)

    website_index_scheduler.trigger_website_index_batch()

    assert calls["name"] == "website-index-manual-trigger"
    assert calls["daemon"] is True
    assert calls["started"] is True
