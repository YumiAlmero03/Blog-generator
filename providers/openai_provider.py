from openai import OpenAI
from providers.base import BaseProvider

class OpenAIProvider(BaseProvider):
    def __init__(self, model: str):
        self.model = model
        self.client = OpenAI()

    def generate_json(self, prompt: str) -> str:
        response = self.client.responses.create(
            model=self.model,
            input=prompt
        )
        return response.output_text