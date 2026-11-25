import json
from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError, APITimeoutError, RateLimitError

import main as cli_main
from app.services.provider_service import (
    JSON_RETRY_INSTRUCTION,
    RetryingJsonProvider,
    generation_error_message,
    get_provider,
)
from generators.title_generator import generate_titles
from providers.base import ProviderError
from providers.openrouter_provider import OPENROUTER_BASE_URL, OpenRouterProvider
from utils import extract_json_string


class SequenceProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        return self.responses.pop(0)


class FakeOpenAIClient:
    def __init__(self, *, api_key, base_url, timeout, max_retries, handler):
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.calls = []
        self._handler = handler
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create_completion)
        )

    def _create_completion(self, **kwargs):
        self.calls.append(kwargs)
        return self._handler(**kwargs)


def _mock_chat_response(content, error=None, reasoning=None):
    if content is None and reasoning is None:
        choices = []
    else:
        choices = [
            SimpleNamespace(
                message=SimpleNamespace(content=content, reasoning=reasoning)
            )
        ]
    return SimpleNamespace(choices=choices, error=error)


def test_retrying_json_provider_reruns_invalid_json(monkeypatch):
    monkeypatch.setenv("JSON_GENERATION_ATTEMPTS", "2")
    provider = SequenceProvider(
        [
            "not valid json",
            json.dumps({"title": "Valid JSON"}),
        ]
    )

    result = RetryingJsonProvider(provider).generate_json("Return JSON.")

    assert json.loads(result) == {"title": "Valid JSON"}
    assert len(provider.prompts) == 2
    assert JSON_RETRY_INSTRUCTION.strip() in provider.prompts[1]


def test_retrying_json_provider_raises_after_configured_attempts(monkeypatch):
    monkeypatch.setenv("JSON_GENERATION_ATTEMPTS", "1")
    provider = SequenceProvider(["still not valid json"])

    with pytest.raises(ValueError, match="Could not parse JSON from model output."):
        RetryingJsonProvider(provider).generate_json("Return JSON.")

    assert len(provider.prompts) == 1


def test_openrouter_provider_uses_openai_sdk_base_url_and_default_model(monkeypatch):
    created_clients = []

    def fake_openai(**kwargs):
        client = FakeOpenAIClient(
            **kwargs,
            handler=lambda **_kw: _mock_chat_response('{"titles": ["Hello World"]}'),
        )
        created_clients.append(client)
        return client

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    monkeypatch.setattr("providers.openrouter_provider.OpenAI", fake_openai)

    provider = OpenRouterProvider()
    output = provider.generate_json("Generate JSON object")

    assert provider.model == "baidu/ernie-5.5-flash-preview:free"
    assert len(created_clients) == 1
    client = created_clients[0]
    assert client.api_key == "test-openrouter-key-not-real"
    assert client.base_url == OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"
    assert client.max_retries == 0
    assert len(client.calls) == 1
    call_kwargs = client.calls[0]
    assert call_kwargs["model"] == "baidu/ernie-5.5-flash-preview:free"
    assert call_kwargs["extra_body"] == {"reasoning": {"enabled": True, "exclude": True}}
    assert "response_format" not in call_kwargs
    assert json.loads(extract_json_string(output)) == {"titles": ["Hello World"]}


def test_openrouter_provider_supports_json_objects_and_json_arrays(monkeypatch):
    responses = [
        '```json\n{"title": "Object Output"}\n```',
        'Here is the array:\n[{"keyword": "alpha"}, {"keyword": "beta"}]',
    ]

    def completion_without_mandatory_reasoning(**kwargs):
        assert kwargs["extra_body"] == {"reasoning": {"enabled": False}}
        return _mock_chat_response(responses.pop(0))

    def fake_openai(**kwargs):
        return FakeOpenAIClient(
            **kwargs,
            handler=completion_without_mandatory_reasoning,
        )

    monkeypatch.setenv("PROVIDER", "openrouter")
    monkeypatch.setenv("MODEL", "google/gemma-4-31b-it:free")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    monkeypatch.setattr("providers.openrouter_provider.OpenAI", fake_openai)

    provider = get_provider()
    obj_raw = provider.generate_json("Return object")
    arr_raw = provider.generate_json("Return array")

    assert json.loads(extract_json_string(obj_raw)) == {"title": "Object Output"}
    assert json.loads(extract_json_string(arr_raw)) == [
        {"keyword": "alpha"},
        {"keyword": "beta"},
    ]


def test_openrouter_provider_missing_api_key_raises_provider_error(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ProviderError, match="OPENROUTER_API_KEY is missing"):
        OpenRouterProvider()


def test_openrouter_provider_handles_rate_limit_429(monkeypatch):
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(
        429,
        request=request,
        json={"error": {"message": "Rate limit exceeded: free-models-per-day"}},
    )

    def raise_rate_limit(**_kwargs):
        raise RateLimitError(
            "Rate limit exceeded",
            response=response,
            body={"error": {"message": "Rate limit exceeded: free-models-per-day"}},
        )

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    monkeypatch.setattr(
        "providers.openrouter_provider.OpenAI",
        lambda **kwargs: FakeOpenAIClient(**kwargs, handler=raise_rate_limit),
    )

    provider = OpenRouterProvider()
    with pytest.raises(ProviderError, match="HTTP 429") as exc_info:
        provider.generate_json("Return JSON")

    assert "free-models-per-day" in generation_error_message("Default error", exc_info.value)


