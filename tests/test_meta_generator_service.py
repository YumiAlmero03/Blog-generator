import json

from app import create_app
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
                        "description": "Explore an online casino guide with practical safety tips, account checks, payment basics, and clearer ways to compare platforms.",
                    },
                    {
                        "title": "Online Casino Guide for Safer Play",
                        "description": "Explore an online casino guide with practical safety tips, account checks, payment basics, and clearer ways to compare platforms.",
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
        count=5,
        language="English",
    )

    assert result["keyword"] == "online casino guide"
    assert result["page_type"] == "Homepage"
    assert len(result["options"]) == 1
    assert result["options"][0]["title_character_count"] == len("Online Casino Guide for Safer Play")
    assert "Keyword: online casino guide" in provider.prompts[0]
    assert "Page type: Homepage" in provider.prompts[0]
    assert "Meta descriptions must be 130-150 characters" in provider.prompts[0]


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
                            "description": "Browse %name% casino guides, updates, and practical insights for safer play, clearer choices, and better planning.",
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


def test_meta_generator_page_renders():
    app = create_app()
    app.testing = True
    response = app.test_client().get("/meta-generator")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Meta Title & Description Generator" in html
    assert "Page Type" in html
    assert "Author Page" in html
    assert 'name="keyword"' not in html
    assert "data-background-submit" in html
    assert "Meta description target: 130-150 characters." in html
    assert "Category Page and Author Page outputs must include %name%." in html
