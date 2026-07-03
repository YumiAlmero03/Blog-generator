from app import create_app
from app.controllers import tool_controller


def test_hidden_test_page_fetches_link(monkeypatch):
    monkeypatch.setattr(
        tool_controller,
        "fetch_url_rendered_html",
        lambda url, wait_seconds=0: {
            "content_type": "text/html; charset=utf-8",
            "html": "<html><body><article>Rendered article HTML.</article></body></html>",
            "byte_count": 64,
            "character_count": 64,
            "final_url": url,
            "rendered": True,
        },
    )
    monkeypatch.setattr(tool_controller.time, "sleep", lambda seconds: None)

    app = create_app()
    app.testing = True
    client = app.test_client()

    response = client.get("/test-page")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Test Page" in html
    assert "Fetch Link" in html
    assert "Fetch Mode" in html
    assert "Wait Time" in html

    response = client.post("/test-page", data={"url": "https://example.com/article"})
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Browser rendered" in html
    assert "text/html; charset=utf-8" in html
    assert "Rendered article HTML." in html


def test_hidden_test_page_can_fetch_raw_http(monkeypatch):
    monkeypatch.setattr(
        tool_controller,
        "fetch_url_html",
        lambda url: {
            "content_type": "text/html; charset=utf-8",
            "html": "<html><body><article>Raw article HTML.</article></body></html>",
            "byte_count": 59,
            "character_count": 59,
            "final_url": url,
        },
    )

    app = create_app()
    app.testing = True
    client = app.test_client()

    response = client.post(
        "/test-page",
        data={"url": "https://example.com/article", "fetch_mode": "http"},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Raw HTML" in html
    assert "Raw HTTP" in html
    assert "text/html; charset=utf-8" in html
    assert "Raw article HTML." in html


def test_hidden_test_page_waits_before_fetching(monkeypatch):
    slept = []
    fetched = []
    monkeypatch.setattr(
        tool_controller,
        "fetch_url_rendered_html",
        lambda url, wait_seconds=0: fetched.append((url, wait_seconds)) or {
            "content_type": "text/html",
            "html": "<html></html>",
            "byte_count": 13,
            "character_count": 13,
            "final_url": url,
            "rendered": True,
        },
    )

    app = create_app()
    app.testing = True
    client = app.test_client()

    response = client.post(
        "/test-page",
        data={"url": "https://example.com/article", "wait_minutes": "0.1"},
    )

    assert response.status_code == 200
    assert slept == []
    assert fetched == [("https://example.com/article", 6)]
