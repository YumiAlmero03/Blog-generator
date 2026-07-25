from app import create_app
from app.controllers import social_media_controller


def test_social_scheduler_page_renders_saved_profiles(monkeypatch):
    monkeypatch.setattr(social_media_controller, "list_brand_names", lambda: ["Example Brand"])
    monkeypatch.setattr(
        social_media_controller,
        "list_social_profiles",
        lambda: [
            {
                "id": 7,
                "brand_name": "Example Brand",
                "social_type": "instagram",
                "account_name": "@example",
                "platform_account_id": "1234567890",
                "profile_url": "https://instagram.com/example",
                "api_key": "example-api-key",
                "api_secret": "example-api-secret",
                "access_token": "example-access-token",
                "refresh_token": "example-refresh-token",
                "posts_per_day": 2,
                "is_active": 1,
                "notes": "Post in the afternoon.",
            }
        ],
    )

    app = create_app()
    app.testing = True
    response = app.test_client().get("/social-scheduler")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Social Scheduler" in html
    assert '<option value="telegram"' in html
    assert "Example Brand" in html
    assert "@example" in html
    assert "Instagram" in html
    assert "...-key" in html
    assert "...cret" in html
    assert "2 target/day" in html


def test_social_scheduler_saves_profile(monkeypatch):
    saved = {}
    monkeypatch.setattr(social_media_controller, "list_brand_names", lambda: ["Example Brand"])
    monkeypatch.setattr(social_media_controller, "list_social_profiles", lambda: [])
    monkeypatch.setattr(
        social_media_controller,
        "save_social_profile",
        lambda **kwargs: saved.update(kwargs) or {"id": 1, **kwargs},
    )

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/social-scheduler",
        data={
            "brand_name": "Example Brand",
            "social_type": "telegram",
            "account_name": "@example_channel",
            "platform_account_id": "telegram-channel-123",
            "profile_url": "https://t.me/example_channel",
            "api_key": "telegram-api-key",
            "api_secret": "telegram-api-secret",
            "access_token": "telegram-access-token",
            "refresh_token": "telegram-refresh-token",
            "posts_per_day": "3",
            "is_active": "1",
            "notes": "Business updates.",
        },
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert saved["brand_name"] == "Example Brand"
    assert saved["social_type"] == "telegram"
    assert saved["account_name"] == "@example_channel"
    assert saved["platform_account_id"] == "telegram-channel-123"
    assert saved["api_key"] == "telegram-api-key"
    assert saved["api_secret"] == "telegram-api-secret"
    assert saved["access_token"] == "telegram-access-token"
    assert saved["refresh_token"] == "telegram-refresh-token"
    assert saved["posts_per_day"] == 3
    assert saved["is_active"] is True
    assert "Social account saved." in html


def test_social_scheduler_edit_populates_api_fields(monkeypatch):
    monkeypatch.setattr(social_media_controller, "list_brand_names", lambda: ["Example Brand"])
    monkeypatch.setattr(social_media_controller, "list_social_profiles", lambda: [])
    monkeypatch.setattr(
        social_media_controller,
        "get_social_profile",
        lambda profile_id: {
            "id": profile_id,
            "brand_name": "Example Brand",
            "social_type": "facebook",
            "account_name": "Example Page",
            "platform_account_id": "1234567890",
            "profile_url": "https://facebook.com/example",
            "api_key": "facebook-api-key",
            "api_secret": "facebook-api-secret",
            "access_token": "facebook-access-token",
            "refresh_token": "facebook-refresh-token",
            "posts_per_day": 1,
            "is_active": 1,
            "notes": "Edit notes.",
        },
    )

    app = create_app()
    app.testing = True
    response = app.test_client().get("/social-scheduler?edit=12")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'name="profile_id" value="12"' in html
    assert 'name="platform_account_id" type="text" value="1234567890"' in html
    assert 'name="api_key" type="password" autocomplete="off" value="facebook-api-key"' in html
    assert 'name="api_secret" type="password" autocomplete="off" value="facebook-api-secret"' in html
    assert 'name="access_token" type="password" autocomplete="off" value="facebook-access-token"' in html
    assert 'name="refresh_token" type="password" autocomplete="off" value="facebook-refresh-token"' in html


