from flask import url_for

from app.services.content_format_service import html_to_gutenberg, html_to_markdown
from config import MODEL, PROVIDER


def base_template_context():
    return {
        "provider": PROVIDER,
        "model": MODEL,
        "html_to_gutenberg": html_to_gutenberg,
        "html_to_markdown": html_to_markdown,
    }


def image_url(relative_path: str) -> str:
    cleaned = (relative_path or "").strip().replace("\\", "/")
    if not cleaned:
        return ""
    return url_for("web.uploaded_file", filename=cleaned)
