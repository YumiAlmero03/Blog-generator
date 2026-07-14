import json

from app.services import ollama_web_search_service as service


def test_search_web_uses_saved_settings(monkeypatch):
    settings = {
        service.OLLAMA_API_KEY_SETTING: "saved-key",
        service.OLLAMA_WEB_SEARCH_ENABLED_SETTING: "true",
        service.OLLAMA_WEB_SEARCH_MAX_RESULTS_SETTING: "12",
    }
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size):
            return json.dumps(
                {
                    "results": [
                        {
                            "title": "Current result",
                            "url": "https://example.com/current",
                            "content": "Fresh web context",
                        }
                    ]
                }
            ).encode("utf-8")

    def fake_get_setting(key, default=""):
        return settings.get(key, default)

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(service, "get_setting", fake_get_setting)
    monkeypatch.setattr(service, "urlopen", fake_urlopen)

    results = service.search_web("latest seo news")

    assert results == [
        {
            "title": "Current result",
            "url": "https://example.com/current",
            "content": "Fresh web context",
        }
    ]
    assert captured["headers"]["Authorization"] == "Bearer saved-key"
    assert captured["payload"] == {"query": "latest seo news", "max_results": 10}
    assert captured["timeout"] == 20


def test_web_search_disabled_without_saved_or_env_key(monkeypatch):
    monkeypatch.setattr(service, "get_setting", lambda key, default="": "")
    monkeypatch.setattr(service.config, "OLLAMA_API_KEY", "")

    assert service.ollama_web_search_enabled() is False
