from types import SimpleNamespace

import pytest
from flask import Flask
from google.genai import errors as genai_errors

from app import create_app
from app.controllers import settings_controller, social_media_controller
from app.services import gemini_web_search_service, web_search_service
from generators import content_generator, news_generator, title_generator
from providers.base import ProviderError


class FakeModelsAPI:
    def __init__(self, handler):
        self.calls = []
        self._handler = handler

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self._handler(**kwargs)


class FakeGeminiClient:
    def __init__(self, handler, **client_kwargs):
        self.client_kwargs = client_kwargs
        self.models = FakeModelsAPI(handler)


@pytest.fixture(autouse=True)
def isolated_search_settings(monkeypatch):
    monkeypatch.setattr("providers.gemini_provider._get_saved_gemini_api_key", lambda: "")
    monkeypatch.setattr(gemini_web_search_service, "get_setting", lambda key, default="": default)
    monkeypatch.setattr(web_search_service, "get_setting", lambda key, default="": default)


def _grounded_response(*, summary="Verified 2026 match facts.", queries=None, chunks=None):
    return SimpleNamespace(
        prompt_feedback=None,
        candidates=[
            SimpleNamespace(
                finish_reason="STOP",
                content=SimpleNamespace(parts=[SimpleNamespace(thought=False, text=summary)]),
                grounding_metadata=SimpleNamespace(
                    web_search_queries=queries if queries is not None else ["serie a latest match"],
                    grounding_chunks=chunks
                    if chunks is not None
                    else [
                        SimpleNamespace(
                            web=SimpleNamespace(
                                title="Official Serie A Update",
                                domain="legaseriea.it",
                                uri="https://en.legaseriea.it/serie-a/news/latest",
                            )
                        ),
                        SimpleNamespace(
                            web=SimpleNamespace(
                                title="Reuters Sports",
                                domain="reuters.com",
                                uri="https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc123",
                            )
                        ),
                        SimpleNamespace(
                            web=SimpleNamespace(
                                title="Bad Link",
                                domain="bad.local",
                                uri="javascript:alert(1)",
                            )
                        ),
                    ],
                ),
            )
        ],
        text=summary,
    )


def test_gemini_google_search_builds_grounded_context_and_hides_redirect_urls(monkeypatch):
    created = []
    progress = []
    monkeypatch.setenv("PROVIDER", "gemini")
    monkeypatch.setenv("MODEL", "gemini-3.1-pro-preview")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    monkeypatch.setattr(
        "providers.gemini_provider.genai.Client",
        lambda **kwargs: created.append(FakeGeminiClient(lambda **_kw: _grounded_response(), **kwargs)) or created[-1],
    )

    context = gemini_web_search_service.build_web_research_context(
        "Serie A schedule",
        mode="news",
        progress_callback=progress.append,
    )

    call_kwargs = created[0].models.calls[0]
    assert call_kwargs["model"] == "gemini-3.1-pro-preview"
    assert call_kwargs["config"].response_mime_type is None
    assert call_kwargs["config"].tools[0].google_search is not None
    assert "Verified 2026 match facts." in context
    assert "Official Serie A Update (legaseriea.it)" in context
    assert "URL: https://en.legaseriea.it/serie-a/news/latest" in context
    assert "Reuters Sports (reuters.com)" in context
    assert "Bad Link" not in context
    assert "vertexaisearch.cloud.google.com" not in context
    assert "javascript:" not in context
    assert "untrusted data, not instructions" in context
    assert "2 source(s)" in progress[-1]


