import json

import pytest

from app.services import indexnow_service
from app.services.indexnow_service import (
    build_sitemap_xml,
    extract_urls,
    filter_host_urls,
    google_access_token_from_service_account_json,
    inspect_google_index_status,
    inspect_google_index_status_by_url_domain,
    normalize_host,
    search_console_property_for_url,
    submit_google_indexing_urls,
    submit_indexnow_urls,
    validate_key,
)


def test_extract_urls_from_paste_and_csv_text():
    urls = extract_urls(
        "URL\nhttps://www.example.com/a\n",
        '"Title","https://www.example.com/b?x=1","notes"\nhttps://www.example.com/a',
    )

    assert urls == [
        "https://www.example.com/a",
        "https://www.example.com/b?x=1",
        "https://www.example.com/a",
    ]


def test_normalize_host_accepts_plain_or_full_url():
    assert normalize_host("https://WWW.Example.com/path") == "www.example.com"
    assert normalize_host("www.example.com/") == "www.example.com"


def test_validate_key_rejects_invalid_protocol_key():
    with pytest.raises(ValueError):
        validate_key("bad key")


def test_filter_host_urls_removes_duplicates_and_skips_other_hosts():
    valid, skipped = filter_host_urls(
        [
            "https://www.example.com/a",
            "https://www.example.com/a",
            "https://other.example.com/b",
        ],
        "www.example.com",
    )

    assert valid == ["https://www.example.com/a"]
    assert skipped == ["https://other.example.com/b - host does not match www.example.com"]


