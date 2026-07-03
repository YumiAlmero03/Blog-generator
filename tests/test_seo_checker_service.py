from dataclasses import dataclass

from app import create_app
from app.controllers import tool_controller
from app.services.seo_checker_service import PageSeoParser


def test_page_seo_parser_collects_core_seo_fields():
    parser = PageSeoParser()
    parser.feed(
        """
        <html>
          <head>
            <title>Example Title</title>
            <meta name="description" content="Example meta description">
            <meta property="og:title" content="Open Graph Title">
            <meta name="twitter:card" content="summary">
            <link rel="canonical" href="https://example.com/page">
          </head>
          <body>
            <h1>Main Heading</h1>
            <h2><span>Section</span> Heading</h2>
            <h3>First Detail</h3>
            <h3>Second Detail</h3>
            <h2>Next Section</h2>
            <img src="/image.jpg">
            <img src="/logo.jpg" alt="Example logo">
            <a href="/internal">Internal</a>
          </body>
        </html>
        """
    )

    assert parser.title == "Example Title"
    assert parser.meta_description == "Example meta description"
    assert parser.canonical == "https://example.com/page"
    assert parser.open_graph["og:title"] == "Open Graph Title"
    assert parser.twitter_cards["twitter:card"] == "summary"
    assert len(parser.headings["h1"]) == 1
    assert parser.headings["h2"] == ["Section Heading", "Next Section"]
    assert parser.heading_sequence == [
        {"level": "h1", "text": "Main Heading"},
        {"level": "h2", "text": "Section Heading"},
        {"level": "h3", "text": "First Detail"},
        {"level": "h3", "text": "Second Detail"},
        {"level": "h2", "text": "Next Section"},
    ]
    assert len(parser.images) == 2
    assert not parser.images[0]["has_alt"]
    assert parser.images[1]["has_alt"]
    assert parser.images[1]["alt"] == "Example logo"
    assert parser.links[0]["href"] == "/internal"
    assert parser.links[0]["text"] == "Internal"


@dataclass
class FakeDiscoveryResult:
    base_url: str
    pages: list
    errors: list
    sitemaps: list


def test_seo_checker_lists_pages_then_checks_each_page(monkeypatch):
    calls = []

    monkeypatch.setattr(
        tool_controller,
        "discover_website_pages",
        lambda url, limit: FakeDiscoveryResult(
            base_url="https://example.com",
            pages=["https://example.com/a", "https://example.com/b"],
            errors=[],
            sitemaps=[],
        ),
    )

    def fake_run_seo_audit(url, verify_ssl=True):
        calls.append(url)
        return {
            "url": url,
            "status_code": 200,
            "content_type": "text/html",
            "score": 80,
            "grade": "B",
            "checks": [
                {
                    "name": "Meta title",
                    "status": "pass",
                    "detail": "Good title",
                    "recommendation": "Keep it clear.",
                }
            ],
            "ai_summary": {"summary": "Looks usable.", "priority_actions": [], "source": "Rules"},
            "stats": {
                "title": f"Title for {url}",
                "word_count": 500,
                "h1_count": 1,
                "missing_alt_count": 0,
            },
        }

    monkeypatch.setattr(tool_controller, "run_seo_audit", fake_run_seo_audit)

    app = create_app()
    app.testing = True
    response = app.test_client().post(
        "/seo-checker",
        data={"url": "https://example.com", "limit": "2"},
    )

    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert calls == ["https://example.com/a", "https://example.com/b"]
    assert "Listed Pages" in html
    assert "Checked Pages" in html
    assert "Page Checks" in html
    assert html.index("Listed Pages") < html.index("Page Checks")
    assert "https://example.com/a" in html
    assert "https://example.com/b" in html


def test_site_seo_checks_publish_current_page_progress(monkeypatch):
    progress_messages = []

    monkeypatch.setattr(
        tool_controller,
        "discover_website_pages",
        lambda url, limit: FakeDiscoveryResult(
            base_url="https://example.com",
            pages=["https://example.com/a", "https://example.com/b"],
            errors=[],
            sitemaps=[],
        ),
    )

    def fake_run_seo_audit(url, verify_ssl=True):
        return {
            "url": url,
            "score": 90,
            "grade": "A",
            "checks": [],
            "ai_summary": {"summary": "", "priority_actions": [], "source": "Rules"},
            "stats": {"title": "", "word_count": 0, "h1_count": 0, "missing_alt_count": 0},
        }

    monkeypatch.setattr(tool_controller, "run_seo_audit", fake_run_seo_audit)

    result = tool_controller._run_site_seo_checks(
        "https://example.com",
        limit=2,
        progress_callback=progress_messages.append,
    )

    assert "Checking page 1/2: https://example.com/a" in progress_messages
    assert "Checking page 2/2: https://example.com/b" in progress_messages
    assert result["checked_pages"] == [
        {"index": 1, "url": "https://example.com/a", "status": "checked", "score": 90, "grade": "A", "error": ""},
        {"index": 2, "url": "https://example.com/b", "status": "checked", "score": 90, "grade": "A", "error": ""},
    ]
