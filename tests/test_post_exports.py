import json
from xml.etree import ElementTree as ET

import pytest
from flask import Flask

from app.controllers import post_controller
from app.services.post_export_service import export_post, normalize_post
from database import common
from database.generation_history import get_generation_history_item
from database.schema import init_db

HEADERS = {"X-Requested-With": "XMLHttpRequest"}


def payload(generator="blog"):
    return dict(generator=generator, selected_title="Casino & slots – guide", category="Slots",
                meta_description_choice="Helpful casino & slots guide.", content_html='<h2>Guide</h2><p>Edited content &amp; tips.</p><table><tr><td>Value</td></tr></table>',
                keyword="slots", brand="", language="English", tags_json='["slots", "guide"]')


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "DB_PATH", tmp_path / "posts.db")
    init_db()
    app = Flask(__name__)
    app.add_url_rule("/posts/save", view_func=post_controller.save_post, methods=["POST"])
    app.add_url_rule("/posts/download", view_func=post_controller.download_post, methods=["POST"])
    app.testing = True
    return app.test_client()


@pytest.mark.parametrize("generator", ["blog", "rework", "news"])
def test_autosave_then_save_updates_same_draft(client, generator):
    data = payload(generator)
    data.update(autosave=True, content_html="")
    response = client.post("/posts/save", json=data, headers=HEADERS)
    assert response.status_code == 200
    history_id = response.json["history_id"]
    data.update(payload(generator), history_id=str(history_id), autosave=False)
    data["meta_description_choice"] = "The second description is selected."
    response = client.post("/posts/save", json=data, headers=HEADERS)
    assert response.status_code == 200
    assert response.json["history_id"] == history_id
    item = get_generation_history_item(history_id)
    assert item["content"] == data["content_html"]
    assert item["meta_description"] == data["meta_description_choice"]
    assert json.loads(item["prompt_inputs"])["category"] == "Slots"
    assert json.loads(item["prompt_inputs"])["news_generator"] == (generator == "news")
    with common.get_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM generation_history").fetchone()[0] == 1
        connection.execute("UPDATE generation_history SET post_link = 'https://example.com/post', saved_at = '2026-01-01' WHERE id = ?", (history_id,))
    data.update(autosave=True, category="Casino")
    assert client.post("/posts/save", json=data, headers=HEADERS).status_code == 200
    item = get_generation_history_item(history_id)
    assert item["post_link"] == "https://example.com/post"
    assert item["saved_at"] == "2026-01-01"
    assert json.loads(item["prompt_inputs"])["category"] == "Casino"


@pytest.mark.parametrize("field", ["selected_title", "meta_description_choice", "category", "content_html"])
@pytest.mark.parametrize("route", ["save", "download"])
def test_required_fields(client, field, route):
    data = payload()
    data[field] = ""
    assert client.post("/posts/" + route, json=data, headers=HEADERS).status_code == 400
    with common.get_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM generation_history").fetchone()[0] == 0


def test_csrf_and_bad_data_rejected(client):
    assert client.post("/posts/save", json=payload()).status_code == 400
    assert client.post("/posts/save", json=payload(), headers={**HEADERS, "Origin": "https://foreign.example"}).status_code == 400
    for overrides in ({"history_id": "999999"}, {"category": "unexpected"}, {"tags_json": "{}"}, {"selected_title": []}, {"generator": "page"}):
        assert client.post("/posts/save", json={**payload(), **overrides}, headers=HEADERS).status_code == 400


@pytest.mark.parametrize("generator", ["blog", "rework", "news"])
def test_json_and_wordpress_share_post_data(client, generator):
    data = payload(generator)
    response = client.post("/posts/download", json={**data, "format": "json"}, headers=HEADERS)
    assert response.status_code == 200
    post = response.json
    assert post["content_html"] == data["content_html"]
    assert post["category"] == "Slots"
    assert post["status"] == "draft"
    assert "attachment" in response.headers["Content-Disposition"]
    response = client.post("/posts/download", json={**data, "format": "wordpress"}, headers=HEADERS)
    assert response.status_code == 200
    root = ET.fromstring(response.data)
    ns = {"wp": "http://wordpress.org/export/1.2/", "content": "http://purl.org/rss/1.0/modules/content/"}
    assert root.findtext("channel/wp:wxr_version", namespaces=ns) == "1.2"
    item = root.find("channel/item")
    assert item.findtext("title") == post["title"]
    assert item.findtext("content:encoded", namespaces=ns) == post["content_html"]
    assert item.findtext("wp:status", namespaces=ns) == post["status"]
    assert item.findtext("category[@domain='category']") == post["category"]
    assert [tag.text for tag in item.findall("category[@domain='post_tag']")] == post["tags"]
    metadata = {meta.findtext("wp:meta_key", namespaces=ns): meta.findtext("wp:meta_value", namespaces=ns) for meta in item.findall("wp:postmeta", ns)}
    assert metadata["_yoast_wpseo_metadesc"] == post["meta_description"]
    assert metadata["rank_math_description"] == post["meta_description"]


def test_xml_handles_unicode_and_cdata_terminator():
    post = normalize_post({**payload(), "selected_title": "カジノ & slots", "content_html": "<p>Unicode café ]]> &amp; more</p>"})
    xml, _ = export_post(post, "wordpress")
    assert ET.fromstring(xml).findtext("channel/item/title") == post["title"]


@pytest.mark.parametrize("title, expected", [
    ("Casino login", "Navigational"),
    ("How to deposit at a casino", "Transactional"),
    ("Best slots guide", "Slots"),
    ("Casino guide", "Casino"),
    ("Product comparison", "Commercial"),
    ("How to keep an account safe", "Informational"),
    ("A new announcement", "General"),
])
def test_automatic_category(title, expected):
    data = {**payload(), "category": "Auto", "selected_title": title, "keyword": ""}
    assert normalize_post(data)["category"] == expected
    assert normalize_post({**data, "category": "News"})["category"] == "News"


@pytest.mark.parametrize("generator", ["blog", "rework", "news"])
def test_auto_category_saved_and_exported(client, generator):
    data = {**payload(generator), "category": "Auto"}
    response = client.post("/posts/save", json=data, headers=HEADERS)
    assert response.status_code == 200
    assert response.json["category"] == "Slots"
    item = get_generation_history_item(response.json["history_id"])
    inputs = json.loads(item["prompt_inputs"])
    assert inputs["category"] == "Slots"
    assert inputs["category_mode"] == "auto"
    response = client.post("/posts/download", json=data, headers=HEADERS)
    assert response.json["category"] == "Slots"
    if generator == "news":
        assert normalize_post({**data, "keyword": "", "selected_title": "Today's announcement"})["category"] == "News"
