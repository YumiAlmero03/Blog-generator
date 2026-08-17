from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse
from xml.etree import ElementTree

from app.services.seo_checker_service import fetch_url


COMMON_SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml", "/wp-sitemap.xml")
MAX_SITEMAPS = 30
MAX_PAGE_URLS = 1000
IMAGE_EXTENSIONS = {
    ".apng",
    ".avif",
    ".bmp",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".tif",
    ".tiff",
    ".webp",
}


@dataclass
class WebsitePageDiscoveryResult:
    base_url: str
    pages: list[str] = field(default_factory=list)
    page_items: list[dict] = field(default_factory=list)
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


class PageKeywordParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._title_depth = 0
        self._heading_depth = 0
        self._skip_depth = 0
        self.title_parts: list[str] = []
        self.heading_parts: list[str] = []
        self.meta_keywords: list[str] = []
        self.meta_descriptions: list[str] = []

    def handle_starttag(self, tag, attrs):
        cleaned_tag = (tag or "").lower()
        attrs_dict = {name.lower(): value or "" for name, value in attrs}
        if cleaned_tag in {"script", "style", "noscript", "svg", "canvas"}:
            self._skip_depth += 1
        if cleaned_tag == "title":
            self._title_depth += 1
        if cleaned_tag in {"h1", "h2", "h3"}:
            self._heading_depth += 1
        if cleaned_tag == "meta":
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").strip().lower()
            content = attrs_dict.get("content", "").strip()
            if name == "keywords" and content:
                self.meta_keywords.extend(_split_keyword_text(content))
            elif name in {"description", "og:description", "twitter:description"} and content:
                self.meta_descriptions.append(content)

    def handle_endtag(self, tag):
        cleaned_tag = (tag or "").lower()
        if cleaned_tag in {"script", "style", "noscript", "svg", "canvas"} and self._skip_depth:
            self._skip_depth -= 1
        if cleaned_tag == "title" and self._title_depth:
            self._title_depth -= 1
        if cleaned_tag in {"h1", "h2", "h3"} and self._heading_depth:
            self._heading_depth -= 1

    def handle_data(self, data):
        if self._skip_depth:
            return
        text = _clean_phrase(data)
        if not text:
            return
        if self._title_depth:
            self.title_parts.append(text)
        if self._heading_depth:
            self.heading_parts.append(text)


def discover_website_pages(raw_url: str, limit: int = 50, allow_private: bool = False) -> WebsitePageDiscoveryResult:
    base_url = _normalize_base_url(raw_url)
    limit = max(1, min(MAX_PAGE_URLS, int(limit or 50)))
    result = WebsitePageDiscoveryResult(base_url=base_url)

    sitemap_urls = _discover_sitemap_urls(base_url, result, allow_private=allow_private)
    seen_sitemaps: set[str] = set()
    pending_sitemaps = list(sitemap_urls)
    page_urls: list[str] = []
    seen_pages: set[str] = set()

    while pending_sitemaps and len(seen_sitemaps) < MAX_SITEMAPS and len(page_urls) < MAX_PAGE_URLS:
        sitemap_url = pending_sitemaps.pop(0)
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        try:
            sitemap_page_urls, nested_sitemaps = _read_sitemap(sitemap_url, allow_private=allow_private)
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
                if len(page_urls) >= MAX_PAGE_URLS:
                    break

    if not page_urls:
        page_urls = _discover_homepage_links(base_url, MAX_PAGE_URLS, result, allow_private=allow_private)

    result.pages = _sort_first_layer_pages(base_url, page_urls)[:limit]
    result.page_items = _build_page_items(result.pages, result, allow_private=allow_private)
    return result


def _build_page_items(page_urls: list[str], result: WebsitePageDiscoveryResult, allow_private: bool = False) -> list[dict]:
    page_items = []
    for page_url in page_urls:
        page_items.append(
            {
                "url": page_url,
                "keywords": extract_page_keywords(page_url, result, allow_private=allow_private),
            }
        )
    return page_items


def extract_page_keywords(page_url: str, result: WebsitePageDiscoveryResult | None = None, allow_private: bool = False) -> list[str]:
    fallback_keywords = _keywords_from_url(page_url)
    try:
        response = _fetch_discovery_url(page_url, allow_private=allow_private)
    except Exception as exc:
        if result is not None:
            result.errors.append(f"{page_url}: keyword fetch failed: {exc}")
        return fallback_keywords

    content_type = (getattr(response, "content_type", "") or "").lower()
    text = getattr(response, "text", "") or ""
    if "html" not in content_type and "<html" not in text[:1000].lower():
        return fallback_keywords

    parser = PageKeywordParser()
    parser.feed(text)
    candidates = []
    candidates.extend(parser.meta_keywords)
    candidates.extend(_split_phrase_sources(parser.title_parts))
    candidates.extend(_split_phrase_sources(parser.heading_parts))
    candidates.extend(_split_phrase_sources(parser.meta_descriptions[:1]))
    candidates.extend(fallback_keywords)
    return _dedupe_keywords(candidates)[:10]


