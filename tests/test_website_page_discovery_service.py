from dataclasses import dataclass

from app import create_app
from app.services import website_page_discovery_service as service
from database.common import get_connection
from database.website_index import upsert_website_index_urls


@dataclass
class FakeFetchResult:
    url: str
    status_code: int
    content_type: str
    text: str


def test_discover_website_pages_reads_sitemap_index(monkeypatch):
    responses = {
        "https://example.com/robots.txt": "Sitemap: https://example.com/sitemap_index.xml",
        "https://example.com/sitemap_index.xml": """
            <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <sitemap><loc>https://example.com/page-sitemap.xml</loc></sitemap>
            </sitemapindex>
        """,
        "https://example.com/page-sitemap.xml": """
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url><loc>https://example.com/about#team</loc></url>
              <url><loc>https://example.com/contact</loc></url>
              <url><loc>https://example.com/uploads/hero-image.webp</loc></url>
              <url><loc>https://other.example.com/offsite</loc></url>
            </urlset>
        """,
    }

    def fake_fetch(url, verify_ssl=True):
        if url not in responses:
            raise ValueError("not found")
        return FakeFetchResult(url=url, status_code=200, content_type="application/xml", text=responses[url])

    monkeypatch.setattr(service, "fetch_url", fake_fetch)

    result = service.discover_website_pages("example.com")

    assert result.base_url == "https://example.com"
    assert result.pages == ["https://example.com/about", "https://example.com/contact"]
    assert result.page_items[0]["url"] == "https://example.com/about"
    assert "about" in result.page_items[0]["keywords"]
    assert any(item["url"] == "https://example.com/page-sitemap.xml" for item in result.sitemaps)


def test_discover_website_pages_extracts_page_keywords(monkeypatch):
    responses = {
        "https://example.com/robots.txt": "Sitemap: https://example.com/sitemap.xml",
        "https://example.com/sitemap.xml": """
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url><loc>https://example.com/best-slots-guide</loc></url>
            </urlset>
        """,
        "https://example.com/best-slots-guide": """
            <html>
              <head>
                <title>Best Slots Guide - Example</title>
                <meta name="keywords" content="online slots, slot games">
                <meta name="description" content="Learn the best slot games for new players.">
              </head>
              <body><h1>Best Slots Guide</h1></body>
            </html>
        """,
    }

    def fake_fetch(url, verify_ssl=True):
        if url not in responses:
            raise ValueError("not found")
        content_type = "text/html" if url.endswith("guide") else "application/xml"
        return FakeFetchResult(url=url, status_code=200, content_type=content_type, text=responses[url])

    monkeypatch.setattr(service, "fetch_url", fake_fetch)

    result = service.discover_website_pages("example.com")

    assert result.page_items[0]["url"] == "https://example.com/best-slots-guide"
    assert "online slots" in result.page_items[0]["keywords"]
    assert "slot games" in result.page_items[0]["keywords"]
    assert "Best Slots Guide" in result.page_items[0]["keywords"]
    assert "Learn the best slot games for new players" in result.page_items[0]["keywords"]


def test_parse_urlset_sitemap_removes_duplicates_and_fragments():
    pages, nested = service._parse_sitemap_xml(
        """
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://example.com/a#top</loc></url>
          <url><loc>https://example.com/a</loc></url>
        </urlset>
        """,
        "https://example.com/sitemap.xml",
    )

    assert pages == ["https://example.com/a"]
    assert nested == []


def test_parse_urlset_sitemap_skips_image_urls():
    pages, nested = service._parse_sitemap_xml(
        """
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
          <url>
            <loc>https://example.com/a</loc>
            <image:image><image:loc>https://example.com/uploads/a.jpg</image:loc></image:image>
          </url>
          <url><loc>https://example.com/uploads/b.png</loc></url>
          <url><loc>https://example.com/gallery</loc></url>
        </urlset>
        """,
        "https://example.com/sitemap.xml",
    )

    assert pages == ["https://example.com/a", "https://example.com/gallery"]
    assert nested == []


def test_homepage_link_discovery_skips_image_urls(monkeypatch):
    def fake_fetch(url, verify_ssl=True):
        if url.endswith("/robots.txt") or url.endswith(".xml"):
            raise ValueError("not found")
        return FakeFetchResult(
            url=url,
            status_code=200,
            content_type="text/html",
            text="""
                <a href="/about">About</a>
                <a href="/uploads/logo.svg">Logo</a>
                <a href="/photo.jpeg">Photo</a>
            """,
        )

    monkeypatch.setattr(service, "fetch_url", fake_fetch)

    result = service.discover_website_pages("https://example.com")

    assert result.pages == ["https://example.com/about"]


def test_website_pages_lists_saved_domain_and_downloads_csv():
    urls = ["https://website-pages-route-test.example/a", "https://website-pages-route-test.example/b"]
    try:
        upsert_website_index_urls([
            {"url": urls[0], "page_keywords": "about us, brand"},
            {"url": urls[1], "page_keywords": "contact"},
        ])
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE website_index_urls
                SET google_status = 'indexed',
                    google_coverage_state = 'Submitted and indexed'
                WHERE url = ?
                """,
                (urls[0],),
            )

        app = create_app()
        app.testing = True
        client = app.test_client()

        page_response = client.get("/website-pages?domain=website-pages-route-test.example")
        assert page_response.status_code == 200
        assert b"website-pages-route-test.example" in page_response.data
        assert b"Submitted and indexed" in page_response.data
        assert b"about us" in page_response.data

        csv_response = client.get("/website-pages/download.csv?domain=website-pages-route-test.example")
        assert csv_response.status_code == 200
        assert csv_response.mimetype == "text/csv"
        assert "website-pages-route-test.example/a" in csv_response.get_data(as_text=True)
        assert "page_keywords" in csv_response.get_data(as_text=True)
        assert "about us, brand" in csv_response.get_data(as_text=True)
        assert "google_status" in csv_response.get_data(as_text=True)
    finally:
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM website_index_urls WHERE url IN (?, ?)",
                tuple(urls),
            )


def test_website_pages_saved_domain_list_is_paginated():
    urls = [f"https://website-pages-pagination-test.example/page-{index:03d}" for index in range(1, 56)]
    try:
        upsert_website_index_urls(urls)

        app = create_app()
        app.testing = True
        client = app.test_client()

        first_page = client.get("/website-pages?domain=website-pages-pagination-test.example")
        assert first_page.status_code == 200
        first_page_html = first_page.get_data(as_text=True)
        assert "Showing 1-50 of 55 saved URLs" in first_page_html
        assert "page-055" in first_page_html
        assert "page-001" not in first_page_html

        second_page = client.get("/website-pages?domain=website-pages-pagination-test.example&page=2")
        assert second_page.status_code == 200
        second_page_html = second_page.get_data(as_text=True)
        assert "Showing 51-55 of 55 saved URLs" in second_page_html
        assert "page-001" in second_page_html
    finally:
        with get_connection() as connection:
            placeholders = ",".join("?" for _item in urls)
            connection.execute(
                f"DELETE FROM website_index_urls WHERE url IN ({placeholders})",
                tuple(urls),
            )
