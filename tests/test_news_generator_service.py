import json
import time
from pathlib import Path

import pytest
from flask import Flask

from app.controllers import news_controller
from generators import news_generator


@pytest.fixture(autouse=True)
def isolated_news_settings(monkeypatch):
    monkeypatch.setattr(news_controller, "get_default_language", lambda: "English")
    monkeypatch.setattr(news_controller, "get_default_country_target", lambda: "Worldwide")
    monkeypatch.setattr(news_controller, "list_brand_names", lambda: [])
    monkeypatch.setattr(news_controller, "list_checklist_items", lambda *args, **kwargs: [])
    monkeypatch.setattr(news_controller, "get_setting", lambda key, default="": default)


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
                "reader_version": news_controller.NEWS_REFERENCE_READER_VERSION,
                "fetched_at": time.time(),
            },
            {
                "url": "https://example.com/two",
                "status": "fetched",
                "source_label": "Second Link",
                "excerpt": "Second link facts.",
                "reader_version": news_controller.NEWS_REFERENCE_READER_VERSION,
                "fetched_at": time.time(),
            },
        ],
    )

    assert context.startswith("Combined reference source.")
    assert "First link facts." in context
    assert "Second link facts." in context
    assert "Reference 1:" not in context


@pytest.mark.parametrize("metadata", [
    {},
    {"reader_version": "old-reader", "fetched_at": 2000},
    {"reader_version": news_controller.NEWS_REFERENCE_READER_VERSION, "fetched_at": 1000},
    {"reader_version": news_controller.NEWS_REFERENCE_READER_VERSION, "fetched_at": "invalid"},
    {"reader_version": news_controller.NEWS_REFERENCE_READER_VERSION, "fetched_at": 3000},
])
def test_incomplete_or_stale_reference_cache_is_refetched(monkeypatch, metadata):
    monkeypatch.setattr(news_controller.time, "time", lambda: 2000)
    url = "https://example.com/fixtures"
    state = {
        "links": [{"url": url}],
        "reference_fetches": [{"url": url, "status": "fetched", "excerpt": "Old cookie text", **metadata}],
        "error": None,
    }
    calls = []

    def fetch(links, **kwargs):
        calls.append(kwargs)
        return "Como vs Cagliari, Saturday 14:00", [{
            "url": url,
            "status": "fetched",
            "excerpt": "Como vs Cagliari, Saturday 14:00",
        }]

    monkeypatch.setattr(news_controller, "fetch_reference_context", fetch)

    context = news_controller._reference_context_for_state(state, lambda message: None)
    cached_context = news_controller._reference_context_for_state(state, lambda message: None)

    assert "Como vs Cagliari" in context
    assert "Como vs Cagliari" in cached_context
    assert "Old cookie text" not in cached_context
    assert len(calls) == 1
    assert "main" in calls[0]["content_tags"]
    assert state["reference_fetches"][0]["reader_version"] == news_controller.NEWS_REFERENCE_READER_VERSION
    assert state["reference_fetches"][0]["fetched_at"] == 2000


def test_hydrate_news_state_prefers_custom_title():
    app = Flask(__name__)
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
    app = Flask(__name__)
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


def _article(marker, words):
    return "# Current news title\n\n## Latest update\n\n" + marker + " " + " ".join(f"detail{index}" for index in range(words))


