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
