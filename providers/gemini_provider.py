import os
from google import genai
from providers.base import BaseProvider

class GeminiProvider(BaseProvider):
    def __init__(self, model: str):
        self.model = model
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set. Set it in your environment before running the app."
            )
        self.client = genai.Client(api_key=api_key)

    def generate_json(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )
        return response.text
