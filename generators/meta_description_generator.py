import json
from prompts import build_meta_description_prompt
from utils import extract_json_string
from logger import logger
from word_bank import find_banned_terms_in_text

MAX_GENERATION_ATTEMPTS = 3

def generate_meta_descriptions(
    provider,
    title: str,
    keyword: str = "",
    count: int = 3,
    brand: str = "",
    brand_context: str = "",
):
    prompt = build_meta_description_prompt(
        title=title,
        keyword=keyword,
        count=count,
        brand=brand,
        brand_context=brand_context,
    )

    last_error = None

    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                "- Your previous response used banned words or phrases.\n"
                "- Return fresh meta descriptions that avoid every banned term completely.\n"
            )

        raw = provider.generate_json(prompt + retry_instruction)

        try:
            json_text = extract_json_string(raw)
            data = json.loads(json_text)
            meta_descriptions = data.get("meta_descriptions", [])
            combined_text = "\n".join(
                item.get("text", "") for item in meta_descriptions if isinstance(item, dict)
            )
            banned_terms = find_banned_terms_in_text(combined_text)
            if banned_terms:
                logger.warning(
                    "Generated meta descriptions used banned terms %s on attempt %d/%d",
                    ", ".join(banned_terms),
                    attempt,
                    MAX_GENERATION_ATTEMPTS,
                )
                continue
            return meta_descriptions
        except Exception as exc:
            last_error = exc
            logger.exception("generate_meta_descriptions failed on attempt %d. Raw response: %s", attempt, raw)

    if last_error is not None:
        raise ValueError("Could not parse JSON from model output.") from last_error

    raise ValueError("Generated meta descriptions kept using banned words after multiple attempts.")

def generate_meta_description(
    provider,
    title: str,
    keyword: str = "",
    brand: str = "",
    brand_context: str = "",
):
    """Legacy function for single meta description"""
    descriptions = generate_meta_descriptions(
        provider,
        title,
        keyword,
        count=1,
        brand=brand,
        brand_context=brand_context,
    )
    return descriptions[0]["text"] if descriptions else ""
