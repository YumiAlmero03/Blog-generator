from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse
from xml.etree import ElementTree

from app.services.seo_checker_service import fetch_url


COMMON_SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml", "/wp-sitemap.xml")
MAX_SITEMAPS = 30
MAX_PAGE_URLS = 1000


@dataclass
class WebsitePageDiscoveryResult:
    base_url: str
    pages: list[str] = field(default_factory=list)
    sitemaps: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class HomepageLinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attrs_dict = {name.lower(): value or "" for name, value in attrs}
        href = attrs_dict.get("href", "").strip()
        if href:
            self.links.append(href)


def discover_website_pages(raw_url: str, limit: int = 500) -> WebsitePageDiscoveryResult:
    base_url = _normalize_base_url(raw_url)
    limit = max(1, min(MAX_PAGE_URLS, int(limit or 500)))
    result = WebsitePageDiscoveryResult(base_url=base_url)

    sitemap_urls = _discover_sitemap_urls(base_url, result)
    seen_sitemaps: set[str] = set()
    pending_sitemaps = list(sitemap_urls)
    page_urls: list[str] = []
    seen_pages: set[str] = set()

    while pending_sitemaps and len(seen_sitemaps) < MAX_SITEMAPS and len(page_urls) < limit:
        sitemap_url = pending_sitemaps.pop(0)
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        try:
            sitemap_page_urls, nested_sitemaps = _read_sitemap(sitemap_url)
            result.sitemaps.append(
                {
                    "url": sitemap_url,
                    "status": "found",
                    "page_count": len(sitemap_page_urls),
                    "sitemap_count": len(nested_sitemaps),
                }
            )
        except Exception as exc:
            result.sitemaps.append({"url": sitemap_url, "status": "error", "page_count": 0, "sitemap_count": 0})
            result.errors.append(f"{sitemap_url}: {exc}")
            continue

        for nested_sitemap in nested_sitemaps:
            if nested_sitemap not in seen_sitemaps and nested_sitemap not in pending_sitemaps:
                pending_sitemaps.append(nested_sitemap)

        for page_url in sitemap_page_urls:
            normalized_url = _normalize_discovered_url(page_url)
            if normalized_url and _same_site(base_url, normalized_url) and normalized_url not in seen_pages:
                seen_pages.add(normalized_url)
                page_urls.append(normalized_url)
                if len(page_urls) >= limit:
                    break

    if not page_urls:
        page_urls = _discover_homepage_links(base_url, limit, result)

    result.pages = page_urls[:limit]
    return result


def _discover_sitemap_urls(base_url: str, result: WebsitePageDiscoveryResult) -> list[str]:
    robots_url = urljoin(base_url, "/robots.txt")
    sitemap_urls: list[str] = []
    try:
        robots = fetch_url(robots_url)
        for line in robots.text.splitlines():
            if line.lower().startswith("sitemap:"):
                sitemap_url = line.split(":", 1)[1].strip()
                if sitemap_url:
                    sitemap_urls.append(sitemap_url)
    except Exception as exc:
        result.errors.append(f"{robots_url}: {exc}")

    sitemap_urls.extend(urljoin(base_url, path) for path in COMMON_SITEMAP_PATHS)
    return _unique_urls(sitemap_urls)


def _read_sitemap(sitemap_url: str) -> tuple[list[str], list[str]]:
    response = fetch_url(sitemap_url)
    if not 200 <= response.status_code < 400:
        raise ValueError(f"HTTP {response.status_code}")
    return _parse_sitemap_xml(response.text, sitemap_url)


def _parse_sitemap_xml(xml_text: str, sitemap_url: str = "") -> tuple[list[str], list[str]]:
    try:
        root = ElementTree.fromstring(xml_text.encode("utf-8"))
    except ElementTree.ParseError as exc:
        raise ValueError("Not a valid XML sitemap.") from exc

    page_urls: list[str] = []
    sitemap_urls: list[str] = []
    for element in root.iter():
        if _local_name(element.tag) != "loc" or not element.text:
            continue
        loc = element.text.strip()
        parent_tag = _parent_hint(root)
        if parent_tag == "sitemapindex":
            sitemap_urls.append(urljoin(sitemap_url, loc))
        else:
            page_urls.append(urljoin(sitemap_url, loc))
    return _unique_urls(page_urls), _unique_urls(sitemap_urls)


def _parent_hint(root) -> str:
    return _local_name(root.tag)


def _discover_homepage_links(base_url: str, limit: int, result: WebsitePageDiscoveryResult) -> list[str]:
    try:
        response = fetch_url(base_url)
    except Exception as exc:
        result.errors.append(f"{base_url}: {exc}")
        return []

    parser = HomepageLinkParser()
    parser.feed(response.text)
    pages: list[str] = []
    seen: set[str] = set()
    for href in parser.links:
        normalized_url = _normalize_discovered_url(urljoin(base_url, href))
        if normalized_url and _same_site(base_url, normalized_url) and normalized_url not in seen:
            seen.add(normalized_url)
            pages.append(normalized_url)
            if len(pages) >= limit:
                break
    return pages


def _normalize_base_url(raw_url: str) -> str:
    cleaned = (raw_url or "").strip()
    if not cleaned:
        raise ValueError("Enter a website URL.")
    if not cleaned.lower().startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Use a valid website URL.")
    return f"{parsed.scheme}://{parsed.netloc}"


def _normalize_discovered_url(url: str) -> str:
    cleaned = (url or "").strip()
    if not cleaned:
        return ""
    cleaned, _fragment = urldefrag(cleaned)
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path or "/"
    return parsed._replace(path=path).geturl()


def _same_site(base_url: str, url: str) -> bool:
    return urlparse(base_url).netloc.lower() == urlparse(url).netloc.lower()


def _unique_urls(urls: list[str]) -> list[str]:
    unique_urls: list[str] = []
    seen: set[str] = set()
    for url in urls:
        cleaned = _normalize_discovered_url(url)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique_urls.append(cleaned)
    return unique_urls


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()