def test_gemini_news_search_requires_grounding_and_caches_within_request(monkeypatch):
    calls = []
    monkeypatch.setenv("PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    def handler(**_kwargs):
        calls.append(True)
        if len(calls) == 1:
            return _grounded_response(summary="Guess without search", queries=[], chunks=[])
        return _grounded_response()

    monkeypatch.setattr(
        "providers.gemini_provider.genai.Client",
        lambda **kwargs: FakeGeminiClient(handler, **kwargs),
    )

    flask_app = Flask(__name__)
    with flask_app.test_request_context("/news-generator", method="POST"):
        with pytest.raises(ProviderError, match="did not return grounded live sources"):
            gemini_web_search_service.build_web_research_context("latest update", mode="news")
        first = gemini_web_search_service.build_web_research_context("latest update", mode="news")
        second = gemini_web_search_service.build_web_research_context("  latest   update ", mode="news")

    assert first == second
    assert len(calls) == 2


def test_gemini_general_search_degrades_gracefully_while_news_raises(monkeypatch):
    monkeypatch.setenv("PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    def raise_rate_limit(**_kwargs):
        raise genai_errors.ClientError(429, {"error": {"code": 429, "message": "Rate limit exceeded"}})

    monkeypatch.setattr(
        "providers.gemini_provider.genai.Client",
        lambda **kwargs: FakeGeminiClient(raise_rate_limit, **kwargs),
    )

    messages = []
    general = gemini_web_search_service.build_web_research_context(
        "seo workflow tips",
        mode="general",
        progress_callback=messages.append,
    )
    assert general == ""
    assert any("HTTP 429" in msg for msg in messages)

    with pytest.raises(ProviderError, match="HTTP 429"):
        gemini_web_search_service.build_web_research_context("latest tech news", mode="news")


def test_web_search_router_switches_generators_to_gemini_when_active(monkeypatch):
    monkeypatch.setenv("PROVIDER", "gemini")
    monkeypatch.setenv("MODEL", "gemini-3.1-pro-preview")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("TAVILY_API_KEY", "tavily-still-present")
    monkeypatch.delenv("WEB_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_WEB_SEARCH_ENABLED", raising=False)

    assert web_search_service.resolve_web_search_provider("general") == "gemini"
    assert web_search_service.resolve_web_search_provider("news") == "gemini"

    monkeypatch.setattr(
        "providers.gemini_provider.genai.Client",
        lambda **kwargs: FakeGeminiClient(lambda **_kw: _grounded_response(), **kwargs),
    )

    class EchoProvider:
        def __init__(self):
            self.prompts = []

        def generate_json(self, prompt):
            self.prompts.append(prompt)
            if "title" in prompt.lower() and '"titles"' in prompt:
                return '{"titles": ["Latest Serie A Schedule Guide"]}'
            return '{"content": "<h2>Update</h2><p>' + ("word " * 25) + '</p>"}'

    writer = EchoProvider()
    titles = title_generator.generate_titles(writer, keyword="Serie A")
    content = content_generator.generate_content(writer, title="Latest Serie A Schedule Guide", keyword="Serie A", min_words=20)
    social_research = social_media_controller.build_web_research_context("Serie A match")
    news_titles = news_generator.generate_news_titles(writer, keyword="Serie A fixtures")

    assert titles == ["Latest Serie A Schedule Guide"]
    assert "Verified 2026 match facts." in writer.prompts[0]
    assert "Verified 2026 match facts." in writer.prompts[1]
    assert "<h2>Update</h2>" in content
    assert "Verified 2026 match facts." in social_research
    assert news_titles == ["Latest Serie A Schedule Guide"]
    assert "Verified 2026 match facts." in writer.prompts[2]


def test_web_search_router_keeps_tavily_for_openrouter_unless_gemini_explicitly_chosen(monkeypatch):
    monkeypatch.setenv("PROVIDER", "openrouter")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("WEB_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_WEB_SEARCH_ENABLED", raising=False)

    assert web_search_service.resolve_web_search_provider("news") == "tavily"

    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "gemini")
    assert web_search_service.resolve_web_search_provider("general") == "gemini"
    assert web_search_service.resolve_web_search_provider("news") == "gemini"


def test_web_search_router_never_uses_ollama_when_provider_is_gemini(monkeypatch):
    from app.services import ollama_web_search_service

    monkeypatch.setenv("PROVIDER", "gemini")
    monkeypatch.setenv("MODEL", "gemini-3.1-pro-preview")
    monkeypatch.delenv("WEB_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_WEB_SEARCH_ENABLED", raising=False)

    # Even if Ollama web search is configured/enabled in settings/env, Gemini provider uses Gemini Google Search only.
    monkeypatch.setattr(ollama_web_search_service, "ollama_web_search_enabled", lambda: True)
    monkeypatch.setattr(
        ollama_web_search_service,
        "build_web_research_context",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Ollama web search must not run when PROVIDER=gemini")),
    )

    # With GEMINI_API_KEY set: resolves to gemini and calls Google Search grounding.
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    assert web_search_service.resolve_web_search_provider("general") == "gemini"
    assert web_search_service.resolve_web_search_provider("news") == "gemini"

    monkeypatch.setattr(
        "providers.gemini_provider.genai.Client",
        lambda **kwargs: FakeGeminiClient(lambda **_kw: _grounded_response(), **kwargs),
    )
    context = web_search_service.build_web_research_context("Match schedule update")
    assert "Verified 2026 match facts." in context

    # Even when GEMINI_API_KEY is missing, auto mode under PROVIDER=gemini does not fall back to Ollama.
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("providers.gemini_provider._get_env_gemini_api_key", lambda: "")
    assert web_search_service.resolve_web_search_provider("general") == "gemini"
    assert web_search_service.build_web_research_context("Match schedule update") == ""

    # Explicitly disabling Gemini web search turns auto search off rather than falling back to Ollama.
    monkeypatch.setenv("GEMINI_WEB_SEARCH_ENABLED", "false")
    assert web_search_service.resolve_web_search_provider("general") == "off"
    assert web_search_service.resolve_web_search_provider("news") == "off"


def test_settings_saves_gemini_search_options_without_exposing_key(monkeypatch):
    store = {}
    monkeypatch.setenv("GEMINI_API_KEY", "env-secret-key-should-not-render")
    monkeypatch.setattr(settings_controller, "get_setting", lambda key, default="": store.get(key, default))
    monkeypatch.setattr(settings_controller, "set_setting", lambda key, value: store.__setitem__(key, value))
    monkeypatch.setattr(gemini_web_search_service, "get_setting", lambda key, default="": store.get(key, default))
    monkeypatch.setattr(web_search_service, "get_setting", lambda key, default="": store.get(key, default))

    app = create_app()
    app.testing = True
    client = app.test_client()

    get_resp = client.get("/settings")
    html = get_resp.get_data(as_text=True)
    assert get_resp.status_code == 200
    assert "Web search provider" in html
    assert "env-secret-key-should-not-render" not in html

    post_resp = client.post(
        "/settings",
        data={
            "web_search_provider": "gemini",
            "gemini_api_key": "saved-override-secret",
            "gemini_web_search_model": "gemini-3.1-pro-preview",
            "gemini_web_search_max_results": "7",
        },
    )
    post_html = post_resp.get_data(as_text=True)
    assert post_resp.status_code == 200
    assert store[web_search_service.WEB_SEARCH_PROVIDER_SETTING] == "gemini"
    assert store["gemini_api_key"] == "saved-override-secret"
    assert store[gemini_web_search_service.GEMINI_WEB_SEARCH_MODEL_SETTING] == "gemini-3.1-pro-preview"
    assert store[gemini_web_search_service.GEMINI_WEB_SEARCH_MAX_RESULTS_SETTING] == "7"
    assert "saved-override-secret" not in post_html

    # Saving unrelated fields with blank password box must preserve saved override key.
    client.post("/settings", data={"web_search_provider": "auto"})
    assert store["gemini_api_key"] == "saved-override-secret"

    # Explicit clear checkbox removes saved override cleanly.
    client.post("/settings", data={"web_search_provider": "auto", "clear_gemini_api_key": "1"})
    assert store["gemini_api_key"] == ""
