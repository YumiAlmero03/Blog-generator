from app import create_app
from app.controllers import blog_controller


def test_hydrate_blog_state_allows_blank_meta_description_with_options():
    app = create_app()
    state = {
        "meta_description": "",
    }

    with app.test_request_context(
        "/",
        method="POST",
        data={
            "selected_title": "Useful Blog Title",
            "keyword": "sample keyword",
            "language": "English",
            "titles_json": '["Useful Blog Title"]',
            "meta_descriptions_json": '[{"text":"Generated meta description","character_count":26}]',
            "meta_description_choice": "",
        },
    ):
        selected = blog_controller._hydrate_blog_generation_state(state)

    assert selected == ""
    assert state["meta_description"] == ""


def test_hydrate_blog_state_reads_suggested_h2s():
    app = create_app()
    state = {
        "meta_description": "",
    }

    with app.test_request_context(
        "/",
        method="POST",
        data={
            "selected_title": "Useful Blog Title",
            "keyword": "sample keyword",
            "supporting_keyword": "secondary keyword",
            "suggested_h2s": "First Main Section\nSecond Main Section",
            "language": "English",
            "titles_json": '["Useful Blog Title"]',
            "meta_descriptions_json": "[]",
            "meta_description_choice": "",
        },
    ):
        blog_controller._hydrate_blog_generation_state(state)

    assert state["suggested_h2s"] == "First Main Section\nSecond Main Section"


def test_generate_all_blog_creates_article_pieces(monkeypatch):
    calls = {}
    recorded = {}
    monkeypatch.setattr(blog_controller, "get_provider", lambda: object())
    monkeypatch.setattr(blog_controller, "upsert_brand", lambda brand: calls.setdefault("upsert_brand", brand))
    monkeypatch.setattr(blog_controller, "get_setting", lambda key, default="": "")
    monkeypatch.setattr(blog_controller, "get_blog_word_limits", lambda: (80, 140))
    monkeypatch.setattr(blog_controller, "get_brand_context", lambda brand: "Brand context")
    monkeypatch.setattr(blog_controller, "clear_generation_status", lambda token: calls.setdefault("clear_token", token))

    def fake_generate_content(*args, **kwargs):
        calls["content"] = kwargs
        return "<p>Generated article body with enough words for this focused controller test.</p>"

    def fake_generate_meta_descriptions(*args, **kwargs):
        calls["meta"] = kwargs
        return [{"text": "Generated meta description for the blog article.", "character_count": 49}]

    def fake_generate_blog_visual_ideas(*args, **kwargs):
        calls["visual"] = kwargs
        return ["Visual idea one", "Visual idea two"]

    def fake_generate_ai_content_tags(*args, **kwargs):
        calls["tags"] = kwargs
        return ["tag one", "tag two"]

    def fake_record_generation(**kwargs):
        recorded.update(kwargs)
        return 77

    monkeypatch.setattr(blog_controller, "generate_content", fake_generate_content)
    monkeypatch.setattr(blog_controller, "generate_meta_descriptions", fake_generate_meta_descriptions)
    monkeypatch.setattr(blog_controller, "generate_blog_visual_ideas", fake_generate_blog_visual_ideas)
    monkeypatch.setattr(blog_controller, "generate_ai_content_tags", fake_generate_ai_content_tags)
    monkeypatch.setattr(blog_controller, "analyze_generated_content", lambda *args, **kwargs: {"word_count": 90})
    monkeypatch.setattr(blog_controller, "record_generation", fake_record_generation)
    monkeypatch.setattr(blog_controller, "record_blog", lambda **kwargs: calls.setdefault("record_blog", kwargs))

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/",
        data={
            "action": "generate_all",
            "selected_title": "Useful Blog Title",
            "keyword": "sample keyword",
            "brand": "Example Brand",
            "supporting_keyword": "secondary keyword",
            "suggested_h2s": "First Main Section\nSecond Main Section",
            "language": "English",
            "tone": "natural",
            "titles_json": '["Useful Blog Title"]',
            "meta_descriptions_json": "[]",
            "tags_json": "[]",
        },
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert calls["content"]["suggested_h2s"] == "First Main Section\nSecond Main Section"
    assert calls["meta"]["title"] == "Useful Blog Title"
    assert calls["visual"]["count"] == 2
    assert calls["tags"]["content"].startswith("<p>Generated article")
    assert recorded["history_id"] == ""
    assert recorded["prompt_inputs"]["suggested_h2s"] == "First Main Section\nSecond Main Section"
    assert "Generated article body" in html
    assert "Generated meta description" in html
    assert "Visual idea one" in html
    assert "tag one" in html
