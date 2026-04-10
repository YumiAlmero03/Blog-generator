import json

from logger import logger
from prompts import build_simple_page_prompt
from utils import extract_json_string


def generate_simple_page(
    provider,
    page_title: str,
    page_type: str = "",
    brand: str = "",
    expectations: str = "",
    brand_context: str = "",
):
    prompt = build_simple_page_prompt(
        page_title=page_title,
        page_type=page_type,
        brand=brand,
        expectations=expectations,
        brand_context=brand_context,
    )
    raw = provider.generate_json(prompt)

    try:
        json_text = extract_json_string(raw)
        data = json.loads(json_text)
        title = data.get("title", "").strip()
        content = data.get("content", "").strip()

        logger.info("Simple page generated successfully for '%s'", page_title)
        return {
            "title": title,
            "content": content,
        }
    except Exception as exc:
        logger.exception("generate_simple_page failed. Raw response: %s", raw)
        raise ValueError("Could not parse JSON from model output.") from exc
