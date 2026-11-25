import re
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.services.sportsbook_odds_extractor import extract_sportsbook_odds_from_page
from logger import logger


MAX_LINKS = 6
MAX_TEXT_PER_LINK = 5000
MAX_ODDS_TEXT_PER_LINK = 16000
MAX_TOTAL_TEXT = 18000


class _ReadableTextParser(HTMLParser):
    def __init__(self, content_tags: set[str] | None = None):
        super().__init__()
        self._content_tags = content_tags or set()
        self._skip_depth = 0
        self._title_depth = 0
        self._article_depth = 0
        self._main_depth = 0
        self.has_main = False
        self._content_depth = 0
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.article_parts: list[str] = []
        self.main_parts: list[str] = []
        self.filtered_parts: list[str] = []
        self.filtered_article_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        cleaned_tag = (tag or "").lower()
        if cleaned_tag in {"script", "style", "noscript", "svg", "canvas", "iframe"}:
            self._skip_depth += 1
        if cleaned_tag == "title":
            self._title_depth += 1
        if cleaned_tag == "article":
            self._article_depth += 1
        if cleaned_tag == "main":
            self._main_depth += 1
            self.has_main = True
        if cleaned_tag in self._content_tags:
            self._content_depth += 1

    def handle_endtag(self, tag):
        cleaned_tag = (tag or "").lower()
        if cleaned_tag in {"script", "style", "noscript", "svg", "canvas", "iframe"} and self._skip_depth:
            self._skip_depth -= 1
        if cleaned_tag == "title" and self._title_depth:
            self._title_depth -= 1
        if cleaned_tag == "article" and self._article_depth:
            self._article_depth -= 1
        if cleaned_tag == "main" and self._main_depth:
            self._main_depth -= 1
        if cleaned_tag in self._content_tags and self._content_depth:
            self._content_depth -= 1

    def handle_data(self, data):
        text = " ".join((data or "").split())
        if not text:
            return
        if self._title_depth:
            self.title_parts.append(text)
        if not self._skip_depth:
            self.text_parts.append(text)
            if self._article_depth:
                self.article_parts.append(text)
            if self._main_depth:
                self.main_parts.append(text)
            if self._content_depth:
                self.filtered_parts.append(text)
                if self._article_depth:
                    self.filtered_article_parts.append(text)


def fetch_reference_context(
    links: list[dict],
    timeout: int = 12,
    use_browser: bool = False,
    browser_wait_seconds: float = 2,
    content_tags: set[str] | tuple[str, ...] | list[str] | None = None,
    merge_context: bool = False,
) -> tuple[str, list[dict]]:
    fetched = []
    context_parts = []
    total_length = 0

    for index, link in enumerate((links or [])[:MAX_LINKS], start=1):
        url = (link.get("url") or "").strip()
        label = (link.get("text") or "").strip()
        if not _is_http_url(url):
            fetched.append({**link, "status": "skipped", "error": "URL must start with http or https."})
            continue

        fetch_method = "http"
        try:
            article = _fetch_url_text_with_options(url, timeout=timeout, content_tags=content_tags)
        except Exception as http_exc:
            if not use_browser:
                logger.warning("Could not fetch reference link %s: %s", url, http_exc)
                fetched.append({**link, "status": "error", "error": str(http_exc)})
                continue
            try:
                logger.warning("HTTP fetch failed for reference link %s, trying browser reader: %s", url, http_exc)
                article = _fetch_url_rendered_text_with_options(
                    url,
                    wait_seconds=browser_wait_seconds,
                    timeout=max(timeout, 30),
                    content_tags=content_tags,
                )
                fetch_method = "browser-fallback"
            except Exception as browser_exc:
                logger.warning("Could not fetch reference link %s: %s", url, browser_exc)
                fetched.append({**link, "status": "error", "error": str(browser_exc), "http_error": str(http_exc)})
                continue

        remaining = MAX_TOTAL_TEXT - total_length
        if remaining <= 0:
            break
        per_link_limit = MAX_ODDS_TEXT_PER_LINK if article.get("structured_odds") else MAX_TEXT_PER_LINK
        excerpt = article["text"][: min(per_link_limit, remaining)]
        total_length += len(excerpt)
        source_label = label or article["title"] or url
        context_parts.append({"index": index, "source_label": source_label, "url": url, "excerpt": excerpt})
        fetched_item = {
            **link,
            "status": "fetched",
            "title": article["title"],
            "source_label": source_label,
            "character_count": len(article["text"]),
            "excerpt": excerpt,
            "fetch_method": fetch_method,
        }
        if article.get("structured_odds"):
            fetched_item["structured_odds"] = True
        fetched.append(fetched_item)
    if merge_context:
        return merge_reference_context_parts(context_parts), fetched
    return "\n\n---\n\n".join(_reference_context_part_text(item) for item in context_parts).strip(), fetched


