from app import create_app
from app.controllers import blog_rework_controller
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
    assert "Old Brand" in html
    assert "New Brand" in html
    assert "data-background-submit" in html
    assert "Source Content" in html
    assert "source_content_html" in html
    assert "Content Type" in html
    assert "value=\"page\"" in html
    assert "Supporting Keywords" in html
    assert "manual_supporting_keywords" in html
    assert "Rework Blog" in html


def test_generate_blog_rework_orchestrates_blog_pieces(monkeypatch):
    content_kwargs = {}

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
        lambda *args, **kwargs: content_kwargs.update(kwargs) or "<h2>Fresh Section</h2><p>Reworked article content.</p>",
    )
    monkeypatch.setattr(
        blog_rework_generator,
        "generate_ai_content_tags",
        lambda *args, **kwargs: ["source guide", "article rewrite"],
    )

    result = blog_rework_generator.generate_blog_rework(
        FakeProvider(),
        source_url="https://example.com/source",
        old_brand="OldCo",
        brand="NewCo",
        language="English",
    )

    assert result["source_title"] == "Original Source"
    assert result["title"] == "Fresh Source Guide"
    assert result["keyword"] == "source guide"
    assert result["visual"] == "Image idea one\n\nImage idea two"
    assert "Reworked article content" in result["content"]
    assert "Replace every reference to OldCo with NewCo" in content_kwargs["change_request"]


def test_generate_blog_rework_uses_pasted_source_content_when_url_empty(monkeypatch):
    content_kwargs = {}

    def fail_fetch(url):
        raise AssertionError("fetch_url_text should not be called for pasted source content")

    monkeypatch.setattr(blog_rework_generator, "fetch_url_text", fail_fetch)
    monkeypatch.setattr(
        blog_rework_generator,
        "generate_meta_descriptions",
        lambda *args, **kwargs: [{"text": "A helpful meta description for the reworked blog.", "character_count": 49}],
    )
    monkeypatch.setattr(
        blog_rework_generator,
        "generate_blog_visual_ideas",
        lambda *args, **kwargs: ["Image idea one"],
    )
    monkeypatch.setattr(
        blog_rework_generator,
        "generate_content",
        lambda *args, **kwargs: content_kwargs.update(kwargs) or "<p>Reworked article content.</p>",
    )
    monkeypatch.setattr(
        blog_rework_generator,
        "generate_ai_content_tags",
        lambda *args, **kwargs: ["source guide"],
    )

    result = blog_rework_generator.generate_blog_rework(
        FakeProvider(),
        source_url="",
        source_content="<h1>Original Guide</h1><p>Pasted article text about account setup and safer play.</p>",
        language="English",
    )

    assert result["source_url"] == ""
    assert result["source_title"] == "Pasted source article"
    assert result["source_content"]
    assert "Pasted article text" in content_kwargs["change_request"]
    assert content_kwargs["links"] == []


def test_generate_blog_rework_passes_page_type_to_content(monkeypatch):
    content_kwargs = {}
    prompts = []

    class CapturingProvider(FakeProvider):
        def generate_json(self, prompt):
            prompts.append(prompt)
            return super().generate_json(prompt)

    monkeypatch.setattr(
        blog_rework_generator,
        "fetch_url_text",
        lambda url: {"title": "Original Source", "text": "Original article text " * 80},
    )
    monkeypatch.setattr(
        blog_rework_generator,
        "generate_meta_descriptions",
        lambda *args, **kwargs: [{"text": "A helpful meta description for the reworked page.", "character_count": 49}],
    )
    monkeypatch.setattr(
        blog_rework_generator,
        "generate_blog_visual_ideas",
        lambda *args, **kwargs: ["Image idea one"],
    )
    monkeypatch.setattr(
        blog_rework_generator,
        "generate_content",
        lambda *args, **kwargs: content_kwargs.update(kwargs) or "<p>Reworked page content.</p>",
    )
    monkeypatch.setattr(
        blog_rework_generator,
        "generate_ai_content_tags",
        lambda *args, **kwargs: ["source page"],
    )

    result = blog_rework_generator.generate_blog_rework(
        CapturingProvider(),
        source_url="https://example.com/source",
        content_type="page",
        min_words=1000,
        max_words=2000,
        language="English",
    )

    assert result["content_type"] == "page"
    assert "WordPress page" in prompts[0]
    assert "fresh, original WordPress page" in content_kwargs["change_request"]
    assert content_kwargs["min_words"] == 1000
    assert content_kwargs["max_words"] == 2000


