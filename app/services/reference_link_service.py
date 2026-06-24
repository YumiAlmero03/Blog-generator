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
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        cleaned_tag = (tag or "").lower()
        if cleaned_tag in {"script", "style", "noscript", "svg", "canvas", "iframe"}:
            self._skip_depth += 1
        if cleaned_tag == "title":
            self._title_depth += 1

    def handle_endtag(self, tag):
        cleaned_tag = (tag or "").lower()
        if cleaned_tag in {"script", "style", "noscript", "svg", "canvas", "iframe"} and self._skip_depth:
            self._skip_depth -= 1
        if cleaned_tag == "title" and self._title_depth:
            self._title_depth -= 1

    def handle_data(self, data):
        text = " ".join((data or "").split())
        if not text:
            return
        if self._title_depth:
            self.title_parts.append(text)
        if not self._skip_depth:
            self.text_parts.append(text)


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


def _fetch_url_text(url: str, timeout: int = 12) -> dict:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; NewsGenerator/1.0; +https://localhost)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(1_500_000)
    except HTTPError as exc:
        raise ValueError(f"HTTP {exc.code}") from exc
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
    text = _clean_text(" ".join(parser.text_parts))
    if title and text.startswith(title):
        text = text[len(title):].strip()
    if len(text) < 200:
        raise ValueError("Could not extract enough readable article text.")
    return {"title": title, "text": text}


def _charset_from_content_type(content_type: str) -> str:
    match = re.search(r"charset=([^;\s]+)", content_type or "", flags=re.IGNORECASE)
    return match.group(1).strip("\"'") if match else ""


def _clean_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    text = re.sub(r"(Advertisement|ADVERTISEMENT|Subscribe|Sign in)\s+", "", text)
    return text


def _is_http_url(url: str) -> bool:
    return bool(re.match(r"^https?://\S+$", url or "", flags=re.IGNORECASE))
