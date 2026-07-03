import re
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from logger import logger


MAX_LINKS = 6
MAX_TEXT_PER_LINK = 5000
MAX_TOTAL_TEXT = 18000


class _ReadableTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._title_depth = 0
        self._article_depth = 0
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.article_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        cleaned_tag = (tag or "").lower()
        if cleaned_tag in {"script", "style", "noscript", "svg", "canvas", "iframe"}:
            self._skip_depth += 1
        if cleaned_tag == "title":
            self._title_depth += 1
        if cleaned_tag == "article":
            self._article_depth += 1

    def handle_endtag(self, tag):
        cleaned_tag = (tag or "").lower()
        if cleaned_tag in {"script", "style", "noscript", "svg", "canvas", "iframe"} and self._skip_depth:
            self._skip_depth -= 1
        if cleaned_tag == "title" and self._title_depth:
            self._title_depth -= 1
        if cleaned_tag == "article" and self._article_depth:
            self._article_depth -= 1

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


def fetch_reference_context(links: list[dict], timeout: int = 12) -> tuple[str, list[dict]]:
    fetched = []
    context_parts = []
    total_length = 0

    for index, link in enumerate((links or [])[:MAX_LINKS], start=1):
        url = (link.get("url") or "").strip()
        label = (link.get("text") or "").strip()
        if not _is_http_url(url):
            fetched.append({**link, "status": "skipped", "error": "URL must start with http or https."})
            continue

        try:
            article = _fetch_url_text(url, timeout=timeout)
        except Exception as exc:
            logger.warning("Could not fetch reference link %s: %s", url, exc)
            fetched.append({**link, "status": "error", "error": str(exc)})
            continue

        remaining = MAX_TOTAL_TEXT - total_length
        if remaining <= 0:
            break
        excerpt = article["text"][: min(MAX_TEXT_PER_LINK, remaining)]
        total_length += len(excerpt)
        source_label = label or article["title"] or url
        context_parts.append(
            f"Reference {index}: {source_label}\nURL: {url}\nExtracted content:\n{excerpt}"
        )
        fetched.append({
            **link,
            "status": "fetched",
            "title": article["title"],
            "source_label": source_label,
            "character_count": len(article["text"]),
            "excerpt": excerpt,
        })

    return "\n\n---\n\n".join(context_parts).strip(), fetched


def fetch_url_text(url: str, timeout: int = 12) -> dict:
    return _fetch_url_text(url, timeout=timeout)


def fetch_url_html(url: str, timeout: int = 12) -> dict:
    return _fetch_url_html(url, timeout=timeout)


def fetch_url_rendered_html(url: str, wait_seconds: float = 0, timeout: int = 60) -> dict:
    return _fetch_url_rendered_html(url, wait_seconds=wait_seconds, timeout=timeout)


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
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                )
                response = page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10_000)
                except PlaywrightError:
                    pass
                if wait_seconds:
                    page.wait_for_timeout(wait_seconds * 1000)
                html = page.content()
                content_type = ""
                if response:
                    content_type = response.headers.get("content-type", "")
                return {
                    "content_type": content_type,
                    "html": html,
                    "byte_count": len(html.encode("utf-8")),
                    "character_count": len(html),
                    "final_url": page.url,
                    "rendered": True,
                }
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


def _fetch_url_text(url: str, timeout: int = 12) -> dict:
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

    parser = _ReadableTextParser()
    parser.feed(decoded)
    title = _clean_text(" ".join(parser.title_parts))
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
    if exc.code == 403:
        if (exc.headers.get("cf-mitigated") or "").lower() == "challenge":
            return (
                "The source page is protected by Cloudflare and blocked automated fetching "
                "(HTTP 403). Use a source URL that can be fetched without a browser challenge."
            )
        return "The source page blocked automated fetching (HTTP 403)."
    return f"HTTP {exc.code}"


def _charset_from_content_type(content_type: str) -> str:
    match = re.search(r"charset=([^;\s]+)", content_type or "", flags=re.IGNORECASE)
    return match.group(1).strip("\"'") if match else ""


def _clean_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    text = re.sub(r"(Advertisement|ADVERTISEMENT|Subscribe|Sign in)\s+", "", text)
    return text


def _is_http_url(url: str) -> bool:
    return bool(re.match(r"^https?://\S+$", url or "", flags=re.IGNORECASE))