def test_generate_blog_rework_uses_manual_supporting_keywords_once_or_twice(monkeypatch):
    content_kwargs = {}

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
        lambda *args, **kwargs: ["Image idea one"],
    )
    monkeypatch.setattr(
        blog_rework_generator,
        "generate_content",
        lambda *args, **kwargs: content_kwargs.update(kwargs) or "<p>Reworked article content.</p>",
    )
    monkeypatch.setattr(
        blog_rework_generator,
        "generate_ai_content_tags",
        lambda *args, **kwargs: ["source guide"],
    )

    result = blog_rework_generator.generate_blog_rework(
        FakeProvider(),
        source_url="https://example.com/source",
        manual_supporting_keywords="safe casino apps, mobile slots",
        language="English",
    )

    assert result["manual_supporting_keywords"] == "safe casino apps, mobile slots"
    assert result["supporting_keyword"] == "article rewrite, safe casino apps, mobile slots"
    assert content_kwargs["supporting_keyword"] == "article rewrite, safe casino apps, mobile slots"
    assert "Use each one no more than once or twice" in content_kwargs["change_request"]
    assert "safe casino apps, mobile slots" in content_kwargs["change_request"]


def test_blog_rework_page_type_uses_page_word_limits(monkeypatch):
    captured = {}

    monkeypatch.setattr(blog_rework_controller, "get_provider", lambda: object())
    monkeypatch.setattr(blog_rework_controller, "get_page_word_limits", lambda: (1000, 2000))
    monkeypatch.setattr(blog_rework_controller, "get_blog_word_limits", lambda: (1300, 1400))
    monkeypatch.setattr(blog_rework_controller, "get_brand_context", lambda brand: "")
    monkeypatch.setattr(blog_rework_controller, "analyze_generated_content", lambda *args, **kwargs: {"word_count": 1000})
    monkeypatch.setattr(blog_rework_controller, "_record_blog_rework", lambda *args, **kwargs: None)
    monkeypatch.setattr(blog_rework_controller, "clear_generation_status", lambda *args, **kwargs: None)

    def fake_generate_blog_rework(*args, **kwargs):
        captured.update(kwargs)
        return {
            "source_url": "",
            "source_content": kwargs.get("source_content", ""),
            "content_type": kwargs.get("content_type", "blog"),
            "manual_supporting_keywords": kwargs.get("manual_supporting_keywords", ""),
            "source_title": "Pasted source article",
            "title": "Generated Rework",
            "keyword": "generated rework",
            "supporting_keyword": "",
            "meta_descriptions": [{"text": "Meta description", "character_count": 16}],
            "meta_description": "Meta description",
            "visual": "",
            "content": "<p>Generated page content.</p>",
            "tag_suggestions": [],
        }

    monkeypatch.setattr(blog_rework_controller, "generate_blog_rework", fake_generate_blog_rework)

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/blog-rework-generator",
        data={
            "action": "generate_rework",
            "source_content_html": "<p>Source content to rework.</p>",
            "rework_content_type": "page",
            "manual_supporting_keywords": "casino guide, app review",
            "language": "English",
        },
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert captured["content_type"] == "page"
    assert captured["manual_supporting_keywords"] == "casino guide, app review"
    assert captured["min_words"] == 1000
    assert captured["max_words"] == 2000
    assert "Generated Rework" in html


def test_generate_rework_brief_includes_old_brand_replacement_rule():
    prompts = []

    class CapturingProvider(FakeProvider):
        def generate_json(self, prompt):
            prompts.append(prompt)
            return super().generate_json(prompt)

    result = blog_rework_generator._generate_rework_brief(
        CapturingProvider(),
        source_url="https://example.com/source",
        source_title="OldCo Guide",
        source_text="OldCo source text",
        old_brand="OldCo",
        brand="NewCo",
        language="English",
    )

    assert result["title"] == "Fresh Source Guide"
    assert "Old brand to replace: OldCo" in prompts[0]
    assert "Brand: NewCo" in prompts[0]
    assert "replace old brand references with the brand" in prompts[0]
