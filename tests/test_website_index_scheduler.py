from datetime import datetime, timezone

from app.services import website_index_scheduler


def test_scheduler_batch_marks_manual_when_google_settings_missing(monkeypatch):
    calls = {}

    monkeypatch.setattr(
        website_index_scheduler,
        "list_due_website_index_urls",
        lambda: [{"url": f"https://example.com/{index}"} for index in range(52)],
    )
    monkeypatch.setattr(website_index_scheduler, "get_setting", lambda key, default="": "")
    monkeypatch.setattr(website_index_scheduler, "mark_website_index_urls_checking", lambda urls: calls.setdefault("checking", urls))
    monkeypatch.setattr(website_index_scheduler, "update_website_index_bing_yahoo_weekly_result", lambda urls: calls.setdefault("manual", urls))

    checked_count = website_index_scheduler.run_website_index_weekly_batch()

    assert checked_count == 50
    assert calls["checking"] == [f"https://example.com/{index}" for index in range(50)]
    assert calls["manual"] == [f"https://example.com/{index}" for index in range(50)]


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
    monkeypatch.setattr(website_index_scheduler, "update_website_index_bing_yahoo_weekly_result", lambda urls: calls.setdefault("manual", urls))
    def fake_inspect(**kwargs):
        calls["google_kwargs"] = kwargs
        return Result()

    monkeypatch.setattr(website_index_scheduler, "inspect_google_index_status_by_url_domain", fake_inspect)
    monkeypatch.setattr(website_index_scheduler, "update_website_index_google_result", lambda item: calls.setdefault("google_items", []).append(item))

    checked_count = website_index_scheduler.run_website_index_weekly_batch()

    assert checked_count == 2
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

    result = website_index_scheduler.run_website_pages_daily_discovery()

    assert result["domains"] == 1
    assert result["discovered"] == 2
    assert result["saved"] == 2
    assert calls["discover"] == {"base_url": "https://example.com", "limit": 1000}
    assert calls["upsert"] == ["https://example.com/a", "https://example.com/b"]
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


def test_scheduler_default_interval_is_10_minutes(monkeypatch):
    monkeypatch.delenv("WEBSITE_INDEX_SCHEDULER_INTERVAL_SECONDS", raising=False)

    assert website_index_scheduler._interval_seconds() == 60 * 10


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
