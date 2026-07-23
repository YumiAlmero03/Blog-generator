import json

from app import create_app
from app.controllers import page_controller
from generators import page_generator
from generators.page_generator import generate_page_content, generate_page_section, generate_page_title
from generators import simple_page_generator
from generators.simple_page_generator import generate_simple_page_title
from prompts.pages import build_page_content_prompt, build_page_prompt, build_page_section_prompt, build_page_title_prompt, build_simple_page_content_prompt, build_simple_page_title_prompt


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        return json.dumps(self.responses.pop(0))


def test_page_title_prompt_requires_50_to_60_characters():
    prompt = build_page_title_prompt(keyword="emergency plumber phoenix")

    assert "between 50 and 60 characters" in prompt
    assert "Start the title with the exact main keyword" in prompt


def test_page_prompts_require_owner_voice_and_yoast_rules():
    full_prompt = build_page_prompt(keyword="emergency plumber phoenix")
    content_prompt = build_page_content_prompt(
        keyword="emergency plumber phoenix",
        title="emergency plumber phoenix Help When Pipes Burst",
        meta_description="Get emergency plumber phoenix help with clear service details, repair support, and practical next steps today.",
    )

    for prompt in (full_prompt, content_prompt):
        assert "use first-person plural language like we, our, and us" in prompt
        assert "Do not refer to the website, brand, team, or service as they, them, or their" in prompt
        assert "Avoid keyword stuffing, repeated exact-match phrases" in prompt
        assert "Follow Yoast-style SEO and readability rules" in prompt


def test_generate_page_title_retries_until_50_to_60_characters(monkeypatch):
    provider = FakeProvider(
        [
            {"title": "emergency plumbing services phoenix Fast Help"},
            {"title": "emergency plumbing services phoenix Available 24/7"},
        ]
    )
    progress_messages = []

    monkeypatch.setattr(page_generator, "max_generation_attempts", lambda: 2)
    monkeypatch.setattr(page_generator, "wait_before_retry", lambda *args, **kwargs: None)

    title = generate_page_title(
        provider,
        keyword="emergency plumbing services phoenix",
        progress_callback=progress_messages.append,
    )

    assert title == "emergency plumbing services phoenix Available 24/7"
    assert 50 <= len(title) <= 60
    assert len(provider.prompts) == 2
    assert any("target is 50-60" in message for message in progress_messages)


def test_generate_page_title_retries_until_title_starts_with_keyword(monkeypatch):
    provider = FakeProvider(
        [
            {"title": "Fast Phoenix Services for Emergency Plumbing Help"},
            {"title": "emergency plumbing phoenix Services for Fast Repairs"},
        ]
    )
    progress_messages = []

    monkeypatch.setattr(page_generator, "max_generation_attempts", lambda: 2)
    monkeypatch.setattr(page_generator, "wait_before_retry", lambda *args, **kwargs: None)

    title = generate_page_title(
        provider,
        keyword="emergency plumbing phoenix",
        progress_callback=progress_messages.append,
    )

    assert title.startswith("emergency plumbing phoenix")
    assert len(provider.prompts) == 2
    assert any("title must start with" in message for message in progress_messages)


def test_generate_page_content_error_reports_banned_terms(monkeypatch):
    banned_content = "# Test Page\n\n### Section\n\n" + " ".join(["helpful details"] * 80) + " fake"
    provider = FakeProvider(
        [
            {"content": banned_content},
            {"content": banned_content},
        ]
    )

    monkeypatch.setattr(page_generator, "max_generation_attempts", lambda: 2)
    monkeypatch.setattr(page_generator, "wait_before_retry", lambda *args, **kwargs: None)

    try:
        generate_page_content(
            provider,
            keyword="test page",
            title="test page Helpful Service Details for Readers",
            meta_description="Helpful test page details for readers who need clear service information, practical guidance, and simple next steps.",
            min_words=10,
            max_words=500,
        )
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected banned term validation to fail")

    assert "banned terms found: fake" in message
    assert "Last attempt was" in message


def test_page_section_prompt_returns_insertable_section_only():
    prompt = build_page_section_prompt(
        keyword="emergency plumber phoenix",
        title="emergency plumber phoenix Fast Local Help",
        current_content="# Existing Page\n\nIntro copy.",
        section_request="Add a service areas section.",
        supporting_keywords="drain cleaning, leak repair",
    )

    assert "Return only the new section, not the full page." in prompt
    assert "Start the section with one ## H2 heading." in prompt
    assert "Add a service areas section." in prompt
    assert "drain cleaning, leak repair" in prompt


