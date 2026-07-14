import json

from app import create_app
from app.controllers import tool_controller
from app.services.meta_generator_service import generate_meta_titles_and_descriptions, keyword_from_page_type


class FakeProvider:
    def __init__(self):
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        return json.dumps(
            {
                "options": [
                    {
                        "title": "Online Casino Guide for Safer Play",
                        "description": "Explore an online casino guide with practical safety tips, account checks, payment basics, and clearer ways to compare platforms today.",
                    },
                    {
                        "title": "Online Casino Guide for Safer Play",
                        "description": "Explore an online casino guide with practical safety tips, account checks, payment basics, and clearer ways to compare platforms today.",
                    },
                    {
                        "title": "",
                        "description": "Missing title should be ignored.",
                    },
                ]
            }
        )


def test_generate_meta_titles_and_descriptions_normalizes_options():
    provider = FakeProvider()

    result = generate_meta_titles_and_descriptions(
        provider,
        keyword=" online casino guide ",
        page_type="Homepage",
        brand="Example Brand",
        brand_context="Helpful comparison guides for cautious players.",
        count=5,
        language="English",
    )

    assert result["keyword"] == "online casino guide"
    assert result["page_type"] == "Homepage"
    assert result["brand"] == "Example Brand"
    assert len(result["options"]) == 1
    assert result["options"][0]["title_character_count"] == len("Online Casino Guide for Safer Play")
    assert "Keyword: online casino guide" in provider.prompts[0]
    assert "Page type: Homepage" in provider.prompts[0]
    assert "Brand: Example Brand" in provider.prompts[0]
    assert "Helpful comparison guides for cautious players." in provider.prompts[0]
    assert "Meta descriptions must be strictly 130-150 characters" in provider.prompts[0]


def test_generate_meta_uses_page_type_as_keyword_when_keyword_empty():
    provider = FakeProvider()

    result = generate_meta_titles_and_descriptions(
        provider,
        keyword="",
        page_type="Blog Page",
        count=5,
        language="English",
    )

    assert result["keyword"] == "blog page"
    assert "Keyword: blog page" in provider.prompts[0]
    assert keyword_from_page_type("Author Page") == "author page"


def test_category_and_author_pages_require_dynamic_name_placeholder():
    class DynamicProvider:
        def __init__(self):
            self.prompts = []

        def generate_json(self, prompt):
            self.prompts.append(prompt)
            return json.dumps(
                {
                    "options": [
                        {
                            "title": "%name% Casino Guides and Updates",
                            "description": "Browse %name% casino guides, updates, and practical insights for safer play, clearer choices, and better planning with helpful tips.",
                        },
                        {
                            "title": "Casino Guides and Updates",
                            "description": "Browse casino guides and updates without a dynamic placeholder.",
                        },
                    ]
                }
            )

    provider = DynamicProvider()

    result = generate_meta_titles_and_descriptions(
        provider,
        keyword="",
        page_type="Category Page",
        count=5,
        language="English",
    )

    assert len(result["options"]) == 1
    assert "%name%" in result["options"][0]["title"]
    assert "%name%" in result["options"][0]["description"]
    assert "Use the literal placeholder %name%" in provider.prompts[0]


def test_meta_generator_retries_when_descriptions_miss_strict_range():
    class RetryProvider:
        def __init__(self):
            self.prompts = []
            self.responses = [
                {
                    "options": [
                        {
                            "title": "Online Casino Guide for Safer Play",
                            "description": "Too short for the strict meta description range.",
                        }
                    ]
                },
                {
                    "options": [
                        {
                            "title": "Online Casino Guide for Safer Play",
                            "description": "Explore an online casino guide with practical safety tips, account checks, payment basics, and clearer ways to compare platforms today.",
                        }
                    ]
                },
            ]

        def generate_json(self, prompt):
            self.prompts.append(prompt)
            return json.dumps(self.responses.pop(0))

    provider = RetryProvider()

    result = generate_meta_titles_and_descriptions(
        provider,
        keyword="online casino guide",
        page_type="Homepage",
        count=1,
        language="English",
    )

    assert len(provider.prompts) == 2
    assert "IMPORTANT RETRY REQUIREMENT" in provider.prompts[1]
    assert result["options"][0]["description_character_count"] == 135


def test_meta_generator_page_renders():
    app = create_app()
    app.testing = True
    response = app.test_client().get("/meta-generator")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Meta Title & Description Generator" in html
    assert 'name="brand"' in html
    assert "Page Type" in html
    assert "Author Page" in html
    assert 'name="keyword"' not in html
    assert "data-background-submit" in html
    assert "Meta description target: 130-150 characters." in html
    assert "Category Page and Author Page outputs must include %name%." in html


def test_meta_generator_route_passes_brand_context(monkeypatch):
    captured = {}
    monkeypatch.setattr(tool_controller, "list_brand_names", lambda: ["Example Brand"])
    monkeypatch.setattr(tool_controller, "get_brand_context", lambda brand: f"context for {brand}")
    monkeypatch.setattr(tool_controller, "get_provider", lambda: object())
    monkeypatch.setattr(tool_controller, "publish_generation_status", lambda *args, **kwargs: None)

    def fake_generate_meta_titles_and_descriptions(*args, **kwargs):
        captured.update(kwargs)
        return {
            "keyword": kwargs["keyword"],
            "page_type": kwargs["page_type"],
            "brand": kwargs["brand"],
            "count": kwargs["count"],
            "language": kwargs["language"],
            "options": [
                {
                    "title": "Example Brand Blog Guide",
                    "title_character_count": 24,
                    "description": "Explore useful blog resources from Example Brand with practical guidance, clearer context, and helpful steps for planning better pages.",
                    "description_character_count": 131,
                    "banned_terms": [],
                }
            ],
        }

    monkeypatch.setattr(tool_controller, "generate_meta_titles_and_descriptions", fake_generate_meta_titles_and_descriptions)

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/meta-generator",
        data={
            "brand": "Example Brand",
            "page_type": "Blog Page",
            "language": "English",
            "count": "1",
        },
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert captured["brand"] == "Example Brand"
    assert captured["brand_context"] == "context for Example Brand"
    assert captured["keyword"] == "blog page"
    assert "Blog Page / Example Brand" in html
