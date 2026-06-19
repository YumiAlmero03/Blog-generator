import json

from app.services import keyword_suggestion_service
from app.services.keyword_suggestion_service import fetch_google_autocomplete_keywords, generate_keyword_suggestions


class FakeProvider:
    def generate_json(self, prompt):
        return json.dumps({
            "keywords": [
                {
                    "keyword": "football predictions",
                    "intent": "informational",
                    "difficulty": "medium",
                    "difficulty_score": 45,
                    "estimated_monthly_searches": "1K-10K",
                    "content_angle": "Prediction guide",
                    "notes": "Useful for evergreen content",
                },
                {
                    "keyword": "football predictions",
                    "intent": "bad",
                    "difficulty": "bad",
                    "difficulty_score": 999,
                    "estimated_monthly_searches": "",
                    "content_angle": "",
                    "notes": "",
                },
            ]
        })


def test_fetch_google_autocomplete_keywords_parses_suggestions(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'["football", ["football scores", "football fixtures"]]'

    monkeypatch.setattr(keyword_suggestion_service, "urlopen", lambda request, timeout: FakeResponse())

    suggestions = fetch_google_autocomplete_keywords("football")

    assert "football scores" in suggestions
    assert "football fixtures" in suggestions


def test_generate_keyword_suggestions_normalizes_model_output(monkeypatch):
    monkeypatch.setattr(keyword_suggestion_service, "fetch_google_autocomplete_keywords", lambda topic: ["football scores"])

    result = generate_keyword_suggestions(FakeProvider(), " football ", count=10)

    assert result["source"] == "Google autocomplete + AI estimates"
    assert result["autocomplete_keywords"] == ["football scores"]
    assert result["keywords"] == [
        {
            "keyword": "football predictions",
            "intent": "informational",
            "difficulty": "medium",
            "difficulty_score": 45,
            "estimated_monthly_searches": "1K-10K",
            "content_angle": "Prediction guide",
            "notes": "Useful for evergreen content",
        }
    ]