def test_generate_page_section_returns_html(monkeypatch):
    provider = FakeProvider(
        [
            {
                "section_title": "Service Areas",
                "content": "## Service Areas\n\nWe support nearby neighborhoods with clear scheduling and practical service details.",
            }
        ]
    )

    monkeypatch.setattr(page_generator, "max_generation_attempts", lambda: 1)

    result = generate_page_section(
        provider,
        keyword="emergency plumber phoenix",
        title="emergency plumber phoenix Fast Local Help",
        current_content="<h1>Existing Page</h1><p>Intro copy.</p>",
        section_request="Add a service areas section.",
    )

    assert result["section_title"] == "Service Areas"
    assert "<h2>Service Areas</h2>" in result["section_content"]
    assert result["section_word_count"] > 0


def test_page_generator_hides_page_type_field():
    app = create_app()
    app.testing = True
    response = app.test_client().get("/page-generator")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Page type</label>" not in html
    assert 'id="page_type"' not in html
    assert "The keyword is used as the page type." in html
    assert "Section Generator" not in html
    assert "Generation Log" in html
    assert "generation_log_json" in html


def test_page_generator_shows_section_generator_after_content(monkeypatch):
    monkeypatch.setattr(page_controller, "get_generation_history_item", lambda history_id: {
        "id": history_id,
        "brand_name": "Example",
        "primary_keyword": "emergency plumber phoenix",
        "title": "emergency plumber phoenix Fast Local Help",
        "meta_description": "Get emergency plumber phoenix help with clear repair details and practical next steps for local service needs.",
        "content": "<h1>emergency plumber phoenix Fast Local Help</h1><p>Existing content.</p>",
        "prompt_inputs": json.dumps({"language": "English", "supporting_keywords": "drain cleaning"}),
        "quality_report": "{}",
    })

    app = create_app()
    app.testing = True
    response = app.test_client().get("/page-generator?edit_history_id=1")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Section Generator" in html
    assert 'name="section_request"' in html


def test_page_progress_callback_records_generation_log():
    log_entries = []
    progress = page_controller._progress_callback("Page", "", log_entries)

    progress("Generating page title...")
    progress("PROMPT BODY", kind="prompt")

    assert log_entries == [
        {"kind": "status", "message": "Generating page title..."},
        {"kind": "prompt", "message": "PROMPT BODY"},
    ]


def test_simple_page_title_prompt_requires_page_title_prefix():
    prompt = build_simple_page_title_prompt(page_title="Privacy Policy")

    assert "Start the title with the exact page title" in prompt
    assert 'Format it like: "Privacy Policy generated title".' in prompt


def test_simple_page_content_prompt_includes_supporting_keywords():
    prompt = build_simple_page_content_prompt(
        page_title="Privacy Policy",
        generated_title="Privacy Policy for Visitor Data",
        supporting_keywords="personal data, cookie policy",
    )

    assert "Supporting keywords:" in prompt
    assert "personal data, cookie policy" in prompt
    assert "Include supporting keywords naturally" in prompt


def test_generate_simple_page_title_retries_until_title_starts_with_page_title(monkeypatch):
    provider = FakeProvider(
        [
            {"title": "Clear Privacy Details for Visitors"},
            {"title": "Privacy Policy for Clear Visitor Data Practices"},
        ]
    )
    progress_messages = []

    monkeypatch.setattr(simple_page_generator, "max_generation_attempts", lambda: 2)
    monkeypatch.setattr(simple_page_generator, "wait_before_retry", lambda *args, **kwargs: None)

    title = generate_simple_page_title(
        provider,
        page_title="Privacy Policy",
        progress_callback=progress_messages.append,
    )

    assert title.startswith("Privacy Policy")
    assert len(provider.prompts) == 2
    assert any("title must start with" in message for message in progress_messages)


def test_simple_page_generator_hides_page_type_field():
    app = create_app()
    app.testing = True
    response = app.test_client().get("/simple-page-generator")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Page type</label>" not in html
    assert 'id="page_type"' not in html
    assert 'name="supporting_keywords"' in html
    assert "The page title is used as the page type." in html