def _discover_sitemap_urls(base_url: str, result: WebsitePageDiscoveryResult, allow_private: bool = False) -> list[str]:
    robots_url = urljoin(base_url, "/robots.txt")
    sitemap_urls: list[str] = []
    try:
        robots = _fetch_discovery_url(robots_url, allow_private=allow_private)
        for line in robots.text.splitlines():
            if line.lower().startswith("sitemap:"):
                sitemap_url = line.split(":", 1)[1].strip()
                if sitemap_url:
                    sitemap_urls.append(sitemap_url)
    except Exception as exc:
        result.errors.append(f"{robots_url}: {exc}")

    sitemap_urls.extend(urljoin(base_url, path) for path in COMMON_SITEMAP_PATHS)
    return _unique_urls(sitemap_urls)


def _read_sitemap(sitemap_url: str, allow_private: bool = False) -> tuple[list[str], list[str]]:
    response = _fetch_discovery_url(sitemap_url, allow_private=allow_private)
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


def _discover_homepage_links(base_url: str, limit: int, result: WebsitePageDiscoveryResult, allow_private: bool = False) -> list[str]:
    try:
        response = _fetch_discovery_url(base_url, allow_private=allow_private)
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


def _fetch_discovery_url(url: str, allow_private: bool = False):
    if allow_private:
        return fetch_url(url, allow_private=True)
    return fetch_url(url)


def _normalize_discovered_url(url: str) -> str:
    cleaned = (url or "").strip()
    if not cleaned:
        return ""
    cleaned, _fragment = urldefrag(cleaned)
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path or "/"
    if _is_image_url_path(path):
        return ""
    return parsed._replace(path=path).geturl()


def _same_site(base_url: str, url: str) -> bool:
    return urlparse(base_url).netloc.lower() == urlparse(url).netloc.lower()


def _sort_first_layer_pages(base_url: str, urls: list[str]) -> list[str]:
    indexed_urls = list(enumerate(urls))
    return [url for _index, url in sorted(indexed_urls, key=lambda item: (_url_path_depth(base_url, item[1]), item[0]))]


def _url_path_depth(base_url: str, url: str) -> int:
    parsed_base = urlparse(base_url)
    parsed_url = urlparse(url)
    if parsed_base.netloc.lower() != parsed_url.netloc.lower():
        return 999
    segments = [segment for segment in (parsed_url.path or "/").split("/") if segment]
    return len(segments)


def _unique_urls(urls: list[str]) -> list[str]:
    unique_urls: list[str] = []
    seen: set[str] = set()
    for url in urls:
        cleaned = _normalize_discovered_url(url)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique_urls.append(cleaned)
    return unique_urls


def _is_image_url_path(path: str) -> bool:
    cleaned_path = (path or "").lower()
    return any(cleaned_path.endswith(extension) for extension in IMAGE_EXTENSIONS)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "page",
    "the",
    "to",
    "with",
    "your",
}


def _split_keyword_text(value: str) -> list[str]:
    return [_clean_phrase(item) for item in re.split(r"[,;|]+", value or "") if _clean_phrase(item)]


def _split_phrase_sources(values: list[str]) -> list[str]:
    keywords = []
    for value in values:
        cleaned = _clean_phrase(value)
        if not cleaned:
            continue
        keywords.append(cleaned)
        words = [word for word in cleaned.split() if word.casefold() not in STOP_WORDS]
        if 2 <= len(words) <= 6:
            keywords.append(" ".join(words))
    return keywords


def _keywords_from_url(url: str) -> list[str]:
    parsed = urlparse(url or "")
    path = parsed.path.strip("/")
    if not path:
        return []
    segments = [segment for segment in path.split("/") if segment]
    candidates = []
    for segment in segments[-2:]:
        cleaned = _clean_phrase(re.sub(r"[-_]+", " ", segment))
        if cleaned:
            candidates.append(cleaned)
    return _dedupe_keywords(candidates)


def _dedupe_keywords(values: list[str]) -> list[str]:
    keywords = []
    seen = set()
    for value in values:
        cleaned = _clean_phrase(value)
        if not cleaned:
            continue
        normalized = cleaned.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        keywords.append(cleaned)
    return keywords


def _clean_phrase(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    text = re.sub(r"\s+[-|:]\s+.*$", "", text).strip()
    text = re.sub(r"[^\w &'/-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -/'")
    if len(text) < 3 or len(text) > 90:
        return ""
    words = text.split()
    if len(words) == 1 and words[0].casefold() in STOP_WORDS:
        return ""
    return text
