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
            banned_terms = find_banned_terms_in_text("\n".join([title, content]))
            if banned_terms:
                logger.warning(
                    "Simple page used banned terms %s on attempt %d/%d",
                    ", ".join(banned_terms),
                    attempt,
                    MAX_GENERATION_ATTEMPTS,
                )
                continue

            logger.info("Simple page generated successfully for '%s'", page_title)
            return {
                "title": title,
                "content": content,
            }
        except Exception as exc:
            last_error = exc
            logger.exception("generate_simple_page failed on attempt %d. Raw response: %s", attempt, raw)

    if last_error is not None:
        raise ValueError("Could not parse JSON from model output.") from last_error

    raise ValueError("Generated simple page kept using banned words after multiple attempts.")
