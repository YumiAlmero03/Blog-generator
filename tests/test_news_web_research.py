import json
from urllib.error import HTTPError

import pytest

from app.controllers import news_controller  # Initialize the app's existing import chain.
from generators import news_generator
from providers.base import ProviderError


ARTICLE = (
    "The league published an updated fixture schedule for the coming round. "
    "Supporters can review the confirmed dates before planning their travel.\n\n"
    "## What to watch next\n\n"
    "The supplied announcement lists the participating clubs and venues. "
    "Further changes should be checked against the official publication."
)


class RecordingProvider:
    def __init__(self):
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        return json.dumps({"content": ARTICLE})


def test_news_article_uses_supplied_references_without_outside_search(monkeypatch):
    def unexpected_search(*args, **kwargs):
        raise AssertionError("Reference-backed news must not search for outside facts.")

    monkeypatch.setattr(news_generator, "build_web_research_context", unexpected_search)
    provider = RecordingProvider()
    reference = "Official league announcement: the round starts on 21 November."

    content = news_generator.generate_news_content(
        provider,
        title="League fixture update",
        reference_context=reference,
        min_words=20,
    )

    assert "<h2>What to watch next</h2>" in content
    assert reference in provider.prompts[0]
    assert "only factual source" in provider.prompts[0]


def test_news_article_without_references_uses_fresh_search_context(monkeypatch):
    searches = []
    research = "Current web research: the league published the latest schedule."

    def search(query, **kwargs):
        searches.append(query)
        return research

    monkeypatch.setattr(news_generator, "build_web_research_context", search)
    provider = RecordingProvider()

    news_generator.generate_news_content(
        provider,
        title="League fixture update",
        target_country="Philippines",
        reference_context="  ",
        min_words=20,
    )

    assert searches == ["League fixture update Philippines latest news"]
    assert research in provider.prompts[0]


def test_news_stops_before_writing_when_tavily_is_rate_limited(monkeypatch):
    from app.services import tavily_web_search_service as search_service

    monkeypatch.setenv("PROVIDER", "openrouter")
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "auto")
    monkeypatch.setattr(search_service.config, "get_tavily_api_key", lambda: "test-key")

    def rate_limited(*args, **kwargs):
        raise HTTPError("https://api.tavily.com/search", 429, "Too many requests", {}, None)

    monkeypatch.setattr(search_service, "urlopen", rate_limited)
    provider = RecordingProvider()

    with pytest.raises(ProviderError, match="429"):
        news_generator.generate_news_content(provider, title="League fixture update", min_words=20)

    assert provider.prompts == []


def test_news_without_tavily_key_requires_sources_before_writing(monkeypatch):
    from app.services import tavily_web_search_service as search_service

    monkeypatch.setenv("PROVIDER", "openrouter")
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "auto")
    monkeypatch.setattr(search_service.config, "get_tavily_api_key", lambda: "")
    provider = RecordingProvider()

    with pytest.raises(ProviderError, match="TAVILY_API_KEY"):
        news_generator.generate_news_content(provider, title="League fixture update", min_words=20)

    assert provider.prompts == []
