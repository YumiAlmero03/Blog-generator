import ipaddress
import json
import re
import socket
import ssl
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import certifi

from app.services.provider_service import get_provider
from logger import logger
from utils import extract_json_string


FETCH_TIMEOUT = 12
USER_AGENT = "AutoBlogGeneratorSeoChecker/1.0"
COMMON_SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml")
LINK_HEALTH_CHECK_LIMIT = 50
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
UNVERIFIED_SSL_CONTEXT = ssl._create_unverified_context()


@dataclass
class FetchResult:
    url: str
    status_code: int
    content_type: str
    text: str
    ssl_verified: bool = True
    ssl_warning: str = ""


class PageSeoParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts = []
        self.meta_description = ""
        self.canonical = ""
        self.open_graph = {}
        self.twitter_cards = {}
        self.images = []
        self.headings = {f"h{level}": [] for level in range(1, 7)}
        self.heading_sequence = []
        self.links = []
        self.text_parts = []
        self._tag_stack = []
        self._heading_stack = []
        self._open_link_indexes = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = {name.lower(): (value or "") for name, value in attrs}
        tag = tag.lower()
        self._tag_stack.append(tag)

        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

        if tag == "meta":
            meta_name = attrs_dict.get("name", "").lower()
            meta_property = attrs_dict.get("property", "").lower()
            content = attrs_dict.get("content", "").strip()
            if meta_name == "description":
                self.meta_description = content
            elif meta_property.startswith("og:"):
                self.open_graph[meta_property] = content
            elif meta_name.startswith("twitter:"):
                self.twitter_cards[meta_name] = content
        elif tag == "link":
            rel_values = {value.strip().lower() for value in attrs_dict.get("rel", "").split()}
            if "canonical" in rel_values:
                self.canonical = attrs_dict.get("href", "").strip()
        elif tag == "img":
            self.images.append(
                {
                    "src": attrs_dict.get("src", "").strip(),
                    "alt": attrs_dict.get("alt", "").strip(),
                    "has_alt": "alt" in attrs_dict and bool(attrs_dict.get("alt", "").strip()),
                }
            )
        elif tag == "a":
            href = attrs_dict.get("href", "").strip()
            if href:
                self.links.append({"href": href, "text": ""})
                self._open_link_indexes.append(len(self.links) - 1)
        elif tag in self.headings:
            self._heading_stack.append({"tag": tag, "parts": []})

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.headings:
            self._flush_heading(tag)
        elif tag == "a" and self._open_link_indexes:
            self._open_link_indexes.pop()

        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data):
        text = " ".join(data.split())
        if not text or self._skip_depth:
            return

        current_tag = self._tag_stack[-1] if self._tag_stack else ""
        if self._heading_stack:
            self._heading_stack[-1]["parts"].append(text)
        for link_index in self._open_link_indexes:
            self.links[link_index]["text"] = " ".join([self.links[link_index]["text"], text]).strip()

        if current_tag == "title":
            self.title_parts.append(text)
        elif current_tag not in {"head", "meta", "link"}:
            self.text_parts.append(text)

    @property
    def title(self):
        return " ".join(self.title_parts).strip()

    @property
    def body_text(self):
        return " ".join(self.text_parts).strip()

    def _flush_heading(self, tag: str):
        for index in range(len(self._heading_stack) - 1, -1, -1):
            if self._heading_stack[index]["tag"] == tag:
                heading = self._heading_stack.pop(index)
                text = " ".join(" ".join(heading["parts"]).split()).strip()
                if text:
                    self.headings[tag].append(text)
                    self.heading_sequence.append({"level": tag, "text": text})
                return


