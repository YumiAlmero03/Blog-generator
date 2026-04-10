from ollama import ResponseError, chat

from providers.base import BaseProvider, ProviderError

class OllamaProvider(BaseProvider):
    def __init__(self, model: str):
        self.model = model

    def generate_json(self, prompt: str) -> str:
        try:
            response = chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                format="json",
                options={
                    "temperature": 0.8
                }
            )
        except ResponseError as exc:
            status = f"status {exc.status_code}" if exc.status_code else "unknown status"
            detail = str(exc).strip()
            if "model failed to load" in detail.lower() or exc.status_code == 500:
                raise ProviderError(
                    f"Ollama could not load model '{self.model}' ({status}). "
                    "Restart Ollama, close other memory-heavy apps, or switch config.py "
                    "to a smaller installed model. Ollama details: "
                    f"{detail}"
                ) from exc
            raise ProviderError(f"Ollama request failed for model '{self.model}' ({status}): {detail}") from exc
        except Exception as exc:
            raise ProviderError(f"Ollama request failed for model '{self.model}': {exc}") from exc

        return response["message"]["content"]
