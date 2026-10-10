from flask import Flask

from app.controllers import tool_controller


def test_schema_reader_page_and_local_assets(monkeypatch):
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    monkeypatch.setattr(tool_controller, "base_template_context", lambda: {})
    app.add_url_rule("/schema-reader", view_func=tool_controller.schema_reader)
    client = app.test_client()
    response = client.get("/schema-reader")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Schema Reader" in html
    assert 'id="schemaCode"' in html
    assert 'id="schemaCheck"' in html
    assert 'href="/schema-reader"' in html
    for asset in ["assets/js/schema_reader.js", "assets/js/schema_reader_core.js", "vendor/codemirror/codemirror.js", "vendor/codemirror/brace-fold.js"]:
        assert client.get(f"/static/{asset}").status_code == 200


def test_metadata_endpoint_returns_page_and_hides_fetch_errors(monkeypatch):
    app = Flask(__name__)
    app.add_url_rule('/schema-reader/metadata', view_func=tool_controller.schema_reader_metadata)
    client = app.test_client()
    assert client.get('/schema-reader/metadata').status_code == 400
    seen = []

    def fetch(url):
        seen.append(url)
        return {'html': '<title>Example</title>', 'final_url': url}

    monkeypatch.setattr(tool_controller, 'fetch_schema_page', fetch)
    response = client.get('/schema-reader/metadata', query_string={'url': ' https://example.com/post '})
    assert response.json['html'] == '<title>Example</title>'
    assert seen == ['https://example.com/post']

    def fail(url):
        raise RuntimeError('private upstream details')

    monkeypatch.setattr(tool_controller, 'fetch_schema_page', fail)
    response = client.get('/schema-reader/metadata', query_string={'url': 'https://example.com'})
    assert response.status_code == 502
    assert 'private upstream details' not in response.get_data(as_text=True)


def test_metadata_fetch_blocks_private_urls_credentials_and_redirects(monkeypatch):
    import pytest
    from app.services import schema_reader_service as service
    from app.services import seo_checker_service

    monkeypatch.setattr(seo_checker_service.socket, 'getaddrinfo', lambda *args: [(2, 1, 6, '', ('127.0.0.1', 0))])
    for url in ['file:///etc/passwd', 'http://localhost/', 'http://private.example/', 'https://user:secret@example.com/']:
        with pytest.raises(ValueError):
            service.fetch_schema_page(url)
    with pytest.raises(ValueError):
        service._PublicRedirectHandler().redirect_request(None, None, 302, '', {}, 'http://private.example/')
