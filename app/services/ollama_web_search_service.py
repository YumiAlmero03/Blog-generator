import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import config
from database import get_setting
from logger import logger


WEB_SEARCH_URL = "https://ollama.com/api/web_search"
MAX_SNIPPET_CHARS = 900
OLLAMA_API_KEY_SETTING = "ollama_api_key"
OLLAMA_WEB_SEARCH_ENABLED_SETTING = "ollama_web_search_enabled"
OLLAMA_WEB_SEARCH_MAX_RESULTS_SETTING = "ollama_web_search_max_results"


def ollama_web_search_enabled() -> bool:
    return bool(get_ollama_web_search_enabled() and get_ollama_api_key())


def get_ollama_api_key() -> str:
    saved_key = _get_setting(OLLAMA_API_KEY_SETTING, "")
    return saved_key or config.OLLAMA_API_KEY


def get_ollama_web_search_enabled() -> bool:
    saved_value = _get_setting(OLLAMA_WEB_SEARCH_ENABLED_SETTING, "")
    if saved_value:
        return saved_value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(config.OLLAMA_WEB_SEARCH_ENABLED)


def get_ollama_web_search_max_results() -> int:
    saved_value = _get_setting(OLLAMA_WEB_SEARCH_MAX_RESULTS_SETTING, "")
    value = saved_value or str(config.OLLAMA_WEB_SEARCH_MAX_RESULTS)
    try:
        return max(1, min(10, int(value)))
    except (TypeError, ValueError):
        return config.OLLAMA_WEB_SEARCH_MAX_RESULTS


def search_web(query: str, max_results: int | None = None, timeout: int = 20) -> list[dict]:
    cleaned_query = (query or "").strip()
    if not cleaned_query or not ollama_web_search_enabled():
        return []

    api_key = get_ollama_api_key()
    limit = max(1, min(10, int(max_results or get_ollama_web_search_max_results())))
    payload = json.dumps({"query": cleaned_query, "max_results": limit}).encode("utf-8")
    request = Request(
        WEB_SEARCH_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(1_000_000).decode("utf-8", errors="replace")
    except HTTPError as exc:
        logger.warning("Ollama web search failed with HTTP %s for query %r", exc.code, cleaned_query)
        return []
    except URLError as exc:
        logger.warning("Ollama web search failed for query %r: %s", cleaned_query, exc.reason or exc)
        return []
    except Exception as exc:
        logger.warning("Ollama web search failed for query %r: %s", cleaned_query, exc)
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Ollama web search returned non-JSON data for query %r", cleaned_query)
        return []

    results = data.get("results", [])
    if not isinstance(results, list):
        return []
    return [_clean_result(item) for item in results if isinstance(item, dict)][:limit]


def build_web_research_context(query: str, max_results: int | None = None, progress_callback=None) -> str:
    if not ollama_web_search_enabled():
        return ""

    _publish_progress(progress_callback, f"Searching the web with Ollama for: {query}")
    results = search_web(query, max_results=max_results)
    if not results:
        _publish_progress(progress_callback, "Ollama web search returned no usable results; continuing without web context.")
        return ""

    lines = [
        "Current web research from Ollama search:",
        "Use these results as supporting context. Cite or link only URLs that fit naturally and are relevant.",
    ]
    for index, result in enumerate(results, start=1):
        title = result.get("title") or "Untitled result"
        url = result.get("url") or ""
        content = result.get("content") or ""
        lines.append(f"{index}. {title}")
        if url:
            lines.append(f"URL: {url}")
        if content:
            lines.append(f"Snippet: {content}")
    return "\n".join(lines).strip()


def append_web_research_context(prompt: str, query: str, progress_callback=None) -> str:
    web_context = build_web_research_context(query, progress_callback=progress_callback)
    if not web_context:
        return prompt
    return f"{prompt}\n\n{web_context}\n"


def _clean_result(result: dict) -> dict:
    return {
        "title": _clean_text(result.get("title", "")),
        "url": _clean_text(result.get("url", "")),
        "content": _clean_text(result.get("content", ""))[:MAX_SNIPPET_CHARS],
    }


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split())


def _publish_progress(progress_callback, message: str) -> None:
    if not progress_callback:
        return
    try:
        progress_callback(message)
    except Exception:
        logger.exception("web search progress callback failed")


def _get_setting(key: str, default: str = "") -> str:
    try:
        return get_setting(key, default).strip()
    except Exception as exc:
        logger.warning("Could not load setting %s for Ollama web search: %s", key, exc)
        return default