def _configure_content_generation(monkeypatch, responses):
    class FakeProvider:
        def __init__(self):
            self.calls = 0

        def generate_json(self, prompt):
            response = responses[self.calls]
            self.calls += 1
            return response

    provider = FakeProvider()
    records = []
    monkeypatch.setenv("GENERATION_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("GENERATION_RETRY_DELAY_SECONDS", "0")
    monkeypatch.setattr(news_controller, "get_provider", lambda: provider)
    monkeypatch.setattr(news_controller, "get_brand_context", lambda brand: "")
    monkeypatch.setattr(news_controller, "get_blog_word_limits", lambda: (800, 1400))
    monkeypatch.setattr(news_generator, "build_web_research_context", lambda *args, **kwargs: "")
    monkeypatch.setattr(news_controller, "generate_news_tags", lambda *args, **kwargs: ["news"])
    monkeypatch.setattr(news_controller, "record_generation", lambda **kwargs: records.append(kwargs) or 1)
    for name in ("publish_generation_prompt", "publish_generation_status", "publish_generation_draft", "clear_generation_status"):
        monkeypatch.setattr(news_controller, name, lambda *args, **kwargs: None)
    return provider, records


def _run_content_generation(monkeypatch, responses, action, existing_content=""):
    provider, records = _configure_content_generation(monkeypatch, responses)

    app = Flask(__name__)
    state = news_controller._initial_state()
    with app.test_request_context(
        "/news-generator",
        method="POST",
        data={
            "selected_title": "Current news title",
            "keyword": "news",
            "content_html": existing_content,
            "meta_descriptions_json": '[{"text":"Existing meta description"}]',
            "visual": "Existing visual description",
        },
    ):
        if action == "generate_all":
            news_controller._handle_generate_all(state)
        else:
            news_controller._handle_generate_news_piece(state, action)
    return state, provider.calls, records


@pytest.mark.parametrize("action", ["generate_all", "generate_content"])
def test_short_news_keeps_best_draft_and_validation_error(monkeypatch, action):
    state, calls, records = _run_content_generation(
        monkeypatch,
        [json.dumps({"content": _article("bestdraft", 760)}), json.dumps({"content": _article("shorterdraft", 700)})],
        action,
    )

    assert calls == 2
    assert "bestdraft" in state["content"]
    assert "shorterdraft" not in state["content"]
    assert state["content"].startswith("<h2>Latest update</h2><p>")
    assert "Current news title" not in state["content"]
    assert "minimum: 800" in state["error"]
    assert "has not passed validation" in state["error"]
    assert state["quality_report"]["word_count"] < 800
    assert state["quality_report"]["checks"][0]["status"] != "pass"
    assert state["step"] == "content"
    assert records == []


def test_news_route_renders_best_draft_with_validation_error(monkeypatch):
    provider, records = _configure_content_generation(
        monkeypatch,
        [json.dumps({"content": _article("bestdraft", 760)}), json.dumps({"content": _article("shorterdraft", 700)})],
    )
    repo_root = Path(__file__).resolve().parents[1]
    app = Flask(__name__, template_folder=str(repo_root / "templates"), static_folder=str(repo_root / "static"))
    app.testing = True
    app.add_url_rule("/news-generator", view_func=news_controller.news_generator, methods=["POST"])

    response = app.test_client().post(
        "/news-generator",
        data={
            "action": "generate_content",
            "selected_title": "Current news title",
            "keyword": "news",
            "titles_json": '["Current news title"]',
        },
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="contentEditor"' in html
    assert "&lt;h2&gt;Latest update&lt;/h2&gt;&lt;p&gt;bestdraft" in html
    assert "minimum: 800" in html
    assert "has not passed validation" in html
    assert "Word count" in html
    assert "target 800-1400" in html
    assert provider.calls == 2
    assert records == []


@pytest.mark.parametrize("action", ["generate_all", "generate_content"])
def test_news_retry_success_uses_validated_article(monkeypatch, action):
    state, calls, records = _run_content_generation(
        monkeypatch,
        [json.dumps({"content": _article("shortdraft", 760)}), json.dumps({"content": _article("validarticle", 900)})],
        action,
    )

    assert calls == 2
    assert "validarticle" in state["content"]
    assert "shortdraft" not in state["content"]
    assert state["error"] is None
    assert state["quality_report"]["word_count"] >= 800
    assert state["step"] == "content"
    assert len(records) == 1
    assert records[0]["content"] == state["content"]


@pytest.mark.parametrize("action", ["generate_all", "generate_content"])
def test_news_without_usable_output_keeps_error_without_draft(monkeypatch, action):
    state, calls, records = _run_content_generation(monkeypatch, ["invalid json", '{"content":""}'], action)

    assert calls == 2
    assert state["content"] == ""
    assert "Generated article could not satisfy the rules" in state["error"]
    assert "draft is shown" not in state["error"]
    assert records == []


@pytest.mark.parametrize("action", ["generate_all", "generate_content"])
def test_failed_news_regeneration_preserves_existing_content(monkeypatch, action):
    existing_content = "<h2>Edited article</h2><p>Keep my changes.</p>"
    state, calls, records = _run_content_generation(
        monkeypatch,
        [json.dumps({"content": _article("newdraft", 760)}), json.dumps({"content": _article("shorterdraft", 700)})],
        action,
        existing_content=existing_content,
    )

    assert calls == 2
    assert state["content"] == existing_content
    assert "minimum: 800" in state["error"]
    assert "draft is shown" not in state["error"]
    assert state["step"] == "content"
    assert records == []


def test_news_generator_renders_minor_change_suggestions_before_content_and_passes_to_prompt(monkeypatch):
    captured_prompts = []

    class CaptureProvider:
        def generate_json(self, prompt):
            captured_prompts.append(prompt)
            if "Create" in prompt and "meta descriptions" in prompt.lower():
                return json.dumps(
                    {"meta_descriptions": [{"text": "Sample news meta description for testing.", "character_count": 40}]}
                )
            return json.dumps({"content": _article("suggestednews", 900)})

    records = []
    monkeypatch.setenv("GENERATION_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("GENERATION_RETRY_DELAY_SECONDS", "0")
    monkeypatch.setattr(news_controller, "get_provider", lambda: CaptureProvider())
    monkeypatch.setattr(news_controller, "get_brand_context", lambda brand: "")
    monkeypatch.setattr(news_controller, "get_blog_word_limits", lambda: (800, 1400))
    monkeypatch.setattr(news_generator, "build_web_research_context", lambda *args, **kwargs: "")
    monkeypatch.setattr(news_controller, "generate_news_tags", lambda *args, **kwargs: ["news"])
    monkeypatch.setattr(news_controller, "record_generation", lambda **kwargs: records.append(kwargs) or 1)
    for name in ("publish_generation_prompt", "publish_generation_status", "publish_generation_draft", "clear_generation_status"):
        monkeypatch.setattr(news_controller, name, lambda *args, **kwargs: None)

    repo_root = Path(__file__).resolve().parents[1]
    app = Flask(__name__, template_folder=str(repo_root / "templates"), static_folder=str(repo_root / "static"))
    app.testing = True
    app.add_url_rule("/news-generator", view_func=news_controller.news_generator, methods=["POST"])
    client = app.test_client()

    # 1. Step 2 before content exists still renders Minor change suggestions and preserves typed input.
    meta_res = client.post(
        "/news-generator",
        data={
            "action": "generate_meta_descriptions",
            "selected_title": "Current news title",
            "keyword": "event update",
            "titles_json": '["Current news title"]',
            "change_request": "Include schedule timeline and official registration rules",
        },
    )
    assert meta_res.status_code == 200
    meta_html = meta_res.get_data(as_text=True)
    assert "Minor change suggestions" in meta_html
    assert 'name="change_request"' in meta_html
    assert "Include schedule timeline and official registration rules" in meta_html

    # 2. Initial content generation receives the user's content suggestions in the news prompt.
    captured_prompts.clear()
    gen_res = client.post(
        "/news-generator",
        data={
            "action": "generate_content",
            "selected_title": "Current news title",
            "keyword": "event update",
            "titles_json": '["Current news title"]',
            "change_request": "Include schedule timeline and official registration rules",
        },
    )
    assert gen_res.status_code == 200
    assert any("Include schedule timeline and official registration rules" in p for p in captured_prompts)
    assert len(records) == 1
    assert records[0]["prompt_inputs"]["change_request"] == "Include schedule timeline and official registration rules"


def test_news_generator_applies_minor_revision_with_scope_and_reference_context(monkeypatch):
    captured = {}
    records = []

    class FakeRevisionProvider:
        def generate_json(self, prompt):
            captured["prompt"] = prompt
            return json.dumps({"content": "<h2>Updated Update</h2><p>Updated schedule October 2026.</p>"})

    monkeypatch.setenv("GENERATION_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("GENERATION_RETRY_DELAY_SECONDS", "0")
    monkeypatch.setattr(news_controller, "get_provider", lambda: FakeRevisionProvider())
    monkeypatch.setattr(news_controller, "get_brand_context", lambda brand: "")
    monkeypatch.setattr(news_controller, "get_blog_word_limits", lambda: (800, 1400))
    monkeypatch.setattr(news_controller, "record_generation", lambda **kwargs: records.append(kwargs) or 1)
    for name in ("publish_generation_prompt", "publish_generation_status", "publish_generation_draft", "clear_generation_status"):
        monkeypatch.setattr(news_controller, name, lambda *args, **kwargs: None)

    app = Flask(__name__)
    state = news_controller._initial_state()
    with app.test_request_context(
        "/news-generator",
        method="POST",
        data={
            "selected_title": "Current news title",
            "keyword": "event update",
            "content_html": "<h2>Initial Update</h2><p>Original copy.</p>",
            "change_request": "Add exact October 2026 schedule from source",
            "regenerate_scope": "section",
            "links_json": json.dumps([{"url": "https://example.com/news-source", "text": "", "type": "reference"}]),
            "reference_fetches_json": json.dumps(
                [
                    {
                        "url": "https://example.com/news-source",
                        "status": "fetched",
                        "source_label": "Official Source",
                        "excerpt": "Schedule starts October 15, 2026.",
                        "reader_version": news_controller.NEWS_REFERENCE_READER_VERSION,
                        "fetched_at": time.time(),
                    }
                ]
            ),
        },
    ):
        news_controller._handle_generate_news_piece(state, "generate_content")

    assert state["error"] is None
    assert "Updated schedule October 2026." in state["content"]
    assert "Add exact October 2026 schedule from source" in captured["prompt"]
    assert "Selected edit target:\nsection" in captured["prompt"]
    assert "Schedule starts October 15, 2026." in captured["prompt"]
    assert records[0]["prompt_inputs"]["change_request"] == "Add exact October 2026 schedule from source"
    assert records[0]["prompt_inputs"]["regenerate_scope"] == "section"


def test_news_generator_renders_and_applies_internal_and_money_site_links(monkeypatch):
    captured_prompts = []

    class LinkCaptureProvider:
        def generate_json(self, prompt):
            captured_prompts.append(prompt)
            body = _article("newslinks", 900)
            body += (
                "\n\nRead our [serie a guide](https://site.test/serie-a-guide), "
                "[official fixtures](https://outside.test/fixtures), and "
                "[main platform](https://money.test/offer).\n"
            )
            return json.dumps({"content": body})

    records = []
    reference_fetch_calls = []
    monkeypatch.setenv("GENERATION_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("GENERATION_RETRY_DELAY_SECONDS", "0")
    monkeypatch.setattr(news_controller, "get_provider", lambda: LinkCaptureProvider())
    monkeypatch.setattr(news_controller, "get_brand_context", lambda brand: "")
    monkeypatch.setattr(news_controller, "get_blog_word_limits", lambda: (800, 1400))
    monkeypatch.setattr(news_controller, "get_setting", lambda key, default="": "https://money.test" if key == "money_site" else default)
    monkeypatch.setattr(news_generator, "build_web_research_context", lambda *args, **kwargs: "Verified news fact.")
    monkeypatch.setattr(
        news_controller,
        "fetch_reference_context",
        lambda links, **kwargs: reference_fetch_calls.append(links) or ("", []),
    )
    monkeypatch.setattr(news_controller, "generate_news_tags", lambda *args, **kwargs: ["news"])
    monkeypatch.setattr(news_controller, "record_generation", lambda **kwargs: records.append(kwargs) or 42)
    for name in ("publish_generation_prompt", "publish_generation_status", "publish_generation_draft", "clear_generation_status"):
        monkeypatch.setattr(news_controller, name, lambda *args, **kwargs: None)

    article_links = [
        {"type": "internal", "text": "serie a guide", "url": "https://site.test/serie-a-guide"},
        {"type": "external", "text": "official fixtures", "url": "https://outside.test/fixtures"},
    ]
    repo_root = Path(__file__).resolve().parents[1]
    app = Flask(__name__, template_folder=str(repo_root / "templates"), static_folder=str(repo_root / "static"))
    app.testing = True
    app.add_url_rule("/news-generator", view_func=news_controller.news_generator, methods=["GET", "POST"])
    client = app.test_client()

    res = client.post(
        "/news-generator",
        data={
            "action": "generate_content",
            "selected_title": "Current news title",
            "keyword": "serie a update",
            "titles_json": '["Current news title"]',
            "include_money_site": "1",
            "article_links_json": json.dumps(article_links),
        },
    )
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # UI renders Step 2 internal link controls, money-site option, and Article link context.
    assert "Links to Include in Content" in html
    assert 'id="articleLinksContainer"' in html
    assert 'id="addArticleLinkButton"' in html
    assert 'id="include_money_site"' in html
    assert "https://money.test" in html
    assert "https://site.test/serie-a-guide" in html
    assert reference_fetch_calls == []

    # Prompt includes distributed anchor links and money site URL.
    assert any("Links to Include in Content:" in prompt for prompt in captured_prompts)
    assert any("Target placement: TOP section" in prompt for prompt in captured_prompts)
    assert any("Target placement: END section" in prompt for prompt in captured_prompts)
    assert any("Money Site URL:" in prompt and "https://money.test" in prompt for prompt in captured_prompts)

    # Internal link stays followable while external and money-site links get rel="nofollow".
    assert len(records) == 1
    saved_content = records[0]["content"]
    assert '<a href="https://site.test/serie-a-guide" target="_blank" rel="noopener noreferrer">serie a guide</a>' in saved_content
    assert '<a href="https://outside.test/fixtures" target="_blank" rel="noopener noreferrer nofollow">official fixtures</a>' in saved_content
    assert '<a href="https://money.test/offer" target="_blank" rel="noopener noreferrer nofollow">main platform</a>' in saved_content
    from html import unescape
    assert '<a href="https://site.test/serie-a-guide" target="_blank" rel="noopener noreferrer">serie a guide</a>' in unescape(html)

    # Saved history persists article_links and include_money_site, and loading restores them.
    assert records[0]["prompt_inputs"]["include_money_site"] is True
    assert records[0]["prompt_inputs"]["article_links"] == article_links

    monkeypatch.setattr(
        news_controller,
        "get_generation_history_item",
        lambda history_id: {
            "id": history_id,
            "brand_name": "",
            "primary_keyword": "serie a update",
            "title": "Current news title",
            "meta_description": "Meta",
            "content": records[0]["content"],
            "tags": "news",
            "quality_report": "{}",
            "prompt_inputs": json.dumps(records[0]["prompt_inputs"]),
        },
    )
    loaded = news_controller._initial_state()
    news_controller._load_history_item(loaded, 42)
    assert loaded["include_money_site"] is True
    assert loaded["article_links"] == article_links


def test_news_minor_revision_passes_article_links_and_money_site_url(monkeypatch):
    captured = {}

    class RevisionProvider:
        def generate_json(self, prompt):
            captured["prompt"] = prompt
            return json.dumps({
                "content": (
                    '<h2>Updated</h2><p>Read <a href="https://site.test/guide">guide</a> and '
                    '<a href="https://money.test">home</a>.</p>'
                )
            })

    monkeypatch.setenv("GENERATION_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("GENERATION_RETRY_DELAY_SECONDS", "0")
    monkeypatch.setattr(news_controller, "get_provider", lambda: RevisionProvider())
    monkeypatch.setattr(news_controller, "get_brand_context", lambda brand: "")
    monkeypatch.setattr(news_controller, "get_blog_word_limits", lambda: (800, 1400))
    monkeypatch.setattr(news_controller, "get_setting", lambda key, default="": "https://money.test" if key == "money_site" else default)
    monkeypatch.setattr(news_controller, "record_generation", lambda **kwargs: 1)
    for name in ("publish_generation_prompt", "publish_generation_status", "publish_generation_draft", "clear_generation_status"):
        monkeypatch.setattr(news_controller, name, lambda *args, **kwargs: None)

    app = Flask(__name__)
    state = news_controller._initial_state()
    with app.test_request_context(
        "/news-generator",
        method="POST",
        data={
            "selected_title": "Current news title",
            "keyword": "update",
            "content_html": "<h2>Initial</h2><p>Draft copy.</p>",
            "change_request": "Spread out internal links across sections",
            "regenerate_scope": "full",
            "include_money_site": "1",
            "article_links_json": json.dumps([
                {"type": "internal", "text": "guide", "url": "https://site.test/guide"},
            ]),
        },
    ):
        news_controller._handle_generate_news_piece(state, "generate_content")

    assert state["error"] is None
    assert "https://site.test/guide" in captured["prompt"]
    assert "Ensure this required URL appears exactly once in the article: https://money.test" in captured["prompt"]
    assert '<a href="https://site.test/guide">guide</a>' in state["content"]
    assert '<a href="https://money.test" rel="nofollow">home</a>' in state["content"]


def test_news_custom_title_skips_ai_title_generation_and_preserves_inputs(monkeypatch):
    monkeypatch.setattr(news_controller, "get_provider", lambda: (_ for _ in ()).throw(AssertionError("AI should not run")))
    monkeypatch.setattr(news_controller, "fetch_reference_context", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Reference fetch should not run during use_custom_title")))
    app = Flask(__name__)
    state = news_controller._initial_state()

    with app.test_request_context(
        "/news-generator",
        method="POST",
        data={
            "action": "use_custom_title",
            "custom_title": "  Serie A Matchday 12 Schedule and Odds  ",
            "keyword": "",
            "link_url[]": ["https://en.legaseriea.it/serie-a/fixtures-results"],
            "include_money_site": "1",
            "article_links_json": json.dumps([{"type": "internal", "text": "serie a guide", "url": "https://site.test/guide"}]),
        },
    ):
        news_controller._handle_generate_titles(state)

    assert state["error"] is None
    assert state["custom_title"] == "Serie A Matchday 12 Schedule and Odds"
    assert state["selected_title"] == "Serie A Matchday 12 Schedule and Odds"
    assert state["titles"] == ["Serie A Matchday 12 Schedule and Odds"]
    assert state["focus_keyword"] == "Serie A Matchday 12 Schedule and Odds"
    assert state["links"] == [{"text": "", "url": "https://en.legaseriea.it/serie-a/fixtures-results", "type": "reference"}]
    assert state["include_money_site"] is True
    assert state["article_links"] == [{"type": "internal", "text": "serie a guide", "url": "https://site.test/guide"}]


def test_news_empty_custom_title_is_rejected():
    app = Flask(__name__)
    state = news_controller._initial_state()
    with app.test_request_context(
        "/news-generator",
        method="POST",
        data={"action": "use_custom_title", "custom_title": "   ", "keyword": "serie a"},
    ):
        news_controller._handle_generate_titles(state)
    assert state["error"] == "Please enter a custom title."


def test_news_generator_route_renders_step1_custom_title_and_opens_step2(monkeypatch):
    monkeypatch.setattr(news_controller, "get_provider", lambda: (_ for _ in ()).throw(AssertionError("AI should not run")))
    repo_root = Path(__file__).resolve().parents[1]
    app = Flask(__name__, template_folder=str(repo_root / "templates"), static_folder=str(repo_root / "static"))
    app.testing = True
    app.add_url_rule("/news-generator", view_func=news_controller.news_generator, methods=["GET", "POST"])
    client = app.test_client()

    get_res = client.get("/news-generator")
    assert get_res.status_code == 200
    get_html = get_res.get_data(as_text=True)
    assert "Custom title (optional)" in get_html
    assert 'name="action" value="generate_titles"' in get_html
    assert 'name="action" value="use_custom_title"' in get_html

    post_res = client.post(
        "/news-generator",
        data={
            "action": "use_custom_title",
            "custom_title": "  My Custom News Title  ",
            "keyword": "serie a",
        },
    )
    assert post_res.status_code == 200
    post_html = post_res.get_data(as_text=True)
    assert "Custom title selected. Continue with news generation below." in post_html
    assert 'id="customTitleRadio"' in post_html
    assert 'value="My Custom News Title"' in post_html
    assert 'id="contentForm"' in post_html


def test_news_generate_titles_clears_stale_custom_title_before_ai_titles(monkeypatch):
    monkeypatch.setattr(news_controller, "get_provider", lambda: object())
    monkeypatch.setattr(news_controller, "get_brand_context", lambda brand: "")
    monkeypatch.setattr(news_controller, "generate_news_titles", lambda *args, **kwargs: ["AI Generated Headline"])
    for name in ("publish_generation_prompt", "publish_generation_status", "publish_generation_draft", "clear_generation_status"):
        monkeypatch.setattr(news_controller, name, lambda *args, **kwargs: None)

    app = Flask(__name__)
    state = news_controller._initial_state()
    with app.test_request_context(
        "/news-generator",
        method="POST",
        data={
            "action": "generate_titles",
            "custom_title": "Old typed custom title",
            "keyword": "serie a",
        },
    ):
        news_controller._handle_generate_titles(state)

    assert state["custom_title"] == ""
    assert state["selected_title"] == ""
    assert state["titles"] == ["AI Generated Headline"]


def test_news_prompts_and_revision_allow_and_convert_tables(monkeypatch):
    from prompts.news import build_news_content_prompt
    from prompts.revisions import build_scoped_content_revision_prompt

    prompt = build_news_content_prompt(
        title="Serie A Matchday 12 Schedule",
        keyword="serie a fixtures",
    )
    revision_prompt = build_scoped_content_revision_prompt(
        title="Serie A Matchday 12 Schedule",
        existing_content="<p>Intro</p>",
        change_request="Add a match schedule table if needed",
    )
    assert "Article table formatting:" in prompt
    assert "schedules, fixtures" in prompt
    assert "Article table formatting:" in revision_prompt

    class TableProvider:
        def __init__(self, payload):
            self.payload = payload

        def generate_json(self, _prompt):
            return self.payload

    monkeypatch.setenv("GENERATION_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("GENERATION_RETRY_DELAY_SECONDS", "0")
    monkeypatch.setattr(news_controller, "get_brand_context", lambda brand: "")
    monkeypatch.setattr(news_controller, "get_blog_word_limits", lambda: (800, 1400))
    monkeypatch.setattr(news_generator, "build_web_research_context", lambda *args, **kwargs: "Verified facts.")
    monkeypatch.setattr(news_controller, "generate_news_tags", lambda *args, **kwargs: ["serie a"])
    monkeypatch.setattr(news_controller, "record_generation", lambda **kwargs: 1)
    for name in ("publish_generation_prompt", "publish_generation_status", "publish_generation_draft", "clear_generation_status"):
        monkeypatch.setattr(news_controller, name, lambda *args, **kwargs: None)

    markdown_article = (
        _article("schedule", 900)
        + "\n\n## Matchday 12 Table\n\n| Match | Date | Time |\n| --- | --- | --- |\n| Como vs Cagliari | Sat, 21 Nov | 14:00 |\n"
    )
    monkeypatch.setattr(news_controller, "get_provider", lambda: TableProvider(json.dumps({"content": markdown_article})))

    app = Flask(__name__)
    state = news_controller._initial_state()
    with app.test_request_context(
        "/news-generator",
        method="POST",
        data={"selected_title": "Serie A Matchday 12 Schedule", "keyword": "serie a"},
    ):
        news_controller._handle_generate_news_piece(state, "generate_content")

    assert "<table><thead><tr><th scope=\"col\">Match</th><th scope=\"col\">Date</th><th scope=\"col\">Time</th></tr></thead><tbody><tr><td>Como vs Cagliari</td><td>Sat, 21 Nov</td><td>14:00</td></tr></tbody></table>" in state["content"]

    revised_payload = json.dumps({
        "content": (
            "<h2>Updated Schedule</h2>\n"
            "| Match | Kickoff |\n"
            "| -- | -- |\n"
            "| Lazio vs Lecce | 14:00 |\n"
            "<p>More updates follow.</p>"
        )
    })
    monkeypatch.setattr(news_controller, "get_provider", lambda: TableProvider(revised_payload))
    state = news_controller._initial_state()
    with app.test_request_context(
        "/news-generator",
        method="POST",
        data={
            "selected_title": "Serie A Matchday 12 Schedule",
            "keyword": "serie a",
            "content_html": "<p>Original copy.</p>",
            "change_request": "Create a match schedule table",
        },
    ):
        news_controller._handle_generate_news_piece(state, "generate_content")

    assert "<table><thead><tr><th scope=\"col\">Match</th><th scope=\"col\">Kickoff</th></tr></thead><tbody><tr><td>Lazio vs Lecce</td><td>14:00</td></tr></tbody></table>" in state["content"]
    assert "<p>More updates follow.</p>" in state["content"]
