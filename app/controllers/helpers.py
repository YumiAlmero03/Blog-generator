from flask import url_for

from config import MODEL, PROVIDER


def base_template_context():
    return {
        "provider": PROVIDER,
        "model": MODEL,
    }


def image_url(relative_path: str) -> str:
    cleaned = (relative_path or "").strip().replace("\\", "/")
    if not cleaned:
        return ""
    return url_for("web.uploaded_file", filename=cleaned)
