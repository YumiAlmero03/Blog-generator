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


def test_blog_and_revision_prompts_distribute_links_across_top_middle_and_end():
    from prompts.blog import build_content_prompt
    from prompts.revisions import build_scoped_content_revision_prompt

    links = [
        {"type": "internal", "text": "mobile app setup guide", "url": "https://example.org/setup"},
        {"type": "internal", "text": "account security checklist", "url": "https://example.org/security"},
        {"type": "external", "text": "official platform update", "url": "https://example.org/update"},
    ]
    blog_prompt = build_content_prompt(
        title="How to Set Up Your Account Safely",
        keyword="account setup",
        links=links,
    )
    assert "Target placement: TOP section" in blog_prompt
    assert "Target placement: MIDDLE section" in blog_prompt
    assert "Target placement: END section" in blog_prompt
    assert "Never cluster, group, or dump multiple anchor links together in the final paragraph" in blog_prompt

    revision_prompt = build_scoped_content_revision_prompt(
        title="How to Set Up Your Account Safely",
        existing_content="<p>Intro</p><p>End with all links</p>",
        change_request="distribute or spread out anchor links from top, middle and end of content",
        links=links,
    )
    assert "Target placement: TOP section" in revision_prompt
    assert "Target placement: MIDDLE section" in revision_prompt
    assert "Target placement: END section" in revision_prompt
    assert "FINAL REMINDER BEFORE RETURNING JSON:" in revision_prompt
    assert revision_prompt.rfind("distribute or spread out anchor links") > revision_prompt.find("Existing article content:")


def test_brazilian_portuguese_language_option_and_prompt():
    from app.services.locale_settings import language_options, normalize_language
    from prompts.shared import build_language_instruction

    options = language_options()
    assert "Brazilian Portuguese" in options
    assert normalize_language("brazil portugues") == "Brazilian Portuguese"
    assert normalize_language("Brazilian Portuguese") == "Brazilian Portuguese"
    assert normalize_language("pt-BR") == "Brazilian Portuguese"

    instruction = build_language_instruction("Brazilian Portuguese")
    assert "Brazilian Portuguese" in instruction
    assert "pt-BR" in instruction


def test_visual_image_descriptions_keep_english_with_quoted_selected_language_text():
    from generators.content_generator import generate_blog_visual_ideas
    from generators.social_media_generator import _build_neutral_blog_visual_prompt
    from prompts.news import build_news_visual_prompt
    from prompts.shared import build_visual_language_instruction

    captured = {}

    class FakeProvider:
        def generate_json(self, prompt):
            captured["prompt"] = prompt
            return (
                '{"visuals": ['
                '"Overhead photo of a notebook with the title \\"Guia Completo\\" beside a coffee cup.", '
                '"Minimalist desk setup under soft daylight."]}'
            )

    visuals = generate_blog_visual_ideas(
        FakeProvider(),
        title="Complete Guide",
        keyword="guide",
        language="Brazilian Portuguese",
    )
    blog_prompt = captured["prompt"]
    assert "Write the Visual / Image Descriptions strictly in English" in blog_prompt
    assert 'double quotes ("...")' in blog_prompt
    assert "Brazilian Portuguese" in blog_prompt
    assert "pt-BR" in blog_prompt
    assert "Write visual descriptions in Brazilian Portuguese" not in blog_prompt
    assert visuals == [
        'Overhead photo of a notebook with the title "Guia Completo" beside a coffee cup.',
        "Minimalist desk setup under soft daylight.",
    ]

    news_prompt = build_news_visual_prompt(
        title="Platform Security Update",
        keyword="security",
        language="Tagalog",
    )
    assert "Write the Visual / Image Descriptions strictly in English" in news_prompt
    assert "Write the content in Tagalog" not in news_prompt
    assert "in Tagalog" in news_prompt

    neutral_prompt = _build_neutral_blog_visual_prompt(
        title="Healthy Morning Habits",
        topic="wellness",
        medium={"website_name": "Editorial Hub", "website_type": "blog"},
        language="Taglish",
    )
    assert "Write the Visual / Image Descriptions strictly in English" in neutral_prompt
    assert "Write the content in Taglish" not in neutral_prompt
    assert "in Taglish" in neutral_prompt

    helper_text = build_visual_language_instruction("Brazilian Portuguese")
    assert '\\"Text\\"' in helper_text


