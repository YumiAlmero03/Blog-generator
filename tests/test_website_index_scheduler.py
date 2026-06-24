from app.services import website_index_scheduler


def test_scheduler_batch_marks_manual_when_google_settings_missing(monkeypatch):
    calls = {}

    monkeypatch.setattr(
        website_index_scheduler,
        "list_due_website_index_urls",
        lambda: [{"url": f"https://example.com/{index}"} for index in range(12)],
    )
    monkeypatch.setattr(website_index_scheduler, "get_setting", lambda key, default="": "")
    monkeypatch.setattr(website_index_scheduler, "mark_website_index_urls_checking", lambda urls: calls.setdefault("checking", urls))
    monkeypatch.setattr(website_index_scheduler, "update_website_index_bing_yahoo_weekly_result", lambda urls: calls.setdefault("manual", urls))

    checked_count = website_index_scheduler.run_website_index_weekly_batch()

    assert checked_count == 10
    assert calls["checking"] == [f"https://example.com/{index}" for index in range(10)]
    assert calls["manual"] == [f"https://example.com/{index}" for index in range(10)]


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
            "google_search_console_property": "https://example.com/",
            "google_oauth_access_token": "token",
            "google_service_account_json": "",
        }.get(key, default),
    )
    monkeypatch.setattr(website_index_scheduler, "mark_website_index_urls_checking", lambda urls: calls.setdefault("checking", urls))
    monkeypatch.setattr(website_index_scheduler, "update_website_index_bing_yahoo_weekly_result", lambda urls: calls.setdefault("manual", urls))
    def fake_inspect(**kwargs):
        calls["google_kwargs"] = kwargs
        return Result()

    monkeypatch.setattr(website_index_scheduler, "inspect_google_index_status", fake_inspect)
    monkeypatch.setattr(website_index_scheduler, "update_website_index_google_result", lambda item: calls.setdefault("google_items", []).append(item))

    checked_count = website_index_scheduler.run_website_index_weekly_batch()

    assert checked_count == 2
    assert calls["google_kwargs"]["urls"] == ["https://example.com/a", "https://example.com/b"]
    assert calls["google_items"] == ["item-1", "item-2"]


def test_scheduler_default_interval_is_30_minutes(monkeypatch):
    monkeypatch.delenv("WEBSITE_INDEX_SCHEDULER_INTERVAL_SECONDS", raising=False)

    assert website_index_scheduler._interval_seconds() == 60 * 30
