import json

from logger import logger
from prompts import build_simple_page_prompt
from utils import extract_json_string
from word_bank import find_banned_terms_in_text

MAX_GENERATION_ATTEMPTS = 3


def generate_simple_page(
    provider,
    page_title: str,
    page_type: str = "",
    brand: str = "",
    expectations: str = "",
    brand_context: str = "",
    change_request: str = "",
):
    prompt = build_simple_page_prompt(
        page_title=page_title,
        page_type=page_type,
        brand=brand,
        expectations=expectations,
        brand_context=brand_context,
        change_request=change_request,
    )

    last_error = None

    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                "- Your previous response used banned words or phrases.\n"
                "- Return a fresh simple page and avoid every banned term completely.\n"
            )

        raw = provider.generate_json(prompt + retry_instruction)

        try:
            json_text = extract_json_string(raw)
            data = json.loads(json_text)
            title = data.get("title", "").strip()
            content = data.get("content", "").strip()
            meta_descriptions = _normalize_meta_descriptions(data.get("meta_descriptions", []))
            meta_text = "\n".join(item.get("text", "") for item in meta_descriptions)
            banned_terms = find_banned_terms_in_text("\n".join([title, content, meta_text]))
            if banned_terms:
                logger.warning(
                    "Simple page used banned terms %s on attempt %d/%d",
                    ", ".join(banned_terms),
                    attempt,
                    MAX_GENERATION_ATTEMPTS,
                )
                continue
            h3_count = _count_h3_tags(content)
            if h3_count < 3:
                logger.warning(
                    "Simple page used only %d <h3> tags on attempt %d/%d",
                    h3_count,
                    attempt,
                    MAX_GENERATION_ATTEMPTS,
                )
                continue

            logger.info("Simple page generated successfully for '%s'", page_title)
            return {
                "title": title,
                "meta_descriptions": meta_descriptions,
                "content": content,
            }
        except Exception as exc:
            last_error = exc
            logger.exception("generate_simple_page failed on attempt %d. Raw response: %s", attempt, raw)

    if last_error is not None:
        raise ValueError("Could not parse JSON from model output.") from last_error

    raise ValueError("Generated simple page could not satisfy the rules after multiple attempts.")


def _normalize_meta_descriptions(raw_items) -> list[dict]:
    if not isinstance(raw_items, list):
        return []

    normalized = []
    for item in raw_items:
        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
        else:
            text = str(item).strip()
        if not text:
            continue
        normalized.append({"text": text, "character_count": len(text)})
        if len(normalized) >= 3:
            break
    return normalized


def _count_h3_tags(content: str) -> int:
    return (content or "").lower().count("<h3")
