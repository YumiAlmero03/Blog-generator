import json

import pytest

from app.services.provider_service import JSON_RETRY_INSTRUCTION, RetryingJsonProvider


class SequenceProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        return self.responses.pop(0)


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
