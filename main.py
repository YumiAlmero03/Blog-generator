from config import get_current_model, get_current_provider
from generators.title_generator import generate_titles


def get_provider():
    provider_name = get_current_provider().lower()
    model_name = get_current_model()
    if provider_name == "openrouter":
        from providers.openrouter_provider import OpenRouterProvider
        return OpenRouterProvider(model_name)
    elif provider_name == "ollama":
        from providers.ollama_provider import OllamaProvider
        return OllamaProvider(model_name)
    elif provider_name == "openai":
        from providers.openai_provider import OpenAIProvider
        return OpenAIProvider(model_name)
    elif provider_name == "gemini":
        from providers.gemini_provider import GeminiProvider
        return GeminiProvider(model_name)
    else:
        raise ValueError(f"Unsupported provider: {provider_name}")

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