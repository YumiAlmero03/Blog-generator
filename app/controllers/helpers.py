from flask import url_for

from app.services.content_format_service import html_to_gutenberg, html_to_markdown
from config import get_current_model, get_current_provider


def base_template_context():
    return {
        "provider": get_current_provider(),
        "model": get_current_model(),
        "html_to_gutenberg": html_to_gutenberg,
        "html_to_markdown": html_to_markdown,
    }


def image_url(relative_path: str) -> str:
    cleaned = (relative_path or "").strip().replace("\\", "/")
    if not cleaned:
        return ""
    return url_for("web.uploaded_file", filename=cleaned)


def scoped_change_request(change_request: str, scope: str) -> str:
    cleaned = (change_request or "").strip()
    cleaned_scope = (scope or "full").strip().lower()
    scope_labels = {
        "intro": "Regenerate only the introduction while keeping the rest of the article structure and intent consistent.",
        "meta": "Regenerate the meta description options and keep the article aligned with the selected title.",
        "tags": "Refresh the tag angle and make the article naturally support better tags.",
        "conclusion": "Regenerate only the ending section while keeping the article body consistent.",
        "section": "Regenerate the weakest body section while keeping the title, intro, and ending consistent.",
    }
    prefix = scope_labels.get(cleaned_scope, "")
    if not prefix:
        return cleaned
    return f"{prefix}\n{cleaned}".strip()
