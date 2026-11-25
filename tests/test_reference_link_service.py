from urllib.error import HTTPError
from types import SimpleNamespace

import pytest

from app.services import reference_link_service


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "text/html; charset=utf-8"):
        self.body = body
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        return self.body if size == -1 else self.body[:size]


def test_fetch_url_text_prefers_article_tag(monkeypatch):
    article_text = " ".join(["Article body sentence with useful match details."] * 40)
    html = f"""
    <html>
      <head><title>Matchday round-up</title></head>
      <body>
        <nav>Navigation Home Tickets Shop</nav>
        <article><h1>Matchday report</h1><p>{article_text}</p></article>
        <footer>Footer links and unrelated page chrome</footer>
      </body>
    </html>
    """

    monkeypatch.setattr(
        reference_link_service,
        "urlopen",
        lambda request, timeout: FakeResponse(html.encode("utf-8")),
    )

    result = reference_link_service.fetch_url_text("https://example.com/article")

    assert result["title"] == "Matchday round-up"
    assert "Article body sentence" in result["text"]
    assert "Navigation Home Tickets Shop" not in result["text"]
    assert "Footer links" not in result["text"]


def test_fetch_url_text_can_limit_to_news_content_tags(monkeypatch):
    paragraph_text = " ".join(["Paragraph news detail."] * 30)
    table_text = " ".join(["Table score detail."] * 20)
    html = f"""
    <html>
      <head><title>Filtered News</title></head>
      <body>
        <article>
          <h1>Main result</h1>
          <div>Promo module and newsletter signup should not appear.</div>
          <p>{paragraph_text}</p>
          <aside>Related links should not appear.</aside>
          <table><tr><th>Team</th><td>{table_text}</td></tr></table>
          <ul><li>List item should not appear.</li></ul>
        </article>
      </body>
    </html>
    """

    monkeypatch.setattr(
        reference_link_service,
        "urlopen",
        lambda request, timeout: FakeResponse(html.encode("utf-8")),
    )

    result = reference_link_service._fetch_url_text(
        "https://example.com/article",
        content_tags=("p", "h1", "h2", "h3", "table"),
    )

    assert result["title"] == "Filtered News"
    assert "Main result" in result["text"]
    assert "Paragraph news detail" in result["text"]
    assert "Table score detail" in result["text"]
    assert "Promo module" not in result["text"]
    assert "Related links" not in result["text"]
    assert "List item" not in result["text"]