def run_seo_audit(raw_url: str, verify_ssl: bool = True) -> dict:
    url = _normalize_url(raw_url)
    page = fetch_url(url, verify_ssl=verify_ssl)
    parser = PageSeoParser()
    parser.feed(page.text)

    parsed_url = urlparse(page.url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    robots_result = _fetch_optional_text(urljoin(base_url, "/robots.txt"), verify_ssl=page.ssl_verified)
    sitemap_result = _check_sitemaps(base_url, robots_result.get("text", ""), verify_ssl=page.ssl_verified)
    link_report = _build_link_report(parser.links, page.url, base_url, verify_ssl=page.ssl_verified)
    scrape_report = _build_scrape_report(parser, link_report)
    checks = _build_checks(parser, page, sitemap_result, robots_result, link_report)
    score = _score_checks(checks)
    ai_summary = _generate_ai_summary(parser, checks, score, page.url, scrape_report)

    return {
        "url": page.url,
        "status_code": page.status_code,
        "content_type": page.content_type,
        "score": score,
        "grade": _grade(score),
        "checks": checks,
        "ai_summary": ai_summary,
        "stats": {
            "title": parser.title,
            "title_length": len(parser.title),
            "meta_description": parser.meta_description,
            "meta_description_length": len(parser.meta_description),
            "word_count": _word_count(parser.body_text),
            "image_count": len(parser.images),
            "missing_alt_count": sum(1 for image in parser.images if not image["has_alt"]),
            "h1_count": len(parser.headings["h1"]),
            "h2_count": len(parser.headings["h2"]),
            "canonical": parser.canonical,
            "open_graph": parser.open_graph,
            "twitter_cards": parser.twitter_cards,
            "robots_found": robots_result.get("found", False),
            "robots_url": robots_result.get("url", ""),
            "robots_status_code": robots_result.get("status_code"),
            "robots_sitemap_count": len(_sitemap_urls_from_robots(robots_result.get("text", ""))),
            "sitemaps": sitemap_result["sitemaps"],
            "heading_outline": parser.headings,
            "heading_sequence": parser.heading_sequence,
            "scrape_report": scrape_report,
            "links": link_report,
            "ssl_verified": page.ssl_verified,
            "ssl_warning": page.ssl_warning,
        },
    }


def fetch_url(url: str, verify_ssl: bool = True) -> FetchResult:
    _validate_public_http_url(url)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    ssl_context = SSL_CONTEXT if verify_ssl else UNVERIFIED_SSL_CONTEXT
    try:
        with urlopen(request, timeout=FETCH_TIMEOUT, context=ssl_context) as response:
            content_type = response.headers.get("content-type", "")
            charset = response.headers.get_content_charset() or "utf-8"
            raw = response.read(2_000_000)
            return FetchResult(
                url=response.geturl(),
                status_code=getattr(response, "status", 200),
                content_type=content_type,
                text=raw.decode(charset, errors="replace"),
                ssl_verified=verify_ssl,
            )
    except HTTPError as exc:
        body = exc.read(200_000).decode("utf-8", errors="replace")
        return FetchResult(
            url=url,
            status_code=exc.code,
            content_type=exc.headers.get("content-type", ""),
            text=body,
            ssl_verified=verify_ssl,
        )
    except URLError as exc:
        if verify_ssl and _is_ssl_certificate_error(exc):
            try:
                result = fetch_url(url, verify_ssl=False)
                result.ssl_warning = _ssl_error_message(exc)
                return result
            except Exception as fallback_exc:
                raise ValueError(
                    f"{_ssl_error_message(exc)} The checker also could not fetch the page with SSL verification disabled: {fallback_exc}"
                ) from fallback_exc
        if _is_ssl_certificate_error(exc):
            raise ValueError(_ssl_error_message(exc)) from exc
        raise ValueError(f"Could not reach that website: {exc.reason}") from exc


def _is_ssl_certificate_error(exc: URLError) -> bool:
    reason_obj = getattr(exc, "reason", exc)
    reason = str(reason_obj)
    return (
        isinstance(reason_obj, ssl.SSLError)
        or "CERTIFICATE_VERIFY_FAILED" in reason
        or "certificate" in reason.lower()
        or "ssl" in reason.lower()
    )


def _ssl_error_message(exc: URLError) -> str:
    reason = str(getattr(exc, "reason", exc))
    if "cloudflare origin certificate" in reason.lower():
        return (
            "The website is serving a Cloudflare Origin Certificate directly. "
            "That certificate is meant for Cloudflare-to-origin traffic, not public browser/Python clients. "
            "In Cloudflare, make sure the DNS record is proxied, or install a public certificate such as Let's Encrypt on the origin server."
        )
    return (
        "Could not verify that website's SSL certificate. "
        "The audit can continue by ignoring SSL verification, but the website certificate chain should still be fixed."
    )


def _normalize_url(raw_url: str) -> str:
    cleaned = (raw_url or "").strip()
    if not cleaned:
        raise ValueError("Enter a website URL to check.")
    if not re.match(r"^https?://", cleaned, flags=re.IGNORECASE):
        cleaned = f"https://{cleaned}"
    return cleaned


def _validate_public_http_url(url: str):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Use a valid http or https website URL.")

    hostname = parsed.hostname or ""
    if hostname in {"localhost", "0.0.0.0"}:
        raise ValueError("Local/private addresses cannot be checked from this page.")

    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError("Could not resolve that website hostname.") from exc

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("Local/private addresses cannot be checked from this page.")


def _fetch_optional_text(url: str, verify_ssl: bool = True) -> dict:
    try:
        result = fetch_url(url, verify_ssl=verify_ssl)
    except Exception:
        return {"found": False, "url": url, "status_code": None, "text": ""}
    return {
        "found": 200 <= result.status_code < 400,
        "url": result.url,
        "status_code": result.status_code,
        "text": result.text if 200 <= result.status_code < 400 else "",
    }


def _sitemap_urls_from_robots(robots_text: str) -> list[str]:
    sitemap_urls = []
    for line in robots_text.splitlines():
        if line.lower().startswith("sitemap:"):
            sitemap_urls.append(line.split(":", 1)[1].strip())
    return sitemap_urls


def _check_sitemaps(base_url: str, robots_text: str, verify_ssl: bool = True) -> dict:
    sitemap_urls = _sitemap_urls_from_robots(robots_text)

    sitemap_urls.extend(urljoin(base_url, path) for path in COMMON_SITEMAP_PATHS)
    seen = set()
    unique_sitemap_urls = []
    for sitemap_url in sitemap_urls:
        if sitemap_url and sitemap_url not in seen:
            seen.add(sitemap_url)
            unique_sitemap_urls.append(sitemap_url)

    sitemaps = []
    for sitemap_url in unique_sitemap_urls[:6]:
        result = _fetch_optional_text(sitemap_url, verify_ssl=verify_ssl)
        text = result.get("text", "")
        is_xml_sitemap = "<urlset" in text.lower() or "<sitemapindex" in text.lower()
        sitemaps.append(
            {
                "url": sitemap_url,
                "found": result.get("found", False) and is_xml_sitemap,
                "status_code": result.get("status_code"),
            }
        )

    return {"sitemaps": sitemaps, "found": any(item["found"] for item in sitemaps)}


def _build_checks(parser: PageSeoParser, page: FetchResult, sitemap_result: dict, robots_result: dict, link_report: dict) -> list[dict]:
    word_count = _word_count(parser.body_text)
    missing_alt_count = sum(1 for image in parser.images if not image["has_alt"])
    title_length = len(parser.title)
    meta_length = len(parser.meta_description)

    return [
        _check(
            "Meta title",
            "pass" if 30 <= title_length <= 65 else "fail" if not parser.title else "warn",
            f"{title_length} characters" if parser.title else "Missing title tag",
            "Add one clear page title around 30-65 characters." if not parser.title else "Keep the title clear and within 30-65 characters.",
            18,
        ),
        _check(
            "Meta description",
            "pass" if 130 <= meta_length <= 160 else "fail" if not parser.meta_description else "warn",
            f"{meta_length} characters" if parser.meta_description else "Missing meta description",
            "Write one useful search snippet around 130-160 characters.",
            16,
        ),
        _check(
            "Image alt text",
            "pass" if missing_alt_count == 0 else "fail",
            f"{missing_alt_count} of {len(parser.images)} images missing alt text",
            "Add descriptive alt text to meaningful images; decorative images can use empty alt attributes.",
            14,
        ),
        _check(
            "Content depth",
            "pass" if word_count >= 500 else "warn" if word_count >= 250 else "fail",
            f"{word_count} words found",
            "Expand the visible copy with helpful, specific content for the page topic.",
            16,
        ),
        _check(
            "Heading structure",
            "pass" if len(parser.headings["h1"]) == 1 and len(parser.headings["h2"]) >= 1 else "fail" if not parser.headings["h1"] else "warn",
            f"{len(parser.headings['h1'])} H1, {len(parser.headings['h2'])} H2 headings",
            "Use one H1 and organize the page with useful H2 sections.",
            10,
        ),
        _check(
            "Canonical URL",
            "pass" if parser.canonical else "warn",
            parser.canonical or "No canonical tag found",
            "Add a canonical link when duplicate URL variations may exist.",
            8,
        ),
        _check(
            "Sitemap",
            "pass" if sitemap_result["found"] else "warn",
            "Sitemap found" if sitemap_result["found"] else "No XML sitemap found in robots.txt or common sitemap paths",
            "Publish an XML sitemap and reference it in robots.txt.",
            10,
        ),
        _check(
            "Robots.txt",
            "pass" if robots_result.get("found") else "warn",
            "Robots.txt found" if robots_result.get("found") else "Robots.txt not found",
            "Add robots.txt with sitemap references and crawler rules.",
            8,
        ),
        _check(
            "Social cards",
            "pass" if parser.open_graph.get("og:title") and parser.open_graph.get("og:description") else "warn",
            f"{len(parser.open_graph)} Open Graph tag(s), {len(parser.twitter_cards)} Twitter card tag(s)",
            "Add Open Graph and Twitter card tags so shared links have useful previews.",
            6,
        ),
        _check(
            "Internal links",
            "pass" if link_report["internal_count"] >= 1 else "warn",
            f"{link_report['internal_count']} internal, {link_report['external_count']} external",
            "Add relevant internal links to help visitors and crawlers discover related pages.",
            5,
        ),
        _check(
            "Sample link health",
            "pass" if link_report["broken_sample_count"] == 0 else "warn",
            f"{link_report['broken_sample_count']} broken/unreachable link(s), including {link_report['not_found_count']} 404 link(s), in {len(link_report['sample_checks'])} checked link(s)",
            "Review broken links and update or remove URLs that no longer resolve.",
            5,
        ),
    ]


def _check(name: str, status: str, detail: str, recommendation: str, weight: int) -> dict:
    return {
        "name": name,
        "status": status,
        "detail": detail,
        "recommendation": recommendation,
        "weight": weight,
    }


def _score_checks(checks: list[dict]) -> int:
    earned = 0
    total = 0
    for check in checks:
        weight = check["weight"]
        total += weight
        if check["status"] == "pass":
            earned += weight
        elif check["status"] == "warn":
            earned += weight * 0.55
    return round((earned / total) * 100) if total else 0


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def _build_link_report(links: list, page_url: str, base_url: str, verify_ssl: bool = True) -> dict:
    parsed_base = urlparse(base_url)
    normalized_links = []
    for link in links:
        if isinstance(link, dict):
            href = link.get("href", "")
            anchor_text = " ".join(str(link.get("text", "")).split()).strip()
        else:
            href = link
            anchor_text = ""
        cleaned = (href or "").strip()
        if not cleaned or cleaned.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute_url = urljoin(page_url, cleaned)
        parsed_link = urlparse(absolute_url)
        if parsed_link.scheme not in {"http", "https"} or not parsed_link.netloc:
            continue
        link_type = "internal" if parsed_link.netloc == parsed_base.netloc else "external"
        normalized_links.append({"url": absolute_url, "text": anchor_text, "type": link_type})

    sample_checks = []
    seen = set()
    for item in normalized_links:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        if len(sample_checks) >= LINK_HEALTH_CHECK_LIMIT:
            break
        sample_checks.append(_check_link_url(item["url"], item["type"], verify_ssl=verify_ssl))
    not_found_links = [item for item in sample_checks if item.get("status_code") == 404]

    return {
        "total_count": len(normalized_links),
        "internal_count": sum(1 for item in normalized_links if item["type"] == "internal"),
        "external_count": sum(1 for item in normalized_links if item["type"] == "external"),
        "items": normalized_links,
        "sample_checks": sample_checks,
        "broken_sample_count": sum(1 for item in sample_checks if item["status"] in {"broken", "unreachable"}),
        "checked_count": len(sample_checks),
        "not_found_count": len(not_found_links),
        "not_found_links": not_found_links,
    }


def _build_scrape_report(parser: PageSeoParser, link_report: dict) -> dict:
    images = [
        {
            "src": image.get("src", ""),
            "alt": image.get("alt", ""),
            "has_alt": image.get("has_alt", False),
        }
        for image in parser.images
    ]
    headings = {
        level: list(values)
        for level, values in parser.headings.items()
    }
    heading_total = sum(len(values) for values in headings.values())

    return {
        "headings": headings,
        "heading_sequence": list(parser.heading_sequence),
        "heading_total": heading_total,
        "images": images,
        "image_total": len(images),
        "images_with_alt": sum(1 for image in images if image["has_alt"]),
        "images_missing_alt": sum(1 for image in images if not image["has_alt"]),
        "links": link_report.get("items", []),
        "link_total": link_report.get("total_count", 0),
        "internal_link_total": link_report.get("internal_count", 0),
        "external_link_total": link_report.get("external_count", 0),
    }


def _check_link_url(url: str, link_type: str, verify_ssl: bool = True) -> dict:
    try:
        _validate_public_http_url(url)
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"}, method="HEAD")
        ssl_context = SSL_CONTEXT if verify_ssl else UNVERIFIED_SSL_CONTEXT
        with urlopen(request, timeout=6, context=ssl_context) as response:
            status_code = getattr(response, "status", 200)
    except HTTPError as exc:
        status_code = exc.code
    except Exception:
        return {"url": url, "type": link_type, "status_code": None, "status": "unreachable"}

    if 200 <= status_code < 400:
        status = "ok"
    elif 400 <= status_code < 600:
        status = "broken"
    else:
        status = "warning"
    return {"url": url, "type": link_type, "status_code": status_code, "status": status}


def _generate_ai_summary(parser: PageSeoParser, checks: list[dict], score: int, url: str, scrape_report: dict) -> dict:
    fallback = _fallback_recommendations(checks)
    prompt = {
        "task": "Return concise SEO audit recommendations as JSON.",
        "rules": [
            "Do not rate or discuss Google Search Console.",
            "Do not make claims about Google index status.",
            "Use the scraped page facts before making suggestions.",
            "Focus on meta title, meta description, missing alt text, content quality, headings, links, canonical, robots.txt, and sitemap.",
        ],
        "url": url,
        "score": score,
        "title": parser.title,
        "meta_description": parser.meta_description,
        "word_count": _word_count(parser.body_text),
        "scraped_page_facts": _ai_scrape_context(scrape_report),
        "checks": checks,
        "response_schema": {
            "summary": "one sentence",
            "priority_actions": ["3 to 5 short action items"],
        },
    }

    try:
        provider = get_provider()
        raw = provider.generate_json(json.dumps(prompt))
        data = json.loads(extract_json_string(raw))
        return {
            "summary": str(data.get("summary", fallback["summary"])).strip() or fallback["summary"],
            "priority_actions": [
                str(item).strip()
                for item in data.get("priority_actions", fallback["priority_actions"])
                if str(item).strip()
            ][:5],
            "source": "AI",
        }
    except Exception as exc:
        logger.warning("AI SEO summary failed; using fallback recommendations: %s", exc)
        return fallback


def _ai_scrape_context(scrape_report: dict) -> dict:
    return {
        "heading_total": scrape_report.get("heading_total", 0),
        "headings": scrape_report.get("headings", {}),
        "image_total": scrape_report.get("image_total", 0),
        "images_with_alt": scrape_report.get("images_with_alt", 0),
        "images_missing_alt": scrape_report.get("images_missing_alt", 0),
        "images": scrape_report.get("images", [])[:40],
        "link_total": scrape_report.get("link_total", 0),
        "internal_link_total": scrape_report.get("internal_link_total", 0),
        "external_link_total": scrape_report.get("external_link_total", 0),
        "links": scrape_report.get("links", [])[:60],
    }


def _fallback_recommendations(checks: list[dict]) -> dict:
    priority_actions = [
        check["recommendation"]
        for check in checks
        if check["status"] in {"fail", "warn"}
    ][:5]
    if not priority_actions:
        priority_actions = ["Keep titles, descriptions, image alt text, content, and sitemaps maintained as pages change."]
    return {
        "summary": "The score is based on on-page SEO and sitemap/robots checks only.",
        "priority_actions": priority_actions,
        "source": "Rules",
    }
