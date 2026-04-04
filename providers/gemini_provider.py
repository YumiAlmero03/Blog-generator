import os
from google import genai
from providers.base import BaseProvider

class GeminiProvider(BaseProvider):
    def __init__(self, model: str):
        self.model = model
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def generate_json(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )
        return response.text