def test_fetch_url_text_reports_cloudflare_challenge(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(
            request.full_url,
            403,
            "Forbidden",
            {"cf-mitigated": "challenge"},
            None,
        )

    monkeypatch.setattr(reference_link_service, "urlopen", fake_urlopen)

    with pytest.raises(ValueError) as exc_info:
        reference_link_service.fetch_url_text("https://example.com/how-to-play/")

    assert "protected by Cloudflare" in str(exc_info.value)
    assert "HTTP 403" in str(exc_info.value)


def test_fetch_url_text_reports_regular_403(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(reference_link_service, "urlopen", fake_urlopen)

    with pytest.raises(ValueError) as exc_info:
        reference_link_service.fetch_url_text("https://example.com/how-to-play/")

    assert str(exc_info.value) == "The source page blocked automated fetching (HTTP 403)."


def test_fetch_reference_context_prefers_http_when_browser_allowed(monkeypatch):
    calls = {"http": 0, "browser": 0}

    def fake_url_text(url, timeout):
        calls["http"] += 1
        return {
            "title": "HTTP News",
            "text": " ".join(["HTTP article body with details."] * 40),
        }

    def fake_rendered_text(url, wait_seconds, timeout):
        calls["browser"] += 1
        return {
            "title": "Rendered News",
            "text": " ".join(["Rendered article body with details."] * 40),
            "rendered": True,
        }

    monkeypatch.setattr(reference_link_service, "_fetch_url_text", fake_url_text)
    monkeypatch.setattr(reference_link_service, "_fetch_url_rendered_text", fake_rendered_text)

    context, fetched = reference_link_service.fetch_reference_context(
        [{"url": "https://example.com/news", "text": ""}],
        use_browser=True,
        browser_wait_seconds=2,
    )

    assert "HTTP article body" in context
    assert calls == {"http": 1, "browser": 0}
    assert fetched[0]["status"] == "fetched"
    assert fetched[0]["fetch_method"] == "http"


def test_fetch_reference_context_can_merge_links(monkeypatch):
    def fake_url_text(url, timeout):
        return {
            "title": "News " + url.rsplit("/", 1)[-1],
            "text": " ".join([f"Facts from {url}."] * 35),
        }

    monkeypatch.setattr(reference_link_service, "_fetch_url_text", fake_url_text)

    context, fetched = reference_link_service.fetch_reference_context(
        [
            {"url": "https://example.com/one", "text": "First Link"},
            {"url": "https://example.com/two", "text": "Second Link"},
        ],
        merge_context=True,
    )

    assert context.startswith("Combined reference source.")
    assert "Use all fetched links together as one mixed source of facts." in context
    assert "1. First Link - https://example.com/one" in context
    assert "2. Second Link - https://example.com/two" in context
    assert "Merged extracted content:" in context
    assert "Facts from https://example.com/one" in context
    assert "Facts from https://example.com/two" in context
    assert "Reference 1:" not in context
    assert len(fetched) == 2


def test_fetch_reference_context_uses_browser_after_http_fails(monkeypatch):
    def fake_url_text(url, timeout):
        raise ValueError("Could not extract enough readable article text.")

    def fake_rendered_text(url, wait_seconds, timeout):
        return {
            "title": "Rendered News",
            "text": " ".join(["Rendered article body with details."] * 40),
            "rendered": True,
        }

    monkeypatch.setattr(reference_link_service, "_fetch_url_text", fake_url_text)
    monkeypatch.setattr(reference_link_service, "_fetch_url_rendered_text", fake_rendered_text)

    context, fetched = reference_link_service.fetch_reference_context(
        [{"url": "https://example.com/news", "text": ""}],
        use_browser=True,
    )

    assert "Rendered article body" in context
    assert fetched[0]["status"] == "fetched"
    assert fetched[0]["fetch_method"] == "browser-fallback"


def test_news_main_content_retains_fixture_cards_and_excludes_footer(monkeypatch):
    fixtures = "".join(
        f"<div class='fixture'><span>Home Team {index}</span><span>Away Team {index}</span>"
        "<time>21 November 2026 20:45</time></div>"
        for index in range(10)
    )
    html = (
        "<html><title>Serie A round 12 fixtures</title><body>"
        "<nav>Unrelated navigation</nav><main><h1>Round 12</h1>"
        + fixtures
        + "</main><footer><p>Cookie preference instructions and newsletter signup.</p></footer></body></html>"
    )
    monkeypatch.setattr(reference_link_service, "urlopen", lambda *args, **kwargs: FakeResponse(html.encode()))

    context, fetched = reference_link_service.fetch_reference_context(
        [{"url": "https://example.com/fixtures?round=12"}],
        content_tags=("p", "h1", "h2", "h3", "table", "main"),
    )

    assert "Home Team 0 Away Team 0 21 November 2026 20:45" in context
    assert "Home Team 9 Away Team 9" in context
    assert "Cookie preference" not in context
    assert "Unrelated navigation" not in context
    assert fetched[0]["status"] == "fetched"


def test_empty_news_main_content_is_not_replaced_by_footer_text(monkeypatch):
    html = (
        "<html><title>Fixtures</title><main><h1>Calendar and Results</h1>"
        "<div>No data available</div></main><footer><p>"
        + "Cookie preferences, privacy policy and legal information. " * 20
        + "</p></footer></html>"
    )
    monkeypatch.setattr(reference_link_service, "urlopen", lambda *args, **kwargs: FakeResponse(html.encode()))

    context, fetched = reference_link_service.fetch_reference_context(
        [{"url": "https://example.com/fixtures"}],
        content_tags=("p", "h1", "h2", "h3", "table", "main"),
    )

    assert context == ""
    assert fetched[0]["status"] == "error"
    assert "main content has no readable data" in fetched[0]["error"]


def test_empty_main_triggers_browser_fallback_to_loaded_fixtures(monkeypatch):
    shell = "<html><title>Fixtures</title><main><div>Loading fixtures...</div></main></html>"
    fixture_text = "Round 12: Home Team versus Away Team on 21 November 2026 at 20:45. " * 6
    rendered = f"<html><title>Fixtures</title><main><div>{fixture_text}</div></main></html>"
    monkeypatch.setattr(reference_link_service, "urlopen", lambda *args, **kwargs: FakeResponse(shell.encode()))
    calls = []

    def browser(url, wait_seconds, timeout):
        calls.append(url)
        return {"html": rendered, "final_url": url}

    monkeypatch.setattr(reference_link_service, "_fetch_url_rendered_html", browser)

    context, fetched = reference_link_service.fetch_reference_context(
        [{"url": "https://example.com/fixtures"}],
        use_browser=True,
        content_tags=("p", "h1", "h2", "h3", "table", "main"),
    )

    assert calls == ["https://example.com/fixtures"]
    assert "Home Team versus Away Team" in context
    assert fetched[0]["fetch_method"] == "browser-fallback"


def test_streamed_main_shell_uses_browser_even_when_header_is_long(monkeypatch):
    header = "Round 12 fixtures, league standings, previous rounds and upcoming rounds. " * 8
    fixture = "Home Team versus Away Team on 21 November 2026 at 20:45. " * 5
    shell = (
        f"<html><title>Fixtures</title><main><h1>Fixtures</h1><div>{header}</div>"
        "<template id='B:2'></template></main>"
        f"<div hidden id='S:2'><div>{fixture}</div></div></html>"
    )
    rendered = f"<html><title>Fixtures</title><main><h1>Fixtures</h1><div>{fixture}</div></main></html>"
    monkeypatch.setattr(reference_link_service, "urlopen", lambda *args, **kwargs: FakeResponse(shell.encode()))
    calls = []

    def browser(url, wait_seconds, timeout):
        calls.append(url)
        return {"html": rendered, "final_url": url}

    monkeypatch.setattr(reference_link_service, "_fetch_url_rendered_html", browser)

    context, fetched = reference_link_service.fetch_reference_context(
        [{"url": "https://example.com/fixtures"}],
        use_browser=True,
        content_tags=("p", "h1", "h2", "h3", "table", "main"),
    )

    assert calls == ["https://example.com/fixtures"]
    assert "Home Team versus Away Team on 21 November 2026 at 20:45" in context
    assert "previous rounds" not in context
    assert fetched[0]["fetch_method"] == "browser-fallback"


def test_article_reader_keeps_existing_http_behavior_for_streamed_page(monkeypatch):
    article = "Match report with useful details about the latest league announcement. " * 8
    html = (
        f"<html><title>Match report</title><article><p>{article}</p></article>"
        "<template id='B:0'></template><div hidden id='S:0'>A navigation fragment</div></html>"
    )
    monkeypatch.setattr(reference_link_service, "urlopen", lambda *args, **kwargs: FakeResponse(html.encode()))

    result = reference_link_service.fetch_url_text("https://example.com/report")

    assert "Match report with useful details" in result["text"]
    assert "A navigation fragment" not in result["text"]


@pytest.mark.parametrize("rendered", [False, True])
def test_http_200_human_verification_is_not_accepted_as_source(monkeypatch, rendered):
    html = (
        "<html><title>Just a moment...</title><form id='challenge-form'><p>"
        + "Verify that you are human before continuing to this website. " * 12
        + "</p></form></html>"
    )
    if rendered:
        monkeypatch.setattr(reference_link_service, "_fetch_url_rendered_html", lambda *args, **kwargs: {"html": html})
        fetch = reference_link_service.fetch_url_rendered_text
    else:
        monkeypatch.setattr(reference_link_service, "urlopen", lambda *args, **kwargs: FakeResponse(html.encode()))
        fetch = reference_link_service.fetch_url_text

    with pytest.raises(ValueError, match="verification challenge instead of source content"):
        fetch("https://example.com/protected")


def test_article_about_browser_verification_is_not_mistaken_for_challenge():
    html = (
        "<html><title>Understanding browser verification</title><article><p>"
        + "Sites may ask visitors to verify that you are human as part of their security process. " * 8
        + "</p></article></html>"
    )

    article = reference_link_service._extract_readable_text_from_html(html)

    assert "Sites may ask visitors" in article["text"]


def test_rendered_http_403_is_rejected_for_text_but_available_for_html_inspection(monkeypatch):
    closed = []
    response = SimpleNamespace(status=403, headers={"cf-mitigated": "challenge"})
    page = SimpleNamespace(
        goto=lambda *args, **kwargs: response,
        wait_for_load_state=lambda *args, **kwargs: None,
        content=lambda: "<html><title>Access denied</title><p>Protected source</p></html>",
        url="https://example.com/protected",
    )
    browser = SimpleNamespace(new_page=lambda **kwargs: page, close=lambda: closed.append(True))
    playwright = SimpleNamespace(chromium=SimpleNamespace(launch=lambda **kwargs: browser))

    class FakePlaywright:
        def __enter__(self):
            return playwright

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("playwright.sync_api.sync_playwright", FakePlaywright)

    inspected = reference_link_service.fetch_url_rendered_html("https://example.com/protected")

    assert inspected["status_code"] == 403
    assert "Access denied" in inspected["html"]
    with pytest.raises(ValueError, match="protected by Cloudflare.*HTTP 403"):
        reference_link_service.fetch_url_rendered_text("https://example.com/protected", wait_seconds=0)

    assert closed == [True, True]
