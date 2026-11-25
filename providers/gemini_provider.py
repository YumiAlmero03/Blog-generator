import os
from typing import Any

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from config import DEFAULT_GEMINI_MODEL, get_gemini_api_key as _get_env_gemini_api_key
from database import get_setting
from logger import logger
from providers.base import BaseProvider, ProviderError


GEMINI_API_KEY_SETTING = "gemini_api_key"
DEFAULT_TIMEOUT_SECONDS = 240.0
DEFAULT_MAX_OUTPUT_TOKENS = 32768

_MODEL_ALIASES = {
    "gemini pro": "gemini-3.1-pro-preview",
    "gemini-pro": "gemini-3.1-pro-preview",
    "gemini 3 pro": "gemini-3.1-pro-preview",
    "gemini-3-pro": "gemini-3.1-pro-preview",
}

_BLOCKED_FINISH_REASONS = {
    "SAFETY",
    "RECITATION",
    "BLOCKLIST",
    "PROHIBITED_CONTENT",
    "SPII",
    "IMAGE_SAFETY",
    "IMAGE_PROHIBITED_CONTENT",
}


def normalize_gemini_model(model: str = "") -> str:
    """Normalize friendly Gemini model labels without altering explicit API model IDs."""
    cleaned = " ".join(str(model or "").split()).strip()
    if not cleaned:
        return DEFAULT_GEMINI_MODEL
    return _MODEL_ALIASES.get(cleaned.lower(), cleaned)


def resolve_gemini_api_key(explicit_api_key: str | None = None, *, require: bool = True) -> str:
    """Resolve Gemini API key from explicit override, saved settings, or environment/.env."""
    if explicit_api_key is not None:
        resolved = explicit_api_key.strip()
    else:
        env_key = _get_env_gemini_api_key() or os.getenv("GEMINI_API_KEY", "").strip()
        saved_key = _get_saved_gemini_api_key()
        resolved = saved_key or env_key

    if "\r" in resolved or "\n" in resolved:
        raise ProviderError("GEMINI_API_KEY is invalid. Check your environment, .env file, or Settings.")
    if require and not resolved:
        raise ProviderError(
            "GEMINI_API_KEY is missing. Set GEMINI_API_KEY in your environment, .env file, or Settings."
        )
    return resolved


def create_gemini_client(api_key: str, timeout: float = DEFAULT_TIMEOUT_SECONDS):
    """Create a configured google-genai Client with bounded timeout and no hidden retry loops."""
    http_options = _build_http_options(timeout)
    if http_options is not None:
        try:
            return genai.Client(api_key=api_key, http_options=http_options)
        except TypeError as exc:
            if "http_options" not in str(exc):
                raise
    return genai.Client(api_key=api_key)


