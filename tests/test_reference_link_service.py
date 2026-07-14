from urllib.error import HTTPError

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