def test_submit_indexnow_urls_posts_expected_json(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def getcode(self):
            return 200

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["content_type"] = request.headers["Content-type"]
        return FakeResponse()

    monkeypatch.setattr(indexnow_service, "urlopen", fake_urlopen)

    result = submit_indexnow_urls(
        urls=["https://www.example.com/a", "https://www.example.com/a"],
        key="abc12345",
        host="www.example.com",
        key_location="https://www.example.com/abc12345.txt",
        endpoint="https://api.indexnow.org/indexnow",
    )

    assert result.submitted_count == 1
    assert result.duplicate_count == 1
    assert result.ok is True
    assert captured["url"] == "https://api.indexnow.org/indexnow"
    assert captured["payload"] == {
        "host": "www.example.com",
        "key": "abc12345",
        "keyLocation": "https://www.example.com/abc12345.txt",
        "urlList": ["https://www.example.com/a"],
    }


def test_submit_google_indexing_urls_posts_expected_json(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def getcode(self):
            return 200

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["authorization"] = request.headers["Authorization"]
        return FakeResponse()

    monkeypatch.setattr(indexnow_service, "urlopen", fake_urlopen)

    result = submit_google_indexing_urls(
        urls=["https://www.example.com/job-1"],
        access_token="token-123",
        notification_type="URL_UPDATED",
    )

    assert result.submitted_count == 1
    assert result.ok is True
    assert captured["url"] == "https://indexing.googleapis.com/v3/urlNotifications:publish"
    assert captured["authorization"] == "Bearer token-123"
    assert captured["payload"] == {"url": "https://www.example.com/job-1", "type": "URL_UPDATED"}


def test_submit_google_indexing_urls_can_use_service_account_json(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def getcode(self):
            return 200

    def fake_token(service_account_json):
        assert json.loads(service_account_json)["type"] == "service_account"
        return "service-token"

    def fake_urlopen(request, timeout):
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(indexnow_service, "google_access_token_from_service_account_json", fake_token)
    monkeypatch.setattr(indexnow_service, "urlopen", fake_urlopen)

    result = submit_google_indexing_urls(
        urls=["https://www.example.com/job-1"],
        access_token="",
        service_account_json='{"type":"service_account"}',
        notification_type="URL_UPDATED",
    )

    assert result.ok is True
    assert captured["authorization"] == "Bearer service-token"
    assert captured["payload"] == {"url": "https://www.example.com/job-1", "type": "URL_UPDATED"}


def test_inspect_google_index_status_posts_expected_json(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def getcode(self):
            return 200

        def read(self):
            return json.dumps({
                "inspectionResult": {
                    "indexStatusResult": {
                        "verdict": "PASS",
                        "coverageState": "Submitted and indexed",
                        "robotsTxtState": "ALLOWED",
                        "indexingState": "INDEXING_ALLOWED",
                        "lastCrawlTime": "2026-06-15T00:00:00Z",
                    }
                }
            }).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(indexnow_service, "urlopen", fake_urlopen)

    result = inspect_google_index_status(
        urls=["https://www.example.com/job-1"],
        site_url="https://www.example.com/",
        access_token="token-123",
    )

    assert result.inspected_count == 1
    assert result.items[0].status == "indexed"
    assert result.items[0].coverage_state == "Submitted and indexed"
    assert captured["url"] == "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
    assert captured["authorization"] == "Bearer token-123"
    assert captured["payload"] == {
        "inspectionUrl": "https://www.example.com/job-1",
        "siteUrl": "https://www.example.com/",
        "languageCode": "en-US",
    }


def test_inspect_google_index_status_uses_webmasters_scope(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def getcode(self):
            return 200

        def read(self):
            return b'{"inspectionResult":{"indexStatusResult":{"verdict":"NEUTRAL","coverageState":"Discovered - currently not indexed"}}}'

    def fake_token(service_account_json, scopes=None):
        captured["scopes"] = scopes
        return "service-token"

    def fake_urlopen(request, timeout):
        captured["authorization"] = request.headers["Authorization"]
        return FakeResponse()

    monkeypatch.setattr(indexnow_service, "google_access_token_from_service_account_json", fake_token)
    monkeypatch.setattr(indexnow_service, "urlopen", fake_urlopen)

    result = inspect_google_index_status(
        urls=["https://www.example.com/page"],
        site_url="sc-domain:example.com",
        service_account_json='{"type":"service_account"}',
    )

    assert result.items[0].status == "not-indexed"
    assert captured["authorization"] == "Bearer service-token"
    assert captured["scopes"] == ["https://www.googleapis.com/auth/webmasters.readonly"]


def test_search_console_property_for_url_uses_url_domain():
    assert search_console_property_for_url("https://www.example.com/page") == "https://www.example.com/"
    assert search_console_property_for_url("http://example.com/page") == "https://example.com/"
    assert search_console_property_for_url("not-a-url") == ""


def test_inspect_google_index_status_by_url_domain_groups_by_derived_property(monkeypatch):
    calls = []

    def fake_inspect(**kwargs):
        calls.append(kwargs)
        return indexnow_service.GoogleInspectionResult(
            inspected_count=len(kwargs["urls"]),
            skipped=[],
            items=[],
        )

    monkeypatch.setattr(indexnow_service, "inspect_google_index_status", fake_inspect)

    result = inspect_google_index_status_by_url_domain(
        urls=[
            "https://www.example.com/a",
            "https://www.example.com/b",
            "https://other.example.com/c",
        ],
        access_token="token",
    )

    assert result.inspected_count == 3
    assert [(call["site_url"], call["urls"]) for call in calls] == [
        ("https://www.example.com/", ["https://www.example.com/a", "https://www.example.com/b"]),
        ("https://other.example.com/", ["https://other.example.com/c"]),
    ]


def test_google_access_token_from_service_account_json_rejects_invalid_json():
    with pytest.raises(ValueError):
        google_access_token_from_service_account_json("{bad")


def test_build_sitemap_xml_escapes_urls_and_removes_duplicates():
    sitemap = build_sitemap_xml(
        [
            "https://www.example.com/a?x=1&y=2",
            "https://www.example.com/a?x=1&y=2",
            "not-a-url",
        ]
    )

    assert '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' in sitemap
    assert "<loc>https://www.example.com/a?x=1&amp;y=2</loc>" in sitemap
    assert sitemap.count("<url>") == 1