def extract_gemini_response_text(
    response: Any,
    model: str,
    *,
    action_label: str = "request",
) -> str:
    """Extract non-thought text from a Gemini response or raise an actionable ProviderError."""
    if response is None:
        raise ProviderError(f"Gemini returned an empty response for model '{model}'.")

    prompt_feedback = getattr(response, "prompt_feedback", None)
    block_reason = _enum_name(getattr(prompt_feedback, "block_reason", None))
    if block_reason and block_reason not in {"NONE", "BLOCK_REASON_UNSPECIFIED"}:
        raise ProviderError(
            f"Gemini {action_label} blocked the prompt for model '{model}' ({block_reason}). Try adjusting the topic or instructions."
        )

    candidates = getattr(response, "candidates", None) or []
    finish_reason = ""
    parts_text = []
    if candidates:
        first_candidate = candidates[0]
        finish_reason = _enum_name(getattr(first_candidate, "finish_reason", None))
        content = getattr(first_candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            if isinstance(getattr(part, "thought", None), bool) and part.thought:
                continue
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text:
                parts_text.append(part_text)

    combined = "".join(parts_text)
    if not combined.strip():
        fallback_text = getattr(response, "text", None)
        if isinstance(fallback_text, str) and fallback_text.strip():
            combined = fallback_text

    if not combined.strip():
        if finish_reason in _BLOCKED_FINISH_REASONS:
            raise ProviderError(
                f"Gemini {action_label} blocked output for model '{model}' ({finish_reason}). Try rewording the topic or guidelines."
            )
        if finish_reason == "MAX_TOKENS":
            raise ProviderError(
                f"Gemini {action_label} hit the output token limit before generating text for model '{model}'."
            )
        raise ProviderError(f"Gemini returned an empty response for model '{model}'.")

    if finish_reason == "MAX_TOKENS":
        logger.warning("Gemini %s reached MAX_TOKENS for model %s (%d chars returned)", action_label, model, len(combined))

    return combined


def raise_gemini_provider_error(
    exc: Exception,
    model: str,
    *,
    api_key: str = "",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    operation: str = "API request",
) -> None:
    """Convert google-genai / httpx / network exceptions into user-friendly ProviderError."""
    if isinstance(exc, ProviderError):
        raise exc

    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        raise ProviderError(
            f"Gemini {operation} timed out after {int(timeout)}s for model '{model}'."
        ) from exc

    status_code = _status_code_from_exception(exc)
    detail = _sanitize_detail(_extract_error_detail(exc), api_key=api_key)

    if isinstance(exc, genai_errors.APIError) or status_code is not None:
        if status_code in {401, 403}:
            raise ProviderError(
                f"Gemini API authentication/permission failed (HTTP {status_code}) for model '{model}': "
                f"{detail} Update GEMINI_API_KEY in your .env file or Settings."
            ) from exc
        if status_code == 404:
            raise ProviderError(
                f"Gemini model '{model}' was not found or is no longer available (HTTP 404). "
                f"Try an active model such as 'gemini-3.1-pro-preview' or 'gemini-4-carbon'. Details: {detail}"
            ) from exc
        if status_code == 429:
            raise ProviderError(
                f"Gemini API rate limit or quota exceeded (HTTP 429) for model '{model}': {detail}"
            ) from exc
        if status_code in {408, 504}:
            raise ProviderError(
                f"Gemini {operation} timed out (HTTP {status_code}) for model '{model}': {detail}"
            ) from exc
        if status_code == 400:
            raise ProviderError(
                f"Gemini {operation} was rejected (HTTP 400) for model '{model}': {detail}"
            ) from exc
        if status_code is not None and 500 <= status_code < 600:
            raise ProviderError(
                f"Gemini API is temporarily unavailable (HTTP {status_code}) for model '{model}': {detail}"
            ) from exc
        status_label = f"HTTP {status_code}" if status_code is not None else "API error"
        raise ProviderError(
            f"Gemini {operation} failed ({status_label}) for model '{model}': {detail}"
        ) from exc

    if isinstance(exc, (httpx.HTTPError, OSError)):
        raise ProviderError(
            f"Gemini network error during {operation} for model '{model}': {detail}"
        ) from exc

    raise ProviderError(
        f"Gemini {operation} failed for model '{model}': {detail}"
    ) from exc


class GeminiProvider(BaseProvider):
    """AI JSON generation provider backed by the official Google GenAI SDK."""

    def __init__(
        self,
        model: str = DEFAULT_GEMINI_MODEL,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.model = normalize_gemini_model(model)
        self.timeout = max(5.0, float(timeout or DEFAULT_TIMEOUT_SECONDS))
        self._api_key = resolve_gemini_api_key(api_key, require=True)
        self.client = create_gemini_client(self._api_key, timeout=self.timeout)

    def generate_json(self, prompt: str) -> str:
        config_obj = self._build_generation_config(use_json_mime=True)
        try:
            response = self._request_generate_content(prompt, config_obj)
        except Exception as exc:
            if _should_retry_without_json_mime(exc):
                logger.warning(
                    "Gemini model %s rejected response_mime_type=application/json; retrying once with plain text JSON prompt.",
                    self.model,
                )
                fallback_config = self._build_generation_config(use_json_mime=False)
                try:
                    response = self._request_generate_content(prompt, fallback_config)
                except Exception as retry_exc:
                    raise_gemini_provider_error(
                        retry_exc,
                        self.model,
                        api_key=self._api_key,
                        timeout=self.timeout,
                        operation="writing request",
                    )
            else:
                raise_gemini_provider_error(
                    exc,
                    self.model,
                    api_key=self._api_key,
                    timeout=self.timeout,
                    operation="writing request",
                )

        return extract_gemini_response_text(response, self.model, action_label="writing")

    def _request_generate_content(self, prompt: str, config_obj: Any):
        kwargs: dict[str, Any] = {
            "model": self.model,
            "contents": prompt,
        }
        if config_obj is not None:
            kwargs["config"] = config_obj
        try:
            return self.client.models.generate_content(**kwargs)
        except TypeError as exc:
            if "config" in kwargs and "config" in str(exc):
                return self.client.models.generate_content(model=self.model, contents=prompt)
            raise

    def _build_generation_config(self, *, use_json_mime: bool = True) -> Any:
        config_cls = getattr(types, "GenerateContentConfig", None)
        if config_cls is None:
            return None

        params: dict[str, Any] = {
            "max_output_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
        }
        if use_json_mime:
            params["response_mime_type"] = "application/json"

        temp = _optional_float_env("GEMINI_TEMPERATURE")
        if temp is not None:
            params["temperature"] = temp

        thinking_cfg = _optional_thinking_config()
        if thinking_cfg is not None:
            params["thinking_config"] = thinking_cfg

        return config_cls(**params)


def _get_saved_gemini_api_key() -> str:
    try:
        return get_setting(GEMINI_API_KEY_SETTING, "").strip()
    except Exception as exc:
        logger.warning("Could not load %s setting: %s", GEMINI_API_KEY_SETTING, exc)
        return ""


def _build_http_options(timeout: float):
    http_options_cls = getattr(types, "HttpOptions", None)
    if http_options_cls is None:
        return None
    kwargs: dict[str, Any] = {
        "timeout": max(1000, int(float(timeout) * 1000)),
    }
    retry_cls = getattr(types, "HttpRetryOptions", None)
    if retry_cls is not None:
        kwargs["retry_options"] = retry_cls(attempts=1)
    return http_options_cls(**kwargs)


def _optional_float_env(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return max(0.0, min(2.0, float(raw)))
    except ValueError:
        return None


def _optional_thinking_config():
    level = os.getenv("GEMINI_THINKING_LEVEL", "").strip().upper()
    if not level:
        return None
    thinking_cls = getattr(types, "ThinkingConfig", None)
    if thinking_cls is None:
        return None
    if level in {"MINIMAL", "LOW", "MEDIUM", "HIGH"}:
        try:
            return thinking_cls(thinking_level=level)
        except Exception:
            return None
    return None


def _should_retry_without_json_mime(exc: Exception) -> bool:
    if _status_code_from_exception(exc) != 400:
        return False
    detail = _extract_error_detail(exc).lower()
    return "response_mime_type" in detail or "json mode" in detail or "application/json" in detail


def _status_code_from_exception(exc: Exception) -> int | None:
    code = getattr(exc, "code", None)
    if isinstance(code, int) and code > 0:
        return code
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) and status > 0 else None


def _extract_error_detail(exc: Exception) -> str:
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        error_obj = details.get("error")
        if isinstance(error_obj, dict):
            msg = str(error_obj.get("message") or "").strip()
            if msg:
                return msg
        msg = str(details.get("message") or "").strip()
        if msg:
            return msg
    msg = str(getattr(exc, "message", "") or "").strip()
    if msg:
        return msg
    return str(exc).strip() or type(exc).__name__


def _sanitize_detail(detail: str, api_key: str = "") -> str:
    cleaned = " ".join(str(detail or "").split())
    if api_key:
        cleaned = cleaned.replace(api_key, "[redacted]")
    return cleaned[:400]


def _enum_name(value: Any) -> str:
    if value is None:
        return ""
    name = getattr(value, "name", None)
    if name:
        return str(name).upper()
    text = str(value).strip()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text.upper()
