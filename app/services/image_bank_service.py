import html
import io
import json
import re
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import quote_plus, unquote, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from database import save_image_bank_item
from logger import logger

from app.controllers.helpers import image_url
from app.services.image_service import IMAGE_BANK_DIR, format_file_size, save_optimized_image
from app.services.seo_checker_service import _validate_public_http_url


GOOGLE_IMAGE_SEARCH_URL = "https://www.google.com/search?tbm=isch&safe=active&q={query}"
IMAGE_SEARCH_TIMEOUT = 10
IMAGE_DOWNLOAD_TIMEOUT = 14
MAX_IMAGE_DOWNLOAD_BYTES = 8_000_000


def parse_bulk_image_queries(value: str) -> list[str]:
    queries = []
    seen = set()
    for line in str(value or "").splitlines():
        for part in line.split(","):
            cleaned = " ".join(part.strip().split())
            key = cleaned.casefold()
            if cleaned and key not in seen:
                seen.add(key)
                queries.append(cleaned)
    return queries[:50]


def search_google_images_for_queries(queries: list[str], per_query: int = 5) -> list[dict]:
    return [
        {
            "query": query,
            "google_url": GOOGLE_IMAGE_SEARCH_URL.format(query=quote_plus(query)),
            "results": search_google_images(query, limit=per_query),
        }
        for query in queries
    ]


def search_google_images(query: str, limit: int = 5) -> list[dict]:
    cleaned_query = " ".join(str(query or "").split())
    if not cleaned_query:
        return []
    request = Request(
        GOOGLE_IMAGE_SEARCH_URL.format(query=quote_plus(cleaned_query)),
        headers={
            "User-Agent": "Mozilla/5.0 AutoBlogGeneratorImageBank/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=IMAGE_SEARCH_TIMEOUT) as response:
        text = response.read(1_500_000).decode("utf-8", errors="replace")
    urls = _extract_google_image_urls(text)
    results = []
    seen = set()
    for image_src in urls:
        key = image_src.casefold()
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "title": cleaned_query,
                "image_url": image_src,
                "thumbnail_url": image_src,
                "source": urlparse(image_src).netloc,
            }
        )
        if len(results) >= limit:
            break
    return results


def save_remote_image_to_bank(image_src: str, query: str = "", title: str = "") -> dict:
    cleaned_url = str(image_src or "").strip()
    if not cleaned_url:
        raise ValueError("Choose an image URL to save.")
    _validate_public_http_url(cleaned_url)
    request = Request(
        cleaned_url,
        headers={
            "User-Agent": "Mozilla/5.0 AutoBlogGeneratorImageBank/1.0",
            "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*,*/*",
        },
    )
    with urlopen(request, timeout=IMAGE_DOWNLOAD_TIMEOUT) as response:
        content_type = response.headers.get("content-type", "")
        raw = response.read(MAX_IMAGE_DOWNLOAD_BYTES + 1)
    if len(raw) > MAX_IMAGE_DOWNLOAD_BYTES:
        raise ValueError("That image is too large. Please choose an image under 8 MB.")
    if "image" not in content_type.lower() and not _looks_like_image_url(cleaned_url):
        raise ValueError("The selected URL did not return an image.")

    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(raw)) as image:
            working = ImageOps.exif_transpose(image).convert("RGBA")
            safe_name = _slug(title or query or "image")
            output_name = f"{safe_name}_{uuid4().hex[:10]}.webp"
            output_path = IMAGE_BANK_DIR / output_name
            save_optimized_image(working, output_path, "webp", quality=90, optimize=True)
            width, height = working.size
    except ImportError as exc:
        raise ValueError("Image Bank needs Pillow. Install it with: pip install pillow") from exc
    except Exception as exc:
        logger.exception("image bank could not save remote image: %s", cleaned_url)
        raise ValueError("The selected URL could not be opened as an image.") from exc

    file_path = f"image_bank/{output_name}"
    return save_image_bank_item(
        query=query,
        title=title or query,
        source_url=cleaned_url,
        file_path=file_path,
        file_name=output_name,
        file_size=output_path.stat().st_size,
        width=width,
        height=height,
    )


def image_bank_view_item(item: dict) -> dict:
    file_size = int(item.get("file_size", 0) or 0)
    return {
        **item,
        "image_url": image_url(item.get("file_path", "")),
        "download_name": item.get("file_name", "") or Path(item.get("file_path", "")).name,
        "file_size_label": format_file_size(file_size) if file_size else "",
    }


def _extract_google_image_urls(text: str) -> list[str]:
    decoded = html.unescape(text or "")
    candidates = []
    candidates.extend(_extract_rg_meta_urls(decoded))
    candidates.extend(_extract_ou_json_urls(decoded))
    candidates.extend(unquote(match) for match in re.findall(r"[?&]imgurl=([^&\"'<>]+)", decoded))
    candidates.extend(match.replace("\\u003d", "=").replace("\\u0026", "&") for match in re.findall(r"https?://[^\"'<>\\\s]+", decoded))
    candidates.extend(_extract_img_tag_sources(decoded))
    direct = []
    fallback = []
    seen = set()
    for candidate in candidates:
        cleaned = _clean_image_candidate(candidate)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        if _looks_like_direct_image_url(cleaned):
            direct.append(cleaned)
        elif "gstatic.com" in urlparse(cleaned).netloc:
            fallback.append(cleaned)
    return direct + fallback


def _extract_rg_meta_urls(text: str) -> list[str]:
    urls = []
    for match in re.findall(r'<div[^>]+class=["\'][^"\']*\brg_meta\b[^"\']*["\'][^>]*>(.*?)</div>', text or "", flags=re.IGNORECASE | re.DOTALL):
        cleaned = html.unescape(match).strip()
        if not cleaned:
            continue
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            continue
        image_url = data.get("ou", "")
        if image_url:
            urls.append(str(image_url))
    return urls


def _extract_ou_json_urls(text: str) -> list[str]:
    urls = []
    for match in re.findall(r'"ou"\s*:\s*"((?:\\.|[^"\\])*)"', text or ""):
        try:
            urls.append(json.loads(f'"{match}"'))
        except json.JSONDecodeError:
            urls.append(match)
    return urls


class _ImageSourceParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sources = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "img":
            return
        attrs_dict = {name.lower(): value or "" for name, value in attrs}
        for key in ("src", "data-src", "data-iurl", "data-ou"):
            value = attrs_dict.get(key, "").strip()
            if value:
                self.sources.append(value)


def _extract_img_tag_sources(text: str) -> list[str]:
    parser = _ImageSourceParser()
    try:
        parser.feed(text or "")
    except Exception:
        return []
    return parser.sources


def _clean_image_candidate(value: str) -> str:
    cleaned = html.unescape(str(value or "")).replace("\\/", "/").strip()
    cleaned = cleaned.split("&amp;")[0].strip()
    if not cleaned.startswith(("http://", "https://")):
        return ""
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if any(blocked in parsed.netloc for blocked in ("google.com", "googleusercontent.com")) and "gstatic.com" not in parsed.netloc:
        return ""
    return cleaned


def _looks_like_direct_image_url(value: str) -> bool:
    path = urlparse(value or "").path.lower()
    return path.endswith((".jpg", ".jpeg", ".png", ".webp", ".avif"))


def _looks_like_image_url(value: str) -> bool:
    return _looks_like_direct_image_url(value) or "gstatic.com" in urlparse(value or "").netloc


def _slug(value: str) -> str:
    slug = "-".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))
    return slug[:80] or "image"