def test_social_scheduler_post_uses_link_or_keyword_context(monkeypatch):
    created = {}
    monkeypatch.setattr(social_media_controller, "list_brand_names", lambda: ["Example Brand"])
    monkeypatch.setattr(
        social_media_controller,
        "list_social_profiles",
        lambda: [
            {
                "id": 7,
                "brand_name": "Example Brand",
                "social_type": "twitter",
                "account_name": "@example",
                "platform_account_id": "",
                "profile_url": "",
                "api_key": "",
                "api_secret": "",
                "access_token": "",
                "refresh_token": "",
                "posts_per_day": 1,
                "is_active": 1,
                "notes": "",
            }
        ],
    )
    monkeypatch.setattr(
        social_media_controller,
        "get_social_profile",
        lambda profile_id: {
            "id": profile_id,
            "brand_name": "Example Brand",
            "social_type": "twitter",
            "account_name": "@example",
            "platform_account_id": "",
            "profile_url": "",
        },
    )
    monkeypatch.setattr(social_media_controller, "get_brand_context", lambda brand: "Saved brand context.")
    monkeypatch.setattr(social_media_controller, "get_provider", lambda: object())
    monkeypatch.setattr(social_media_controller, "build_web_research_context", lambda query: f"Research for {query}")
    monkeypatch.setattr(social_media_controller, "social_post_character_limit_for_platform", lambda platform: 240)

    def fake_generate_social_media_post(*args, **kwargs):
        created.update(kwargs)
        return {
            "post_content": "A concise generated social post.",
            "image_description": "A simple image idea.",
            "tags": ["#Example"],
            "character_count": 32,
            "character_limit": kwargs["max_characters"],
        }

    monkeypatch.setattr(social_media_controller, "generate_social_media_post", fake_generate_social_media_post)
    monkeypatch.setattr(social_media_controller, "record_generation", lambda **kwargs: 42)

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/social-scheduler",
        data={
            "action": "create_post",
            "profile_id": "7",
            "post_keyword": "product update",
            "post_link": "https://example.com/update",
        },
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert created["social_type"] == "twitter"
    assert created["reference_link"] == "https://example.com/update"
    assert created["research_context"] == "Research for https://example.com/update"
    assert created["max_characters"] == 240
    assert "A concise generated social post." in html
    assert "/generation-history/42" in html


def test_generated_social_post_page_renders_selected_profile(monkeypatch):
    monkeypatch.setattr(
        social_media_controller,
        "list_social_profiles",
        lambda: [
            {
                "id": 7,
                "brand_name": "Example Brand",
                "social_type": "facebook",
                "account_name": "Example Page",
                "platform_account_id": "1234567890",
            }
        ],
    )

    app = create_app()
    app.testing = True
    response = app.test_client().get("/generated-social-post?profile_id=7")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Generated Social Post" in html
    assert 'value="7" selected' in html
    assert "Example Brand / Facebook / Example Page" in html


def test_generated_social_post_generates_review_draft(monkeypatch):
    monkeypatch.setattr(
        social_media_controller,
        "list_social_profiles",
        lambda: [
            {
                "id": 7,
                "brand_name": "Example Brand",
                "social_type": "twitter",
                "account_name": "@example",
                "platform_account_id": "",
            }
        ],
    )
    monkeypatch.setattr(
        social_media_controller,
        "get_social_profile",
        lambda profile_id: {
            "id": profile_id,
            "brand_name": "Example Brand",
            "social_type": "twitter",
            "account_name": "@example",
            "platform_account_id": "",
            "profile_url": "",
        },
    )
    monkeypatch.setattr(social_media_controller, "get_brand_context", lambda brand: "Saved brand context.")
    monkeypatch.setattr(social_media_controller, "get_provider", lambda: object())
    monkeypatch.setattr(social_media_controller, "build_web_research_context", lambda query, progress_callback=None: f"Research for {query}")
    monkeypatch.setattr(social_media_controller, "social_post_character_limit_for_platform", lambda platform: 240)
    monkeypatch.setattr(
        social_media_controller,
        "generate_social_media_post",
        lambda *args, **kwargs: {
            "post_content": "Generated draft post.",
            "image_description": "Image idea.",
            "tags": ["#Example"],
            "character_count": 21,
            "character_limit": 240,
        },
    )
    monkeypatch.setattr(social_media_controller, "record_generation", lambda **kwargs: 42)

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/generated-social-post",
        data={
            "social_profile_id": "7",
            "post_keyword": "launch update",
            "post_link": "",
        },
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Generated draft post." in html
    assert "Review Post" in html
    assert "/generation-history/42" in html
    assert "21/240 characters" in html


def test_generated_social_post_adds_matchup_reaction_lines(monkeypatch):
    monkeypatch.setattr(
        social_media_controller,
        "list_social_profiles",
        lambda: [
            {
                "id": 7,
                "brand_name": "Example Brand",
                "social_type": "facebook",
                "account_name": "Example Page",
                "platform_account_id": "",
            }
        ],
    )
    monkeypatch.setattr(
        social_media_controller,
        "get_social_profile",
        lambda profile_id: {
            "id": profile_id,
            "brand_name": "Example Brand",
            "social_type": "facebook",
            "account_name": "Example Page",
            "platform_account_id": "",
            "profile_url": "",
        },
    )
    monkeypatch.setattr(social_media_controller, "get_brand_context", lambda brand: "Saved brand context.")
    monkeypatch.setattr(social_media_controller, "get_provider", lambda: object())
    monkeypatch.setattr(social_media_controller, "build_web_research_context", lambda query, progress_callback=None: f"Research for {query}")
    monkeypatch.setattr(social_media_controller, "social_post_character_limit_for_platform", lambda platform: 240)
    monkeypatch.setattr(
        social_media_controller,
        "generate_social_media_post",
        lambda *args, **kwargs: {
            "post_content": "Match night is here. Who are you backing?",
            "image_description": "Matchup graphic.",
            "tags": ["#MatchDay"],
            "character_count": 41,
            "character_limit": 240,
        },
    )
    monkeypatch.setattr(social_media_controller, "record_generation", lambda **kwargs: 42)

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/generated-social-post",
        data={
            "social_profile_id": "7",
            "post_keyword": "Golden State Warriors vs Boston Celtics",
            "post_link": "",
        },
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "React \U0001f49f for Team #GoldenStateWarriors" in html
    assert "React \U0001f44d for Team #BostonCeltics" in html
    assert "Added matchup reaction lines for the vs keyword." in html


