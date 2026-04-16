import os


PROVIDER = os.getenv("PROVIDER", "ollama").strip() or "ollama"   # ollama | openai | gemini
MODEL = os.getenv("MODEL", "qwen3:8b").strip() or "qwen3:8b"   # change depending on provider

# Examples:
# OpenAI: "gpt-5.4-mini"
# Gemini: "gemini-3-flash-preview"
# Ollama: "qwen3:8b"
