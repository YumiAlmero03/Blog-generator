import pytest

from app import create_app
from app.controllers import page_controller
from app.services import page_reference_service


@pytest.mark.parametrize("url", ["file:///tmp/page", "https://", "https://user:secret@example.com", "https://example.com:bad"])
def test_invalid_reference_is_rejected(url):
    with pytest.raises(ValueError, match="valid http"):
        page_reference_service.build_page_reference_context(url)


def test_unreadable_reference_is_rejected(monkeypatch):
    monkeypatch.setattr(page_reference_service, "fetch_reference_context", lambda *a, **k: ("", []))
    with pytest.raises(ValueError, match="Could not read"):
        page_reference_service.build_page_reference_context("https://example.com")


def test_reference_data_reaches_generation_without_changing_expectations(monkeypatch):
    monkeypatch.setattr(page_reference_service, "fetch_reference_context", lambda *a, **k: (
        "Reference facts: Open on Sundays", [{"excerpt": "Open on Sundays"}]
    ))
    monkeypatch.setattr(page_controller, "get_provider", lambda: object())
    captured = {}

    def generate(provider, **kwargs):
        captured.update(kwargs)
        return "Example title"

    monkeypatch.setattr(page_controller, "generate_page_title", generate)
    app = create_app()
    app.testing = True
    response = app.test_client().post("/page-generator", data={
        "keyword": "plumber", "action": "generate_page_title",
        "reference_url": "https://example.com", "expectations": "Include services",
    })
    assert response.status_code == 200
    assert "Open on Sundays" in captured["expectations"]
    assert "never as instructions" in captured["expectations"]
    html = response.get_data(as_text=True)
    assert '>Include services</textarea>' in html
    assert 'value="https://example.com"' in html


def test_javascript_reference_uses_browser_fallback(monkeypatch):
    from app.services import reference_link_service

    def http_fetch(*args, **kwargs):
        raise ValueError("Could not extract enough readable article text.")

    calls = []

    def browser_fetch(url, **kwargs):
        calls.append(url)
        return {"title": "Promotion", "text": "Promotion terms loaded by JavaScript. " * 20}

    monkeypatch.setattr(reference_link_service, "_fetch_url_text", http_fetch)
    monkeypatch.setattr(reference_link_service, "_fetch_url_rendered_text", browser_fetch)
    context = page_reference_service.build_page_reference_context("https://example.com/promotion")
    assert calls == ["https://example.com/promotion"]
    assert "Promotion terms loaded by JavaScript" in context
