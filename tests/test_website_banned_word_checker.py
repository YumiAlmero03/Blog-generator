from app import create_app
from app.controllers import tool_controller
from app.services import banned_word_checker_service
from app.services.seo_checker_service import FetchResult


def test_check_website_banned_words_reports_counts_and_snippets(monkeypatch):
    monkeypatch.setattr(
        banned_word_checker_service,
        "load_banned_word_bank",
        lambda: ["guaranteed", "restricted phrase"],
    )
    monkeypatch.setattr(
        banned_word_checker_service,
        "fetch_url",
        lambda url, verify_ssl=True, allow_private=False: FetchResult(
            url=url,
            status_code=200,
            content_type="text/html",
            text="""
                <html>
                  <head><title>Guaranteed Guide</title></head>
                  <body>
                    <h1>Safe page</h1>
                    <p>This page says guaranteed once and includes a restricted phrase.</p>
                  </body>
                </html>
            """,
        ),
    )

    result = banned_word_checker_service.check_website_banned_words("https://example.com/page")

    assert result["match_count"] == 3
    assert result["matched_term_count"] == 2
    assert result["matches"][0]["term"] == "guaranteed"
    assert result["matches"][0]["count"] == 2
    assert "Guaranteed Guide" in result["matches"][0]["snippets"][0]


def test_website_banned_word_checker_page_renders_results(monkeypatch):
    monkeypatch.setattr(
        tool_controller,
        "check_website_banned_words",
        lambda url, verify_ssl=True, allow_private=False: {
            "url": url,
            "status_code": 200,
            "content_type": "text/html",
            "checked_character_count": 120,
            "banned_word_count": 2,
            "match_count": 1,
            "matched_term_count": 1,
            "matches": [{"term": "guaranteed", "count": 1, "snippets": ["This is guaranteed text."]}],
        },
    )

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/website-banned-word-checker",
        data={"url": "https://example.com/page"},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Website Banned Word Checker" in html
    assert "guaranteed" in html
    assert "This is guaranteed text." in html
