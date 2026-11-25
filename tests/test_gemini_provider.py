import json
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors as genai_errors

import config
from app.services.provider_service import generation_error_message, get_provider
from providers.base import ProviderError
from providers.gemini_provider import DEFAULT_MAX_OUTPUT_TOKENS, GeminiProvider, normalize_gemini_model
from utils import extract_json_string


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
def isolated_gemini_settings(monkeypatch):
    monkeypatch.setattr("providers.gemini_provider._get_saved_gemini_api_key", lambda: "")


def test_gemini_provider_missing_or_multiline_key_raises_provider_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("providers.gemini_provider._get_env_gemini_api_key", lambda: "")

    with pytest.raises(ProviderError, match="GEMINI_API_KEY is missing") as exc_info:
        GeminiProvider("gemini-3.1-pro-preview")

    assert "GEMINI_API_KEY is missing" in generation_error_message("Default error", exc_info.value)

    monkeypatch.setenv("GEMINI_API_KEY", "bad\nkey")
    with pytest.raises(ProviderError, match="GEMINI_API_KEY is invalid"):
        GeminiProvider("gemini-3.1-pro-preview")


def test_config_defaults_to_gemini_pro_when_provider_is_gemini_and_model_unset(monkeypatch):
    monkeypatch.setenv("PROVIDER", "gemini")
    monkeypatch.delenv("MODEL", raising=False)

    assert config.get_current_provider() == "gemini"
    assert config.get_current_model() == "gemini-3.1-pro-preview"

    monkeypatch.setenv("MODEL", "gemini-2.5-pro")
    assert config.get_current_model() == "gemini-2.5-pro"

    assert normalize_gemini_model("Gemini Pro") == "gemini-3.1-pro-preview"
    assert normalize_gemini_model("gemini-2.5-pro") == "gemini-2.5-pro"


def test_gemini_provider_writes_json_configures_pro_headroom_and_excludes_thought_parts(monkeypatch):
    created = []
    monkeypatch.setenv("PROVIDER", "gemini")
    monkeypatch.setenv("MODEL", "gemini-3.1-pro-preview")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    response = SimpleNamespace(
        prompt_feedback=None,
        candidates=[
            SimpleNamespace(
                finish_reason="STOP",
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(thought=True, text='{"internal":"draft"}'),
                        SimpleNamespace(thought=False, text='{"content": "<p>Gemini Pro article</p>"}'),
                    ]
                ),
            )
        ],
        text='{"content": "<p>Gemini Pro article</p>"}',
    )

    def fake_client(**kwargs):
        client = FakeGeminiClient(lambda **_kw: response, **kwargs)
        created.append(client)
        return client

    monkeypatch.setattr("providers.gemini_provider.genai.Client", fake_client)

    provider = get_provider()
    raw = provider.generate_json("Write an article")

    assert json.loads(extract_json_string(raw)) == {"content": "<p>Gemini Pro article</p>"}
    client = created[0]
    assert client.client_kwargs["api_key"] == "test-gemini-key"
    assert client.client_kwargs["http_options"].timeout == 240000
    assert client.client_kwargs["http_options"].retry_options.attempts == 1
    call_kwargs = client.models.calls[0]
    assert call_kwargs["model"] == "gemini-3.1-pro-preview"
    assert call_kwargs["config"].response_mime_type == "application/json"
    assert call_kwargs["config"].max_output_tokens == DEFAULT_MAX_OUTPUT_TOKENS


def test_gemini_provider_retries_without_json_mime_when_model_rejects_it(monkeypatch):
    created = []
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    def handler(**kwargs):
        if kwargs["config"].response_mime_type == "application/json":
            raise genai_errors.ClientError(
                400,
                {"error": {"code": 400, "message": "response_mime_type application/json is unsupported", "status": "INVALID_ARGUMENT"}},
            )
        return SimpleNamespace(text='{"titles": ["Fallback JSON"]}', candidates=[], prompt_feedback=None)

    monkeypatch.setattr(
        "providers.gemini_provider.genai.Client",
        lambda **kwargs: created.append(FakeGeminiClient(handler, **kwargs)) or created[-1],
    )

    provider = GeminiProvider("gemini-2.5-pro")
    raw = provider.generate_json("Generate titles")

    assert json.loads(raw) == {"titles": ["Fallback JSON"]}
    assert len(created[0].models.calls) == 2
    assert created[0].models.calls[0]["config"].response_mime_type == "application/json"
    assert created[0].models.calls[1]["config"].response_mime_type is None


@pytest.mark.parametrize(
    ("code", "message", "expected"),
    [
        (403, "Your API key AIza-secret-123 was reported as leaked.", "HTTP 403"),
        (404, "models/gemini-3-pro-preview is not found", "gemini-3.1-pro-preview"),
        (429, "Quota exceeded for quota metric", "HTTP 429"),
        (503, "The model is overloaded.", "HTTP 503"),
    ],
)
def test_gemini_provider_maps_api_errors_cleanly_without_exposing_key(monkeypatch, code, message, expected):
    secret = "AIza-secret-123"
    monkeypatch.setenv("GEMINI_API_KEY", secret)

    def raise_api_error(**_kwargs):
        exc_cls = genai_errors.ServerError if code >= 500 else genai_errors.ClientError
        raise exc_cls(code, {"error": {"code": code, "message": message, "status": "ERROR"}})

    monkeypatch.setattr(
        "providers.gemini_provider.genai.Client",
        lambda **kwargs: FakeGeminiClient(raise_api_error, **kwargs),
    )

    provider = GeminiProvider("gemini-3.1-pro-preview")
    with pytest.raises(ProviderError, match=expected) as exc_info:
        provider.generate_json("Return JSON")

    assert secret not in str(exc_info.value)


def test_gemini_provider_handles_blocked_empty_and_timeout_responses(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    blocked = SimpleNamespace(
        prompt_feedback=SimpleNamespace(block_reason="SAFETY"),
        candidates=[],
        text=None,
    )
    monkeypatch.setattr(
        "providers.gemini_provider.genai.Client",
        lambda **kwargs: FakeGeminiClient(lambda **_kw: blocked, **kwargs),
    )
    with pytest.raises(ProviderError, match="SAFETY"):
        GeminiProvider("gemini-3.1-pro-preview").generate_json("Return JSON")

    max_tokens_empty = SimpleNamespace(
        prompt_feedback=None,
        candidates=[SimpleNamespace(finish_reason="MAX_TOKENS", content=SimpleNamespace(parts=[]))],
        text=None,
    )
    monkeypatch.setattr(
        "providers.gemini_provider.genai.Client",
        lambda **kwargs: FakeGeminiClient(lambda **_kw: max_tokens_empty, **kwargs),
    )
    with pytest.raises(ProviderError, match="output token limit"):
        GeminiProvider("gemini-3.1-pro-preview").generate_json("Return JSON")

    def raise_timeout(**_kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(
        "providers.gemini_provider.genai.Client",
        lambda **kwargs: FakeGeminiClient(raise_timeout, **kwargs),
    )
    with pytest.raises(ProviderError, match="timed out"):
        GeminiProvider("gemini-3.1-pro-preview", timeout=30).generate_json("Return JSON")
