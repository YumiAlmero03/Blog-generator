from app import create_app
from app.controllers import news_controller


def test_reference_context_stops_when_all_links_are_unreadable(monkeypatch):
    state = {
        "links": [{"url": "https://www.fifa.com/example"}],
        "reference_fetches": [],
        "error": None,
    }
    progress_messages = []

    monkeypatch.setattr(
        news_controller,
        "fetch_reference_context",
        lambda links, **kwargs: (
            "",
            [
                {
                    "url": "https://www.fifa.com/example",
                    "status": "error",
                    "error": "Could not extract enough readable article text.",
                }
            ],
        ),
    )

    context = news_controller._reference_context_for_state(state, progress_messages.append)

    assert context == ""
    assert state["error"] == "Reference links could not be read, so News Generator stopped instead of writing from unsupported context."
    assert state["reference_fetches"][0]["status"] == "error"
    assert "Generation stopped" in progress_messages[-1]


def test_reference_context_uses_browser_reader(monkeypatch):
    state = {
        "links": [{"url": "https://www.fifa.com/example"}],
        "reference_fetches": [],
        "error": None,
    }
    calls = {}

    def fake_fetch_reference_context(links, **kwargs):
        calls.update(kwargs)
        return (
            "Reference 1: FIFA\nURL: https://www.fifa.com/example\nExtracted content:\nRendered article",
            [
                {
                    "url": "https://www.fifa.com/example",
                    "status": "fetched",
                    "excerpt": "Rendered article",
                    "fetch_method": "browser",
                }
            ],
        )

    monkeypatch.setattr(news_controller, "fetch_reference_context", fake_fetch_reference_context)

    context = news_controller._reference_context_for_state(state, lambda message: None)

    assert "Rendered article" in context
    assert calls["use_browser"] is True
    assert calls["browser_wait_seconds"] == 2
    assert calls["content_tags"] == news_controller.NEWS_REFERENCE_CONTENT_TAGS
    assert calls["merge_context"] is True
    assert state["reference_fetches"][0]["fetch_method"] == "browser"


def test_reference_fetch_summary_counts_failures():
    summary = news_controller._reference_fetch_summary(
        [
            {"status": "fetched"},
            {"status": "error"},
            {"status": "skipped"},
        ]
    )

    assert summary == {"fetched": 1, "failed": 2, "total": 3}


def test_cached_reference_context_is_merged():
    context = news_controller._reference_context_from_cached_fetches(
        [
            {"url": "https://example.com/one"},
            {"url": "https://example.com/two"},
        ],
        [
            {
                "url": "https://example.com/one",
                "status": "fetched",
                "source_label": "First Link",
                "excerpt": "First link facts.",
            },
            {
                "url": "https://example.com/two",
                "status": "fetched",
                "source_label": "Second Link",
                "excerpt": "Second link facts.",
            },
        ],
    )

    assert context.startswith("Combined reference source.")
    assert "First link facts." in context
    assert "Second link facts." in context
    assert "Reference 1:" not in context


def test_hydrate_news_state_prefers_custom_title():
    app = create_app()
    state = news_controller._initial_state()

    with app.test_request_context(
        "/news-generator",
        method="POST",
        data={
            "selected_title": "Generated News Title",
            "custom_title": "Custom News Title",
            "keyword": "world cup update",
            "titles_json": '["Generated News Title"]',
        },
    ):
        news_controller._hydrate_news_state(state)

    assert state["custom_title"] == "Custom News Title"
    assert state["selected_title"] == "Custom News Title"


def test_hydrate_news_state_allows_blank_meta_description_with_options():
    app = create_app()
    state = news_controller._initial_state()

    with app.test_request_context(
        "/news-generator",
        method="POST",
        data={
            "selected_title": "Generated News Title",
            "keyword": "world cup update",
            "titles_json": '["Generated News Title"]',
            "meta_descriptions_json": '[{"text":"Generated meta description","character_count":26}]',
            "meta_description_choice": "",
        },
    ):
        news_controller._hydrate_news_state(state)

    assert state["meta_description"] == ""
