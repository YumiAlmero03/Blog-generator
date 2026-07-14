import os


def _load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as env_file:
        for line in env_file:
            cleaned = line.strip()
            if not cleaned or cleaned.startswith("#") or "=" not in cleaned:
                continue
            key, value = cleaned.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = value.strip().strip('"').strip("'")


_load_dotenv()

PROVIDER = os.getenv("PROVIDER", "ollama").strip() or "ollama"   # ollama | openai | gemini
# MODEL = os.getenv("MODEL", "qwen3:8b").strip() or "qwen3.5:8b"   # change depending on provider
MODEL = "qwen3.5:9b"   # change depending on provider
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "").strip()
OLLAMA_WEB_SEARCH_ENABLED = os.getenv("OLLAMA_WEB_SEARCH_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
OLLAMA_WEB_SEARCH_MAX_RESULTS = min(10, max(1, int(os.getenv("OLLAMA_WEB_SEARCH_MAX_RESULTS", "5") or 5)))

# Examples:
# OpenAI: "gpt-5.4-mini"
# Gemini: "gemini-3-flash-preview"
# Ollama: "qwen3.5:8b"
