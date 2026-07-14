import io
import json
import random
import re
import zipfile

from docx import Document

from app import create_app
from app.services import website_planner_service
from app.services.website_planner_service import build_website_plan, fetch_google_trends_blog_keywords, parse_keyword_categories, parse_page_list


def test_parse_page_list_deduplicates_lines_and_commas():
    pages = parse_page_list("Home\nAbout Us, Contact Us\nhome\n")

    assert pages == ["Home", "About Us", "Contact Us"]


def test_parse_keyword_categories_accepts_lists_and_deduplicates():
    categories = parse_keyword_categories(["Slots", "Sports, Casino Games", "slots"])

    assert categories == ["Slots", "Sports", "Casino Games"]


def test_build_website_plan_uses_requested_counts_with_random_lists():
    plan = build_website_plan(
        "Home\nAbout Us\nServices",
        "Privacy Policy\nTerms",
        page_count=4,
        trust_page_count=3,
        blog_count=2,
        keyword_categories_text=["Slots"],
        use_google_trends=False,
        rng=random.Random(7),
    )

    assert plan["summary"] == {
        "main_pages": 4,
        "trust_pages": 3,
        "blogs": 2,
        "total": 9,
        "blog_keyword_source": "Category fallback",
    }
    assert len(plan["main_pages"]) == 4
    assert len(plan["trust_pages"]) == 3
    assert len(plan["blogs"]) == 2
    assert all("slots" in item["name"] for item in plan["blogs"])


def test_build_website_plan_filters_brand_names_from_blog_keywords():
    plan = build_website_plan(
        "Home",
        "Privacy Policy",
        page_count=1,
        trust_page_count=1,
        blog_count=4,
        keyword_categories_text=["BrandX", "Slots"],
        brand_names=["BrandX"],
        use_google_trends=False,
        rng=random.Random(3),
    )

    blog_keywords = [item["name"] for item in plan["blogs"]]
    assert blog_keywords
    assert all("brandx" not in keyword.casefold() for keyword in blog_keywords)


def test_fetch_google_trends_blog_keywords_filters_by_category_and_brand(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"""
            <rss>
              <channel>
                <item><title>Slots Bonus Guide</title></item>
                <item><title>BrandX Casino Offer</title></item>
                <item><title>Weather Today</title></item>
              </channel>
            </rss>
            """

    monkeypatch.setattr(website_planner_service, "urlopen", lambda request, timeout: FakeResponse())

    keywords = fetch_google_trends_blog_keywords(["Slots"], ["BrandX"], geo="PH")

    assert [item["name"] for item in keywords] == ["slots bonus guide"]
    assert keywords[0]["source"] == "Google Trends"
    assert "trends.google.com" in keywords[0]["trend_url"]


def test_website_planner_page_renders_and_generates_plan(monkeypatch):
    monkeypatch.setattr(website_planner_service, "fetch_google_trends_blog_keywords", lambda *args, **kwargs: [])

    app = create_app()
    app.testing = True
    client = app.test_client()

    response = client.get("/website-planner")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Website Planner" in html
    assert "How many blogs" in html
    assert "How many pages" in html
    assert "How many trust pages" in html
    assert "Keyword Category" in html
    assert "Slots" in html

    response = client.post(
        "/website-planner",
        data={
            "page_count": "2",
            "trust_page_count": "1",
            "blog_count": "3",
            "keyword_categories": ["Slots"],
            "planner_reference_file": (_docx_upload(), "reference.docx"),
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "5 total item(s)" in html
    assert "VIP Slots Guide" in html
    assert "Headings: Weekly Promotions, Fast Deposits" in html
    assert "Extracted 1 page(s) from DOCX Heading 1/Page sections." in html
    assert "Using uploaded DOCX pages as the core page list." in html
    assert "slots" in html.lower()
    assert "Blog Keywords" in html
    assert "Google Trends" in html
    assert "Print Preview" in html
    assert "Report sections:" in html
    assert "Download report (.docx)" in html
    assert "Using reference: reference.docx" in html
    assert "VIP rewards and weekly slot promotions" in html


def test_website_planner_download_report_contains_required_sections():
    app = create_app()
    app.testing = True
    client = app.test_client()
    plan = {
        "main_pages": [
            {"index": 1, "name": "online slot games", "keyword": "online slot games", "h1": "Best Online Slot Games", "headings": ["Weekly Promotions", "Fast Deposits"]},
            {"index": 2, "name": "Home"},
        ],
        "trust_pages": [{"index": 1, "name": "Privacy Policy"}],
        "blogs": [{"index": 1, "name": "slot bonus guide", "source": "Planner"}],
        "summary": {"main_pages": 2, "trust_pages": 1, "blogs": 1, "total": 4, "blog_keyword_source": "Category fallback"},
    }

    response = client.post(
        "/website-planner/download-report",
        data={
            "planner_client": "PhMacao Casino",
            "planner_domain": "https://example.com",
            "planner_target_market": "Philippines",
            "planner_language": "English",
            "planner_site_type": "Informational / Affiliate Lead Gen",
            "planner_reference_filename": "reference.docx",
            "planner_reference_content": "Existing website content mentions VIP rewards, weekly slot promotions, and fast deposits.",
            "plan_json": json.dumps(plan),
        },
    )

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert "Website_Planner_Report" in response.headers["Content-Disposition"]
    text = _docx_text(response.data)
    for expected in (
        "KEYWORD PLAN",
        "About site",
        "Keyword CLUSTER",
        "CONTENT LAYOUT PLAN",
        "INTERNAL LINKING PLAN",
        "Internal Link Map",
        "Anchor Text Guidelines",
        "BLOG CONTENT CATEGORIES AND CURRENT PAGE-DERIVED TOPICS",
        "SUMMARY DASHBOARD",
        "Current Core Page Mapping",
        "PRIORITY LAUNCH ORDER (First 7 Days)",
        "Step-by-step prompt",
        "Website Content Reference",
        "VIP rewards",
        "Best Online Slot Games",
        "Weekly Promotions",
    ):
        assert expected in text
    assert "Privacy PolicyPrimary Target Page" not in text


def test_settings_page_includes_website_planner_lists():
    app = create_app()
    app.testing = True
    response = app.test_client().get("/settings")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Website Planner Pages" in html
    assert "Pages Main" in html
    assert "Trust Page" in html


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    return re.sub(r"<[^>]+>", "", xml)


def _docx_upload() -> io.BytesIO:
    doc = Document()
    doc.add_paragraph("VIP Slots Guide", style="Heading 1")
    doc.add_paragraph("Keyword: vip slots")
    doc.add_paragraph("Weekly Promotions", style="Heading 2")
    doc.add_paragraph("VIP rewards and weekly slot promotions.")
    doc.add_paragraph("Fast Deposits", style="Heading 2")
    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    return output
