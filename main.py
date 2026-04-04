from config import PROVIDER, MODEL
from generators.title_generator import generate_titles

from providers.ollama_provider import OllamaProvider
from providers.openai_provider import OpenAIProvider
from providers.gemini_provider import GeminiProvider

def get_provider():
    if PROVIDER == "ollama":
        return OllamaProvider(MODEL)
    elif PROVIDER == "openai":
        return OpenAIProvider(MODEL)
    elif PROVIDER == "gemini":
        return GeminiProvider(MODEL)
    else:
        raise ValueError(f"Unsupported provider: {PROVIDER}")

def main():
    keyword = input("Enter keyword/topic: ").strip()
    tone = input("Enter tone (default natural): ").strip() or "natural"

    provider = get_provider()
    titles = generate_titles(provider, keyword=keyword, tone=tone, count=10)

    print("\n10 title variants:\n")
    for i, title in enumerate(titles, 1):
        print(f"{i}. {title}")

if __name__ == "__main__":
    main()