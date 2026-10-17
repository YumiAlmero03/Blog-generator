"""Read metadata and content from pages within a website section."""
import json
import re
import time
from collections import deque
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener

from app.services.reference_link_service import _ReadableTextParser
from app.services.seo_checker_service import (
    FETCH_TIMEOUT, SSL_CONTEXT, USER_AGENT, FetchResult, PageSeoParser,
    _validate_public_http_url,
)
from app.services.website_page_discovery_service import (
    COMMON_SITEMAP_PATHS, MAX_SITEMAPS, _parse_sitemap_xml,
)
from logger import logger

MAX_PAGES = 1000
MAX_SECONDS = 120


class _PublicRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_public_http_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_url(url):
    """Apply the existing public URL checks to initial URLs and every redirect."""
    _validate_public_http_url(url)
    opener = build_opener(HTTPSHandler(context=SSL_CONTEXT), _PublicRedirectHandler())
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xml"})
    with opener.open(request, timeout=FETCH_TIMEOUT) as response:
        text = response.read(2_000_000).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        return FetchResult(response.geturl(), response.status, response.headers.get("content-type", ""), text)


def normalize_url(value):
    value = (value or "").strip()
    if "://" not in value:
        value = "https://" + value
    try:
        parts = urlsplit(value)
        valid = parts.scheme in {"http", "https"} and parts.hostname and not parts.username and not parts.password
        parts.port
    except ValueError:
        valid = False
    if not valid or len(value) > 2048:
        raise ValueError("Enter a valid public http or https website URL without credentials.")
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or "/", urlencode(sorted(query)), ""))


class ContentParser(PageSeoParser):
    def __init__(self):
        super().__init__()
        self.published = ""
        self.time_date = ""

    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        values = dict(attrs)
        name = (values.get("property") or values.get("name") or values.get("itemprop") or "").lower()
        if tag == "meta" and name in {"article:published_time", "datepublished", "pubdate", "publishdate", "date"}:
            self.published = self.published or values.get("content", "")
        if tag == "time" and values.get("datetime") and not any(word in str(values).lower() for word in ("modified", "updated")):
            self.time_date = self.time_date or values["datetime"]


def _schema_date(value):
    if isinstance(value, list):
        return next((date for item in value if (date := _schema_date(item))), "")
    if isinstance(value, dict):
        date = value.get("datePublished")
        if isinstance(date, str):
            return date
        return next((date for item in value.values() if isinstance(item, (list, dict)) and (date := _schema_date(item))), "")
    return ""


def extract_page(html, url):
    parser = ContentParser()
    parser.feed(html)
    readable = _ReadableTextParser(content_tags={"main"})
    readable.feed(html)
    published = parser.published
    for script in parser.schema_scripts:
        if published:
            break
        try:
            published = _schema_date(json.loads(script))
        except (ValueError, RecursionError):
            continue
    return {
        "url": url,
        "post_date": published or parser.time_date,
        "title": " ".join(parser.title_parts).strip() or next(iter(parser.headings["h1"]), ""),
        "meta_description": parser.meta_description,
        "content": "\n".join(readable.article_parts or readable.filtered_parts or readable.text_parts),
    }, parser.links


def collect_website_content(raw_url, limit=1000):
    base = normalize_url(raw_url)
    limit = max(1, min(MAX_PAGES, int(limit)))
    scope = urlsplit(base)
    prefix = scope.path.rstrip("/")
    deadline = time.monotonic() + MAX_SECONDS
    result = {"pages": [], "errors": [], "notes": [], "base_url": base}
    pending = deque([base])
    queued = {base}
    visited = set()

    def in_scope(url):
        parts = urlsplit(url)
        return parts.netloc == scope.netloc and (parts.path.rstrip("/") == prefix or parts.path.startswith(prefix + "/"))

    def enqueue(value, source):
        try:
            url = normalize_url(urljoin(source, value))
        except ValueError:
            return
        if in_scope(url) and url not in queued and not re.search(r"\.(?:xml|pdf|zip|jpe?g|png|gif|svg|webp|css|js|mp4)$", urlsplit(url).path, re.I):
            if len(queued) < MAX_PAGES * 5:
                queued.add(url)
                pending.append(url)
            elif "Discovery queue limit reached; results may be incomplete." not in result["notes"]:
                result["notes"].append("Discovery queue limit reached; results may be incomplete.")

    sitemaps = deque(urljoin(base, path) for path in COMMON_SITEMAP_PATHS)
    try:
        robots = fetch_url(urljoin(base, "/robots.txt"))
        if robots.status_code == 200:
            for line in robots.text.splitlines():
                if line.strip().lower().startswith("sitemap:"):
                    sitemaps.appendleft(urljoin(base, line.split(":", 1)[1].strip()))
    except Exception as exc:
        logger.info("Content discovery robots unavailable: %s", type(exc).__name__)
    seen_maps = set()
    while sitemaps and len(seen_maps) < MAX_SITEMAPS and time.monotonic() < deadline:
        sitemap = sitemaps.popleft()
        if sitemap in seen_maps:
            continue
        seen_maps.add(sitemap)
        try:
            response = fetch_url(sitemap)
            if response.status_code != 200:
                continue
            pages, nested = _parse_sitemap_xml(response.text, sitemap)
            sitemaps.extend(nested)
            for url in pages:
                enqueue(url, sitemap)
        except Exception as exc:
            logger.info("Content discovery sitemap unavailable: %s", type(exc).__name__)
    if sitemaps:
        result["notes"].append("Sitemap discovery stopped at its time or sitemap limit; results may be incomplete.")

    attempts = 0
    while pending and len(result["pages"]) < limit and attempts < MAX_PAGES and time.monotonic() < deadline:
        url = pending.popleft()
        if url in visited:
            continue
        visited.add(url)
        attempts += 1
        try:
            response = fetch_url(url)
            final_url = normalize_url(response.url)
            if not in_scope(final_url):
                result["errors"].append(f"Skipped a redirect outside the selected section: {url}")
                continue
            if final_url != url and final_url in visited:
                continue
            visited.add(final_url)
            if response.status_code != 200:
                raise ValueError("Page returned an unsuccessful HTTP status.")
            if "html" not in response.content_type.lower():
                continue
            page, links = extract_page(response.text, final_url)
            for link in links:
                enqueue(link["href"], final_url)
            # Crawl listing/pagination pages, but export only inner content pages.
            path = urlsplit(final_url).path.rstrip("/")
            pagination = re.search(r"/page/\d+$", path) or any(key.lower() in {"page", "paged", "offset"} for key, _ in parse_qsl(urlsplit(final_url).query))
            if path != prefix and not pagination:
                result["pages"].append(page)
        except Exception as exc:
            logger.warning("Website content page failed (%s): %s", url, type(exc).__name__)
            result["errors"].append(f"Could not read {url}. Check that it is publicly accessible.")
    if pending:
        result["notes"].append("Crawl limit or two-minute time limit reached; these are partial results. Try a smaller website section.")
    return result
