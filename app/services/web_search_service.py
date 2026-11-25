import config
from app.services import gemini_web_search_service, ollama_web_search_service, tavily_web_search_service
from database import get_setting
from logger import logger


WEB_SEARCH_PROVIDER_SETTING = "web_search_provider"
VALID_WEB_SEARCH_PROVIDERS = {"auto", "gemini", "ollama", "tavily", "off"}


def get_configured_web_search_provider() -> str:
    """Return configured web search backend preference: auto, gemini, ollama, tavily, or off."""
    saved = _get_setting(WEB_SEARCH_PROVIDER_SETTING, "")
    value = (saved or config.get_web_search_provider()).strip().lower()
    return value if value in VALID_WEB_SEARCH_PROVIDERS else "auto"


def resolve_web_search_provider(use_case: str = "general") -> str:
    """Resolve active web search provider for 'general' (blog/social) or 'news'."""
    configured = get_configured_web_search_provider()
    is_news = (use_case or "general").strip().lower() == "news"

    if configured == "off":
        return "off"
    if configured in {"gemini", "ollama", "tavily"}:
        if configured == "tavily" and not is_news:
            # Tavily can also run for general queries if explicitly chosen by the user.
            return "tavily"
        return configured

    # Automatic routing
    active_provider = config.get_current_provider()
    if active_provider == "gemini":
        if gemini_web_search_service.get_gemini_web_search_enabled() is False:
            return "off"
        return "gemini"

    if is_news:
        if gemini_web_search_service.gemini_web_search_enabled():
            return "gemini"
        return "tavily"

    if gemini_web_search_service.gemini_web_search_enabled():
        return "gemini"
    if ollama_web_search_service.ollama_web_search_enabled():
        return "ollama"
    return "off"


def describe_active_web_search() -> dict[str, str]:
    """Return human-readable active AI provider and resolved search backends for Settings display."""
    labels = {
        "gemini": "Gemini Google Search",
        "ollama": "Ollama Web Search",
        "tavily": "Tavily Search",
        "off": "Off",
    }
    return {
        "ai_provider": config.get_current_provider(),
        "general_search": labels.get(resolve_web_search_provider("general"), "Off"),
        "news_search": labels.get(resolve_web_search_provider("news"), "Off"),
    }


def build_web_research_context(query: str, max_results: int | None = None, progress_callback=None) -> str:
    """Build current web research context for general generators (blog titles, blog content, social posts)."""
    cleaned_query = " ".join(str(query or "").split())
    if not cleaned_query:
        return ""

    backend = resolve_web_search_provider("general")
    if backend == "gemini":
        return gemini_web_search_service.build_web_research_context(
            cleaned_query,
            max_results=max_results,
            progress_callback=progress_callback,
            mode="general",
            raise_on_error=False,
        )
    if backend == "ollama":
        return ollama_web_search_service.build_web_research_context(
            cleaned_query,
            max_results=max_results,
            progress_callback=progress_callback,
        )
    if backend == "tavily":
        try:
            return tavily_web_search_service.build_web_research_context(
                cleaned_query,
                max_results=max_results,
                progress_callback=progress_callback,
            )
        except Exception as exc:
            logger.warning("Tavily general web search skipped: %s", exc)
            _publish_progress(progress_callback, f"Tavily web search skipped ({exc}); continuing without web context.")
            return ""
    return ""


def append_web_research_context(prompt: str, query: str, progress_callback=None) -> str:
    web_context = build_web_research_context(query, progress_callback=progress_callback)
    if not web_context:
        return prompt
    return f"{prompt}\n\n{web_context}\n"


def build_news_web_research_context(query: str, max_results: int | None = None, progress_callback=None) -> str:
    """Build current web research context for News Generator with strict error reporting."""
    cleaned_query = " ".join(str(query or "").split())
    if not cleaned_query:
        return ""

    backend = resolve_web_search_provider("news")
    if backend == "gemini":
        return gemini_web_search_service.build_web_research_context(
            cleaned_query,
            max_results=max_results,
            progress_callback=progress_callback,
            mode="news",
            raise_on_error=True,
            require_grounding=True,
        )
    if backend == "ollama":
        context = ollama_web_search_service.build_web_research_context(
            cleaned_query,
            max_results=max_results,
            progress_callback=progress_callback,
        )
        if not context:
            from providers.base import ProviderError

            raise ProviderError(
                "Ollama web search returned no usable news sources or is missing OLLAMA_API_KEY."
            )
        return context
    if backend == "off":
        from providers.base import ProviderError

        raise ProviderError(
            "Web search is disabled in Settings while no reference news links were supplied."
        )
    return tavily_web_search_service.build_web_research_context(
        cleaned_query,
        max_results=max_results,
        progress_callback=progress_callback,
    )


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
        logger.warning("Could not load setting %s: %s", key, exc)
        return default