def test_blog_page_renders_reference_fields_and_generates_with_reference_url_and_notes(monkeypatch):
    app = create_app()
    app.testing = True
    client = app.test_client()

    get_html = client.get("/").get_data(as_text=True)
    assert 'name="reference_url"' in get_html
    assert 'name="reference_notes"' in get_html

    fetch_calls = []
    prompts = []

    def fake_fetch_reference(links, **kwargs):
        fetch_calls.append((links, kwargs))
        return (
            "Combined reference source.\nMerged extracted content:\nOfficial release states v3.2 launches November 2026 with 40% lower latency.",
            [
                {
                    "url": links[0]["url"],
                    "status": "fetched",
                    "title": "Official Release Notes",
                    "source_label": "Official Release Notes",
                    "character_count": 79,
                    "excerpt": "Official release states v3.2 launches November 2026 with 40% lower latency.",
                    "fetch_method": "browser-fallback",
                }
            ],
        )

    class CapturingProvider:
        def generate_json(self, prompt):
            prompts.append(prompt)
            if '"titles"' in prompt:
                return '{"titles": ["Inside the v3.2 November 2026 Release"]}'
            if '"meta_descriptions"' in prompt:
                desc = "Discover what the v3.2 November 2026 release brings with 40% lower latency and key updates from official notes."
                return f'{{"meta_descriptions": [{{"text": "{desc}", "character_count": {len(desc)}}}]}}'
            if '"visuals"' in prompt:
                return '{"visuals": ["Minimalist dashboard chart showing 40% lower latency metrics.", "Editorial product workflow diagram."]}'
            if '"tags"' in prompt:
                return '{"tags": ["release notes", "v3.2 update", "latency"]}'
            return '{"content": "## Release Overview\\n\\n' + ("Official v3.2 update lowers latency by 40 percent in November 2026. " * 2) + '"}'

    monkeypatch.setattr(blog_controller, "fetch_reference_context", fake_fetch_reference)
    monkeypatch.setattr(blog_controller, "get_provider", lambda: CapturingProvider())
    monkeypatch.setattr(blog_controller, "upsert_brand", lambda *_a, **_kw: None)
    monkeypatch.setattr(blog_controller, "get_brand_context", lambda *_a, **_kw: "")
    monkeypatch.setattr(blog_controller, "get_setting", lambda *_a, **_kw: "")
    monkeypatch.setattr(blog_controller, "get_blog_word_limits", lambda: (15, 140))
    monkeypatch.setattr(blog_controller, "analyze_generated_content", lambda *a, **k: {"word_count": 24})
    monkeypatch.setattr(blog_controller, "record_generation", lambda **_kw: 91)
    monkeypatch.setattr(blog_controller, "record_blog", lambda **_kw: None)

    step1_resp = client.post(
        "/",
        data={
            "action": "generate_titles",
            "keyword": "platform v3.2 update",
            "reference_url": "www.example.com/release-notes",
            "reference_notes": "Focus on developer migration timing.",
        },
    )
    step1_html = step1_resp.get_data(as_text=True)
    assert step1_resp.status_code == 200
    assert len(fetch_calls) == 1
    assert fetch_calls[0][0][0]["url"] == "https://www.example.com/release-notes"
    assert fetch_calls[0][1]["use_browser"] is True
    assert "40% lower latency" in prompts[0]
    assert "Focus on developer migration timing." in prompts[0]
    assert 'value="https://www.example.com/release-notes"' in step1_html
    assert "Focus on developer migration timing.</textarea>" in step1_html
    assert "browser-fallback" in step1_html

    # Step 2 generate_all uses cached reference fetch when reference_fetches_json matches and passes notes cleanly.
    import json
    import time
    cached_fetches = json.dumps(
        [
            {
                "url": "https://www.example.com/release-notes",
                "status": "fetched",
                "title": "Official Release Notes",
                "source_label": "Official Release Notes",
                "character_count": 79,
                "excerpt": "Official release states v3.2 launches November 2026 with 40% lower latency.",
                "fetch_method": "browser-fallback",
                "fetched_at": time.time(),
            }
        ]
    )
    step2_resp = client.post(
        "/",
        data={
            "action": "generate_all",
            "selected_title": "Inside the v3.2 November 2026 Release",
            "keyword": "platform v3.2 update",
            "reference_url": "https://www.example.com/release-notes",
            "reference_notes": "Focus on developer migration timing.",
            "reference_fetches_json": cached_fetches,
            "titles_json": '["Inside the v3.2 November 2026 Release"]',
            "meta_descriptions_json": "[]",
            "tags_json": "[]",
        },
    )
    step2_html = step2_resp.get_data(as_text=True)
    assert step2_resp.status_code == 200
    assert len(fetch_calls) == 1  # Reused cached fetch cleanly without second scrape
    assert "40% lower latency" in prompts[1]  # Content prompt received URL context
    assert "Focus on developer migration timing." in prompts[1]  # Content prompt received notes
    assert "40% lower latency" in prompts[2]  # Meta description prompt received reference
    assert "Official v3.2 update lowers latency" in step2_html


def test_blog_invalid_or_unreadable_reference_url_stops_before_ai(monkeypatch):
    monkeypatch.setattr(blog_controller, "get_provider", lambda: object())
    monkeypatch.setattr(
        blog_controller,
        "fetch_reference_context",
        lambda *a, **k: ("", [{"url": "https://example.com/locked", "status": "error", "error": "HTTP 403"}]),
    )

    app = create_app()
    app.testing = True
    client = app.test_client()

    bad_url_resp = client.post(
        "/",
        data={
            "action": "generate_titles",
            "keyword": "seo checklist",
            "reference_url": "file:///etc/passwd",
        },
    )
    assert "valid http or https reference URL" in bad_url_resp.get_data(as_text=True)

    unreadable_resp = client.post(
        "/",
        data={
            "action": "generate_titles",
            "keyword": "seo checklist",
            "reference_url": "https://example.com/locked",
        },
    )
    assert "Could not read the reference page" in unreadable_resp.get_data(as_text=True)



