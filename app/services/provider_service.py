from config import MODEL, PROVIDER
from providers.base import ProviderError


def generation_error_message(default_message: str, exc: Exception) -> str:
    if isinstance(exc, ProviderError):
        return str(exc)
    return default_message


def get_provider():
    if PROVIDER == "ollama":
        from providers.ollama_provider import OllamaProvider

        return OllamaProvider(MODEL)
    if PROVIDER == "openai":
        from providers.openai_provider import OpenAIProvider

        return OpenAIProvider(MODEL)
    if PROVIDER == "gemini":
        from providers.gemini_provider import GeminiProvider

        return GeminiProvider(MODEL)
    raise ValueError(f"Unsupported provider: {PROVIDER}")