def merge_reference_context_parts(parts: list[dict]) -> str:
    cleaned_parts = [item for item in parts if item.get("excerpt")]
    if not cleaned_parts:
        return ""
    sources = []
    excerpts = []
    for item in cleaned_parts:
        index = item.get("index") or len(sources) + 1
        source_label = item.get("source_label") or item.get("url") or f"Reference {index}"
        url = item.get("url") or ""
        sources.append(f"{index}. {source_label} - {url}".strip())
        excerpts.append(str(item.get("excerpt") or "").strip())
    return (
        "Combined reference source. Use all fetched links together as one mixed source of facts.\n"
        "Sources:\n"
        + "\n".join(sources)
        + "\n\nMerged extracted content:\n"
        + "\n\n".join(excerpts)
    ).strip()


def _reference_context_part_text(item: dict) -> str:
    return (
        f"Reference {item.get('index')}: {item.get('source_label')}\n"
        f"URL: {item.get('url')}\n"
        f"Extracted content:\n{item.get('excerpt')}"
    )


def fetch_url_text(url: str, timeout: int = 12) -> dict:
    return _fetch_url_text(url, timeout=timeout)


def fetch_url_html(url: str, timeout: int = 12) -> dict:
    return _fetch_url_html(url, timeout=timeout)


def fetch_url_rendered_html(url: str, wait_seconds: float = 0, timeout: int = 60) -> dict:
    return _fetch_url_rendered_html(url, wait_seconds=wait_seconds, timeout=timeout)


def fetch_url_rendered_text(url: str, wait_seconds: float = 2, timeout: int = 60) -> dict:
    return _fetch_url_rendered_text(url, wait_seconds=wait_seconds, timeout=timeout)


def _fetch_url_rendered_html(url: str, wait_seconds: float = 0, timeout: int = 60) -> dict:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ValueError(
            "Browser fetch needs Playwright. Install it with `pip install playwright` "
            "and `python -m playwright install chromium`."
        ) from exc

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(
                    viewport={"width": 1440, "height": 900},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
                )
                response = page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10_000)
                except PlaywrightError:
                    pass
                if wait_seconds:
                    page.wait_for_timeout(wait_seconds * 1000)
                structured_article = extract_sportsbook_odds_from_page(page, url=page.url)
                html = page.content()
                content_type = ""
                if response:
                    content_type = response.headers.get("content-type", "")
                result = {
                    "content_type": content_type,
                    "html": html,
                    "byte_count": len(html.encode("utf-8")),
                    "character_count": len(html),
                    "final_url": page.url,
                    "rendered": True,
                    "status_code": response.status if response else 0,
                    "cf_mitigated": response.headers.get("cf-mitigated", "") if response else "",
                }
                if structured_article:
                    result["structured_article"] = structured_article
                return result
            finally:
                browser.close()
    except PlaywrightError as exc:
        raise ValueError(f"Browser fetch failed: {exc}") from exc


def _fetch_url_html(url: str, timeout: int = 12) -> dict:
    request = _build_request(url)
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(1_500_000)
            final_url = response.geturl()
    except HTTPError as exc:
        raise ValueError(_http_error_message(exc)) from exc
    except URLError as exc:
        raise ValueError(str(exc.reason or exc)) from exc

    charset = _charset_from_content_type(content_type) or "utf-8"
    decoded = raw.decode(charset, errors="replace")
    return {
        "content_type": content_type,
        "html": decoded,
        "byte_count": len(raw),
        "character_count": len(decoded),
        "final_url": final_url,
    }


def _fetch_url_text(url: str, timeout: int = 12, content_tags: set[str] | tuple[str, ...] | list[str] | None = None) -> dict:
    request = _build_request(url)
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(1_500_000)
    except HTTPError as exc:
        raise ValueError(_http_error_message(exc)) from exc
    except URLError as exc:
        raise ValueError(str(exc.reason or exc)) from exc

    charset = _charset_from_content_type(content_type) or "utf-8"
    decoded = raw.decode(charset, errors="replace")
    if "html" not in content_type.lower() and "<html" not in decoded[:1000].lower():
        text = _clean_text(decoded)
        return {"title": "", "text": text}

    if "main" in {str(tag).strip().lower() for tag in (content_tags or [])} and _has_pending_streamed_content(decoded):
        raise ValueError("The source page streams its main content with JavaScript and needs the browser reader.")
    return _extract_readable_text_from_html(decoded, content_tags=content_tags)


def _fetch_url_text_with_options(url: str, timeout: int, content_tags: set[str] | tuple[str, ...] | list[str] | None = None) -> dict:
    if content_tags:
        return _fetch_url_text(url, timeout=timeout, content_tags=content_tags)
    return _fetch_url_text(url, timeout=timeout)


