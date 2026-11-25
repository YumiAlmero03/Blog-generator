import os
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from config import DEFAULT_MODEL, get_openrouter_api_key
from providers.base import BaseProvider, ProviderError


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = DEFAULT_MODEL
DEFAULT_TIMEOUT_SECONDS = 240.0


def _extract_error_detail(exc: Exception) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error_obj = body.get("error")
        if isinstance(error_obj, dict):
            message = str(error_obj.get("message") or "").strip()
            metadata = error_obj.get("metadata")
            raw_meta = ""
            if isinstance(metadata, dict):
                raw_meta = str(metadata.get("raw") or "").strip()
            if message and raw_meta and raw_meta not in message:
                return f"{message} ({raw_meta})"
            if message:
                return message
        elif error_obj:
            return str(error_obj).strip()
    message = str(getattr(exc, "message", "") or exc).strip()
    return message or "Unknown OpenRouter error."


def _extract_message_content(message) -> str:
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
            else:
                text = getattr(item, "text", "") or getattr(item, "content", "") or ""
            if text:
                parts.append(str(text))
        combined = "".join(parts)
        if combined.strip():
            return combined
    reasoning = getattr(message, "reasoning", None)
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning
    return ""


class OpenRouterProvider(BaseProvider):
    def __init__(
        self,
        model: str = DEFAULT_OPENROUTER_MODEL,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.model = (model or "").strip() or DEFAULT_OPENROUTER_MODEL
        resolved_key = (
            api_key.strip()
            if api_key is not None
            else (os.getenv("OPENROUTER_API_KEY", "").strip() or get_openrouter_api_key())
        )
        if not resolved_key:
            raise ProviderError(
                "OPENROUTER_API_KEY is missing. Set OPENROUTER_API_KEY in your environment or .env file."
            )

        self.client = OpenAI(
            api_key=resolved_key,
            base_url=OPENROUTER_BASE_URL,
            timeout=timeout,
            max_retries=0,
        )

    def generate_json(self, prompt: str) -> str:
        reasoning = {"enabled": False}
        if self.model.split(":", 1)[0] == "baidu/ernie-5.5-flash-preview":
            # This endpoint requires reasoning; keep it out of the JSON answer.
            reasoning = {"enabled": True, "exclude": True}
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                temperature=0.7,
                max_tokens=8192,
                extra_body={"reasoning": reasoning},
            )
        except RateLimitError as exc:
            detail = _extract_error_detail(exc)
            raise ProviderError(
                f"OpenRouter rate limit exceeded (HTTP 429) for model '{self.model}': {detail}"
            ) from exc
        except AuthenticationError as exc:
            detail = _extract_error_detail(exc)
            raise ProviderError(
                f"OpenRouter authentication failed for model '{self.model}': {detail}"
            ) from exc
        except APITimeoutError as exc:
            detail = _extract_error_detail(exc)
            raise ProviderError(
                f"OpenRouter request timed out for model '{self.model}': {detail}"
            ) from exc
        except APIConnectionError as exc:
            detail = _extract_error_detail(exc)
            raise ProviderError(
                f"OpenRouter network error for model '{self.model}': {detail}"
            ) from exc
        except APIStatusError as exc:
            status_code = getattr(exc, "status_code", None)
            detail = _extract_error_detail(exc)
            if status_code == 429:
                raise ProviderError(
                    f"OpenRouter rate limit exceeded (HTTP 429) for model '{self.model}': {detail}"
                ) from exc
            raise ProviderError(
                f"OpenRouter API error (HTTP {status_code}) for model '{self.model}': {detail}"
            ) from exc
        except OpenAIError as exc:
            detail = _extract_error_detail(exc)
            raise ProviderError(
                f"OpenRouter request failed for model '{self.model}': {detail}"
            ) from exc
        except TimeoutError as exc:
            raise ProviderError(
                f"OpenRouter request timed out for model '{self.model}': {exc}"
            ) from exc

        error_payload = getattr(response, "error", None)
        if error_payload:
            if isinstance(error_payload, dict):
                code = error_payload.get("code")
                msg = error_payload.get("message") or str(error_payload)
                if str(code) == "429":
                    raise ProviderError(
                        f"OpenRouter rate limit exceeded (HTTP 429) for model '{self.model}': {msg}"
                    )
                raise ProviderError(f"OpenRouter API error for model '{self.model}': {msg}")
            raise ProviderError(f"OpenRouter API error for model '{self.model}': {error_payload}")

        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ProviderError(f"OpenRouter returned an empty response for model '{self.model}'.")

        content = _extract_message_content(getattr(choices[0], "message", None))
        if not content or not content.strip():
            raise ProviderError(f"OpenRouter returned an empty response for model '{self.model}'.")

        return content
