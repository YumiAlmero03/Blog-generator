import os

from config import MODEL, PROVIDER
from logger import logger
from providers.base import ProviderError
from utils import extract_json_string


JSON_RETRY_INSTRUCTION = """

IMPORTANT RETRY REQUIREMENT:
Your previous response could not be parsed as JSON.
Return only one complete, valid JSON object or array.
Do not include markdown fences, comments, explanations, or text outside the JSON.
"""


def generation_error_message(default_message: str, exc: Exception) -> str:
    if isinstance(exc, ProviderError):
        return str(exc)
    if isinstance(exc, ValueError) and str(exc):
        return str(exc)
    return default_message


def get_provider():
    if PROVIDER == "ollama":
        from providers.ollama_provider import OllamaProvider

        return RetryingJsonProvider(OllamaProvider(MODEL))
    if PROVIDER == "openai":
        from providers.openai_provider import OpenAIProvider

        return RetryingJsonProvider(OpenAIProvider(MODEL))
    if PROVIDER == "gemini":
        from providers.gemini_provider import GeminiProvider

        return RetryingJsonProvider(GeminiProvider(MODEL))
    raise ValueError(f"Unsupported provider: {PROVIDER}")


class RetryingJsonProvider:
    def __init__(self, provider):
        self.provider = provider

    def generate_json(self, prompt: str) -> str:
        attempts = _json_retry_attempts()
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            retry_prompt = prompt if attempt == 1 else f"{prompt}{JSON_RETRY_INSTRUCTION}"
            raw = self.provider.generate_json(retry_prompt)
            try:
                extract_json_string(raw)
                return raw
            except ValueError as exc:
                last_error = exc
                logger.warning(
                    "Model returned invalid JSON on attempt %d of %d. Retrying generation.",
                    attempt,
                    attempts,
                )
        raise ValueError("Could not parse JSON from model output.") from last_error


def _json_retry_attempts() -> int:
    raw_value = os.getenv("JSON_GENERATION_ATTEMPTS", "2").strip()
    try:
        return max(1, min(5, int(raw_value)))
    except ValueError:
        return 2
