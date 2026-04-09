import json
import random
import re

from logger import logger
from prompts import build_page_prompt
from utils import extract_json_string


PLACEHOLDER_PALETTE = [
    ("#fde68a", "#92400e"),
    ("#bfdbfe", "#1d4ed8"),
    ("#fecdd3", "#be123c"),
    ("#c7f9cc", "#166534"),
    ("#ddd6fe", "#6d28d9"),
    ("#fed7aa", "#c2410c"),
]


def build_image_placeholder(description: str) -> str:
    background, text_color = random.choice(PLACEHOLDER_PALETTE)
    safe_description = (description or "Image placeholder").strip()
    return (
        "<div style=\"margin:24px 0;padding:32px 20px;border-radius:18px;"
        f"background:{background};color:{text_color};min-height:220px;"
        "display:flex;align-items:center;justify-content:center;text-align:center;"
        "font-weight:700;font-size:20px;\">"
        f"{safe_description}"
        "</div>"
    )


def inject_image_placeholders(content: str) -> tuple[str, int]:
    placeholder_count = 0

    def replace(match):
        nonlocal placeholder_count
        placeholder_count += 1
        return build_image_placeholder(match.group(1))

    processed = re.sub(r"\[IMAGE:\s*(.*?)\s*\]", replace, content, flags=re.IGNORECASE)
    return processed, placeholder_count


def generate_page(
    provider,
    keyword: str,
    supporting_keywords: str = "",
    page_type: str = "",
    expectations: str = "",
    brand: str = "",
):
    prompt = build_page_prompt(
        keyword=keyword,
        supporting_keywords=supporting_keywords,
        page_type=page_type,
        expectations=expectations,
        brand=brand,
    )
    raw = provider.generate_json(prompt)

    try:
        json_text = extract_json_string(raw)
        data = json.loads(json_text)
        title = data.get("title", "").strip()
        meta_description = data.get("meta_description", "").strip()
        content = data.get("content", "").strip()
        content, injected_count = inject_image_placeholders(content)

        logger.info(
            "Page generated successfully for keyword '%s' with %d image placeholders",
            keyword,
            injected_count,
        )
        return {
            "title": title,
            "meta_description": meta_description,
            "content": content,
            "image_count": injected_count,
        }
    except Exception as exc:
        logger.exception("generate_page failed. Raw response: %s", raw)
        raise ValueError("Could not parse JSON from model output.") from exc
