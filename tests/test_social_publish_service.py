import json
from urllib.parse import parse_qs

from app.services import social_publish_service as service


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, *_args):
        return json.dumps({"id": "123_456"}).encode("utf-8")


def test_publish_facebook_page_post_posts_to_page_feed(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = parse_qs(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(service, "urlopen", fake_urlopen)

    result = service.publish_facebook_page_post(
        {
            "platform_account_id": "123",
            "account_name": "Example Page",
            "access_token": "token",
        },
        message="Hello Facebook",
        link="https://example.com",
        graph_version="v99.0",
    )

    assert captured["url"] == "https://graph.facebook.com/v99.0/123/feed"
    assert captured["payload"]["message"] == ["Hello Facebook"]
    assert captured["payload"]["link"] == ["https://example.com"]
    assert captured["payload"]["access_token"] == ["token"]
    assert result.remote_post_id == "123_456"
    assert result.url == "https://www.facebook.com/123_456"
