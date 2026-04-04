from ollama import chat
from providers.base import BaseProvider

class OllamaProvider(BaseProvider):
    def __init__(self, model: str):
        self.model = model

    def generate_json(self, prompt: str) -> str:
        response = chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            format="json",
            options={
                "temperature": 0.8
            }
        )
        return response["message"]["content"]