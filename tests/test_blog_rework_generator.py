from app import create_app
from generators import blog_rework_generator


class FakeProvider:
    def generate_json(self, prompt):
        return '{"title":"Fresh Source Guide","keyword":"source guide","supporting_keyword":"article rewrite"}'


def test_blog_rework_page_renders():
    app = create_app()
    app.testing = True
    response = app.test_client().get("/blog-rework-generator")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Blog Rework Generator" in html
    assert "data-background-submit" in html
    assert "Rework Blog" in html


def test_generate_blog_rework_orchestrates_blog_pieces(monkeypatch):
    monkeypatch.setattr(
        blog_rework_generator,
        "fetch_url_text",
        lambda url: {"title": "Original Source", "text": "Original article text " * 80},
    )
    monkeypatch.setattr(
        blog_rework_generator,
        "generate_meta_descriptions",
        lambda *args, **kwargs: [{"text": "A helpful meta description for the reworked blog.", "character_count": 49}],
    )
    monkeypatch.setattr(
        blog_rework_generator,
        "generate_blog_visual_ideas",
        lambda *args, **kwargs: ["Image idea one", "Image idea two"],
    )
    monkeypatch.setattr(
        blog_rework_generator,
        "generate_content",
        lambda *args, **kwargs: "<h2>Fresh Section</h2><p>Reworked article content.</p>",
    )
    monkeypatch.setattr(
        blog_rework_generator,
        "generate_ai_content_tags",
        lambda *args, **kwargs: ["source guide", "article rewrite"],
    )

    result = blog_rework_generator.generate_blog_rework(
        FakeProvider(),
        source_url="https://example.com/source",
        language="English",
    )

    assert result["source_title"] == "Original Source"
    assert result["title"] == "Fresh Source Guide"
    assert result["keyword"] == "source guide"
    assert result["visual"] == "Image idea one\n\nImage idea two"
    assert "Reworked article content" in result["content"]