def test_generated_social_post_confirm_updates_history(monkeypatch):
    recorded = {}
    monkeypatch.setattr(social_media_controller, "list_social_profiles", lambda: [])
    monkeypatch.setattr(
        social_media_controller,
        "get_social_profile",
        lambda profile_id: {
            "id": profile_id,
            "brand_name": "Example Brand",
            "social_type": "linkedin",
            "account_name": "Example Page",
            "platform_account_id": "linkedin-org-123",
            "profile_url": "",
        },
    )

    def fake_record_generation(**kwargs):
        recorded.update(kwargs)
        return int(kwargs["history_id"])

    monkeypatch.setattr(social_media_controller, "record_generation", fake_record_generation)

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/generated-social-post",
        data={
            "action": "confirm_social_post",
            "social_profile_id": "7",
            "post_keyword": "launch update",
            "generated_content": "Approved social post.",
            "image_description": "Image idea.",
            "tags_text": "#Example",
            "character_limit": "3000",
            "history_id": "42",
        },
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert recorded["history_id"] == "42"
    assert recorded["prompt_inputs"]["confirmed"] is True
    assert recorded["prompt_inputs"]["publish_status"] == "confirmed_ready_to_post"
    assert "Social post confirmed" in html


def test_generated_social_post_confirm_posts_to_facebook(monkeypatch):
    recorded = {}
    published = {}
    monkeypatch.setattr(social_media_controller, "list_social_profiles", lambda: [])
    monkeypatch.setattr(
        social_media_controller,
        "get_social_profile",
        lambda profile_id: {
            "id": profile_id,
            "brand_name": "Example Brand",
            "social_type": "facebook",
            "account_name": "Example Page",
            "platform_account_id": "1234567890",
            "profile_url": "",
            "access_token": "page-token",
        },
    )

    class FakePublishResult:
        remote_post_id = "1234567890_987654321"
        url = "https://www.facebook.com/1234567890_987654321"

    def fake_publish_facebook_page_post(profile, message, link=""):
        published.update({"profile": profile, "message": message, "link": link})
        return FakePublishResult()

    def fake_record_generation(**kwargs):
        recorded.update(kwargs)
        return int(kwargs["history_id"])

    monkeypatch.setattr(social_media_controller, "publish_facebook_page_post", fake_publish_facebook_page_post)
    monkeypatch.setattr(social_media_controller, "record_generation", fake_record_generation)

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/generated-social-post",
        data={
            "action": "confirm_social_post",
            "social_profile_id": "7",
            "post_keyword": "launch update",
            "post_link": "https://example.com/update",
            "generated_content": "Approved Facebook post.",
            "image_description": "Image idea.",
            "tags_text": "#Example",
            "character_limit": "1000",
            "history_id": "42",
        },
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert published["profile"]["platform_account_id"] == "1234567890"
    assert published["message"] == "Approved Facebook post."
    assert published["link"] == "https://example.com/update"
    assert recorded["post_link"] == "https://www.facebook.com/1234567890_987654321"
    assert recorded["prompt_inputs"]["publish_status"] == "posted"
    assert recorded["prompt_inputs"]["remote_post_id"] == "1234567890_987654321"
    assert "posted to Facebook" in html


def test_generated_social_post_facebook_publish_error_stays_on_review(monkeypatch):
    monkeypatch.setattr(social_media_controller, "list_social_profiles", lambda: [])
    monkeypatch.setattr(
        social_media_controller,
        "get_social_profile",
        lambda profile_id: {
            "id": profile_id,
            "brand_name": "Example Brand",
            "social_type": "facebook",
            "account_name": "Example Page",
            "platform_account_id": "1234567890",
            "profile_url": "",
            "access_token": "bad-token",
        },
    )
    monkeypatch.setattr(
        social_media_controller,
        "publish_facebook_page_post",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("Invalid OAuth access token.")),
    )

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/generated-social-post",
        data={
            "action": "confirm_social_post",
            "social_profile_id": "7",
            "post_keyword": "launch update",
            "post_link": "https://example.com/update",
            "generated_content": "Approved Facebook post.",
            "image_description": "Image idea.",
            "tags_text": "#Example",
            "character_limit": "1000",
            "history_id": "42",
            "platform": "Facebook",
            "account_name": "Example Page",
        },
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Could not post to Facebook" in html
    assert "Invalid OAuth access token." in html
    assert "Approved Facebook post." in html
    assert "Confirm & Post to Facebook" in html