def test_openrouter_provider_handles_api_errors_and_timeouts(monkeypatch):
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(
        502,
        request=request,
        json={"error": {"message": "Upstream provider unavailable"}},
    )

    def raise_api_error(**_kwargs):
        raise APIStatusError(
            "Bad gateway",
            response=response,
            body={"error": {"message": "Upstream provider unavailable"}},
        )

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    monkeypatch.setattr(
        "providers.openrouter_provider.OpenAI",
        lambda **kwargs: FakeOpenAIClient(**kwargs, handler=raise_api_error),
    )

    provider = OpenRouterProvider()
    with pytest.raises(ProviderError, match="HTTP 502"):
        provider.generate_json("Return JSON")

    def raise_timeout(**_kwargs):
        raise APITimeoutError(request=request)

    monkeypatch.setattr(
        "providers.openrouter_provider.OpenAI",
        lambda **kwargs: FakeOpenAIClient(**kwargs, handler=raise_timeout),
    )
    timeout_provider = OpenRouterProvider()
    with pytest.raises(ProviderError, match="timed out"):
        timeout_provider.generate_json("Return JSON")


def test_openrouter_provider_handles_empty_output_and_invalid_json_without_extra_retries(monkeypatch):
    monkeypatch.setenv("PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key-not-real")
    monkeypatch.delenv("JSON_GENERATION_ATTEMPTS", raising=False)

    monkeypatch.setattr(
        "providers.openrouter_provider.OpenAI",
        lambda **kwargs: FakeOpenAIClient(
            **kwargs,
            handler=lambda **_kw: _mock_chat_response("   "),
        ),
    )
    empty_provider = get_provider()
    with pytest.raises(ProviderError, match="empty response"):
        empty_provider.generate_json("Return JSON")

    created_clients = []

    def fake_invalid_json_openai(**kwargs):
        client = FakeOpenAIClient(
            **kwargs,
            handler=lambda **_kw: _mock_chat_response("plain text without json"),
        )
        created_clients.append(client)
        return client

    monkeypatch.setattr("providers.openrouter_provider.OpenAI", fake_invalid_json_openai)
    invalid_json_provider = get_provider()
    with pytest.raises(ValueError, match="Could not parse JSON from model output."):
        invalid_json_provider.generate_json("Return JSON")

    assert len(created_clients[0].calls) == 1

    monkeypatch.setattr(
        "providers.openrouter_provider.OpenAI",
        lambda **kwargs: FakeOpenAIClient(
            **kwargs,
            handler=lambda **_kw: _mock_chat_response(
                "",
                reasoning='Drafting output:\n{"titles": ["Recovered From Reasoning"]}',
            ),
        ),
    )
    reasoning_fallback_provider = get_provider()
    recovered = reasoning_fallback_provider.generate_json("Return JSON")
    assert json.loads(extract_json_string(recovered)) == {
        "titles": ["Recovered From Reasoning"]
    }


def test_get_provider_preserves_ollama_openai_and_gemini(monkeypatch):
    monkeypatch.setenv("PROVIDER", "ollama")
    monkeypatch.setenv("MODEL", "qwen3:8b")
    web_provider = get_provider()
    cli_provider = cli_main.get_provider()
    assert type(web_provider.provider).__name__ == "OllamaProvider"
    assert type(cli_provider).__name__ == "OllamaProvider"

    monkeypatch.setenv("PROVIDER", "openai")
    monkeypatch.setenv("MODEL", "gpt-5.4-mini")
    monkeypatch.setattr("providers.openai_provider.OpenAI", lambda **_kw: object())
    assert type(get_provider().provider).__name__ == "OpenAIProvider"
    assert type(cli_main.get_provider()).__name__ == "OpenAIProvider"

    monkeypatch.setenv("PROVIDER", "gemini")
    monkeypatch.setenv("MODEL", "gemini-3-flash-preview")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setattr("providers.gemini_provider.genai.Client", lambda **_kw: object())
    assert type(get_provider().provider).__name__ == "GeminiProvider"
    assert type(cli_main.get_provider()).__name__ == "GeminiProvider"


def test_title_generator_filters_banned_titles_in_python_without_extra_ai_request():
    provider = SequenceProvider(
        [
            json.dumps(
                {
                    "titles": [
                        "Guaranteed Gaming Platform Safety Tips",
                        "How Gaming Platforms Improve Account Safety",
                        "Practical Steps for Player Account Protection",
                    ]
                }
            )
        ]
    )

    titles = generate_titles(provider, keyword="gaming platform safety", count=3)

    assert titles == [
        "How Gaming Platforms Improve Account Safety",
        "Practical Steps for Player Account Protection",
    ]
    assert len(provider.prompts) == 1