def _fetch_url_rendered_text(
    url: str,
    wait_seconds: float = 2,
    timeout: int = 60,
    content_tags: set[str] | tuple[str, ...] | list[str] | None = None,
) -> dict:
    rendered = _fetch_url_rendered_html(url, wait_seconds=wait_seconds, timeout=timeout)
    if rendered.get("status_code", 0) >= 400:
        raise ValueError(_http_status_error_message(
            rendered["status_code"],
            {"cf-mitigated": rendered.get("cf_mitigated", "")},
        ))
    if rendered.get("structured_article"):
        article = dict(rendered["structured_article"])
        article["final_url"] = rendered.get("final_url", url)
        article["rendered"] = True
        return article
    article = _extract_readable_text_from_html(rendered.get("html", ""), content_tags=content_tags)
    article["final_url"] = rendered.get("final_url", url)
    article["rendered"] = True
    return article


def _fetch_url_rendered_text_with_options(
    url: str,
    wait_seconds: float,
    timeout: int,
    content_tags: set[str] | tuple[str, ...] | list[str] | None = None,
) -> dict:
    if content_tags:
        return _fetch_url_rendered_text(url, wait_seconds=wait_seconds, timeout=timeout, content_tags=content_tags)
    return _fetch_url_rendered_text(url, wait_seconds=wait_seconds, timeout=timeout)


def _extract_readable_text_from_html(html: str, content_tags: set[str] | tuple[str, ...] | list[str] | None = None) -> dict:
    cleaned_content_tags = {str(tag).lower() for tag in (content_tags or []) if str(tag).strip()}
    parser = _ReadableTextParser(content_tags=cleaned_content_tags)
    parser.feed(html or "")
    title = _clean_text(" ".join(parser.title_parts))
    if _is_challenge_page(html or "", title, " ".join(parser.text_parts)):
        raise ValueError(
            "The source page returned an automated-access verification challenge instead of source content. "
            "Use a source URL that can be read without a browser challenge."
        )
    if "main" in cleaned_content_tags and parser.has_main:
        text = _clean_text(" ".join(parser.main_parts))
        if len(text) < 200:
            raise ValueError(
                "The source page's main content has no readable data yet. "
                "It may still be loading or display no data available."
            )
    elif cleaned_content_tags:
        article_text = _clean_text(" ".join(parser.filtered_article_parts))
        text = article_text if len(article_text) >= 200 else _clean_text(" ".join(parser.filtered_parts))
    else:
        article_text = _clean_text(" ".join(parser.article_parts))
        text = article_text if len(article_text) >= 200 else _clean_text(" ".join(parser.text_parts))
    if title and text.startswith(title):
        text = text[len(title):].strip()
    if len(text) < 200:
        raise ValueError("Could not extract enough readable article text.")
    return {"title": title, "text": text}


def _build_request(url: str) -> Request:
    return Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; NewsGenerator/1.0; +https://localhost)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
        },
    )


def _http_error_message(exc: HTTPError) -> str:
    return _http_status_error_message(exc.code, exc.headers)


def _http_status_error_message(status: int, headers=None) -> str:
    if status == 403:
        if ((headers or {}).get("cf-mitigated") or "").lower() == "challenge":
            return (
                "The source page is protected by Cloudflare and blocked automated fetching "
                "(HTTP 403). Use a source URL that can be fetched without a browser challenge."
            )
        return "The source page blocked automated fetching (HTTP 403)."
    return f"HTTP {status}"


def _is_challenge_page(html: str, title: str, text: str) -> bool:
    challenge_title = re.match(
        r"^(just a moment|attention required|access denied|security verification|security check|"
        r"verify (?:that )?you are human|checking your browser)(?:\b|[.!])",
        title.lower(),
    )
    if not challenge_title:
        return False
    challenge_marker = re.search(
        r"/cdn-cgi/challenge-platform/|cf_chl_opt|__cf_chl|challenges\.cloudflare\.com/|"
        r"id\s*=\s*[\"'](?:challenge-form|challenge-running|cf-challenge-running|human-verification)[\"']",
        html,
        flags=re.IGNORECASE,
    )
    verification_text = re.search(
        r"verify (?:that )?you are human|checking your browser|performing security verification|"
        r"enable javascript and cookies to continue|checking if the site connection is secure",
        text,
        flags=re.IGNORECASE,
    )
    return bool(challenge_marker or verification_text)


def _has_pending_streamed_content(html: str) -> bool:
    pending_placeholder = re.search(r"<template\b[^>]*\bid\s*=\s*[\"']B:[^\"']+[\"']", html, flags=re.IGNORECASE)
    hidden_fragment = re.search(
        r"<div\b(?=[^>]*\bhidden(?:\s|=|>))[^>]*\bid\s*=\s*[\"']S:[^\"']+[\"']",
        html,
        flags=re.IGNORECASE,
    )
    return bool(pending_placeholder and hidden_fragment)


def _charset_from_content_type(content_type: str) -> str:
    match = re.search(r"charset=([^;\s]+)", content_type or "", flags=re.IGNORECASE)
    return match.group(1).strip("\"'") if match else ""


def _clean_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    text = re.sub(r"(Advertisement|ADVERTISEMENT|Subscribe|Sign in)\s+", "", text)
    return text


def _is_http_url(url: str) -> bool:
    return bool(re.match(r"^https?://\S+$", url or "", flags=re.IGNORECASE))
