import os

_LAST_DOTENV_MTIME: float | None = None


def _read_dotenv_values(path: str = ".env") -> dict[str, str]:
    values: dict[str, str] = {}
    if not os.path.exists(path):
        return values
    with open(path, encoding="utf-8") as env_file:
        for line in env_file:
            cleaned = line.strip()
            if not cleaned or cleaned.startswith("#") or "=" not in cleaned:
                continue
            key, value = cleaned.split("=", 1)
            key = key.strip()
            if not key:
                continue
            values[key] = value.strip().strip('"').strip("'")
    return values


def _load_dotenv(path: str = ".env", override: bool = True) -> None:
    global _LAST_DOTENV_MTIME
    if os.path.exists(path):
        try:
            _LAST_DOTENV_MTIME = os.path.getmtime(path)
        except OSError:
            _LAST_DOTENV_MTIME = None
    for key, value in _read_dotenv_values(path).items():
        if not override and key in os.environ:
            continue
        if value or key not in os.environ:
            os.environ[key] = value


def _refresh_dotenv_if_changed(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    try:
        current_mtime = os.path.getmtime(path)
    except OSError:
        return
    if _LAST_DOTENV_MTIME is None or current_mtime != _LAST_DOTENV_MTIME:
        _load_dotenv(path=path, override=True)


_load_dotenv()

DEFAULT_PROVIDER = "openrouter"
DEFAULT_MODEL = "baidu/ernie-5.5-flash-preview:free"
DEFAULT_GEMINI_MODEL = "gemini-3.1-pro-preview"

PROVIDER = os.getenv("PROVIDER", DEFAULT_PROVIDER).strip() or DEFAULT_PROVIDER   # openrouter | ollama | openai | gemini
MODEL = os.getenv("MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL   # change depending on provider
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_WEB_SEARCH_ENABLED = os.getenv("GEMINI_WEB_SEARCH_ENABLED", "").strip()
GEMINI_WEB_SEARCH_MAX_RESULTS = min(10, max(1, int(os.getenv("GEMINI_WEB_SEARCH_MAX_RESULTS", "5") or 5)))
GEMINI_WEB_SEARCH_MODEL = os.getenv("GEMINI_WEB_SEARCH_MODEL", "").strip()
WEB_SEARCH_PROVIDER = os.getenv("WEB_SEARCH_PROVIDER", "auto").strip().lower() or "auto"
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "").strip()
OLLAMA_WEB_SEARCH_ENABLED = os.getenv("OLLAMA_WEB_SEARCH_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
OLLAMA_WEB_SEARCH_MAX_RESULTS = min(10, max(1, int(os.getenv("OLLAMA_WEB_SEARCH_MAX_RESULTS", "5") or 5)))


def get_current_provider() -> str:
    _refresh_dotenv_if_changed()
    return os.getenv("PROVIDER", DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER


def get_current_model() -> str:
    _refresh_dotenv_if_changed()
    configured = os.getenv("MODEL", "").strip()
    if configured:
        return configured
    if os.getenv("PROVIDER", DEFAULT_PROVIDER).strip().lower() == "gemini":
        return DEFAULT_GEMINI_MODEL
    return DEFAULT_MODEL


def get_openrouter_api_key() -> str:
    _refresh_dotenv_if_changed()
    return os.getenv("OPENROUTER_API_KEY", "").strip()


def get_gemini_api_key() -> str:
    _refresh_dotenv_if_changed()
    return os.getenv("GEMINI_API_KEY", "").strip()


def get_gemini_web_search_enabled_raw() -> str:
    _refresh_dotenv_if_changed()
    return os.getenv("GEMINI_WEB_SEARCH_ENABLED", "").strip()


def get_gemini_web_search_max_results() -> int:
    _refresh_dotenv_if_changed()
    try:
        return max(1, min(10, int(os.getenv("GEMINI_WEB_SEARCH_MAX_RESULTS", "5") or 5)))
    except (TypeError, ValueError):
        return 5


def get_gemini_web_search_model() -> str:
    _refresh_dotenv_if_changed()
    return os.getenv("GEMINI_WEB_SEARCH_MODEL", "").strip()


def get_web_search_provider() -> str:
    _refresh_dotenv_if_changed()
    value = os.getenv("WEB_SEARCH_PROVIDER", "auto").strip().lower()
    return value if value in {"auto", "gemini", "ollama", "tavily", "off"} else "auto"


def get_tavily_api_key() -> str:
    _refresh_dotenv_if_changed()
    return os.getenv("TAVILY_API_KEY", "").strip()


def get_tavily_max_results() -> int:
    _refresh_dotenv_if_changed()
    try:
        return max(1, min(10, int(os.getenv("TAVILY_SEARCH_MAX_RESULTS", "5"))))
    except (TypeError, ValueError):
        return 5


def get_tavily_time_range() -> str:
    _refresh_dotenv_if_changed()
    value = os.getenv("TAVILY_SEARCH_TIME_RANGE", "week").strip().lower()
    return value if value in {"day", "week", "month", "year"} else "week"


# Examples:
# OpenRouter: "baidu/ernie-5.5-flash-preview:free"
# OpenAI: "gpt-5.4-mini"
# Gemini: "gemini-3.1-pro-preview"
# Ollama: "bjoernb/gemma4-31b-fast"
