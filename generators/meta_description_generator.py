import json
from prompts import build_backlink_meta_description_prompt, build_meta_description_prompt
from utils import extract_json_string
from logger import logger
from word_bank import find_banned_terms_in_text

MAX_GENERATION_ATTEMPTS = 3
MIN_META_DESCRIPTION_CHARACTERS = 120
MAX_META_DESCRIPTION_CHARACTERS = 140

def _generate_meta_descriptions_from_prompt(provider, prompt: str):
    last_error = None

    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                "- Your previous response used banned words or phrases, or missed the 120-140 character range.\n"
                "- Return fresh meta descriptions that avoid every banned term completely.\n"
                "- Make every meta description between 120 and 140 characters.\n"
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
            invalid_lengths = [
                len(item.get("text", ""))
                for item in meta_descriptions
                if isinstance(item, dict)
                and not MIN_META_DESCRIPTION_CHARACTERS <= len(item.get("text", "")) <= MAX_META_DESCRIPTION_CHARACTERS
            ]
            if invalid_lengths:
                logger.warning(
                    "Generated meta descriptions missed %d-%d characters with lengths %s on attempt %d/%d",
                    MIN_META_DESCRIPTION_CHARACTERS,
                    MAX_META_DESCRIPTION_CHARACTERS,
                    ", ".join(str(length) for length in invalid_lengths),
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

    raise ValueError("Generated meta descriptions could not satisfy banned words and length rules after multiple attempts.")


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
    return _generate_meta_descriptions_from_prompt(provider, prompt)

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


def generate_backlink_meta_descriptions(
    provider,
    title: str,
    keyword: str = "",
    count: int = 3,
    brand: str = "",
    brand_context: str = "",
    backlink_website_name: str = "",
    backlink_blog_url: str = "",
    backlink_website_type: str = "",
    backlink_post_type: str = "html",
    backlink_title_max_characters: int | str = 0,
    backlink_min_words: int | str = 0,
    backlink_max_characters: int | str = 0,
    backlink_tier_level: str = "",
    backlink_blog_name: str = "",
    backlink_writer_name: str = "",
    backlink_content_guidelines: str = "",
):
    prompt = build_backlink_meta_description_prompt(
        title=title,
        keyword=keyword,
        count=count,
        brand=brand,
        brand_context=brand_context,
        backlink_website_name=backlink_website_name,
        backlink_blog_url=backlink_blog_url,
        backlink_website_type=backlink_website_type,
        backlink_post_type=backlink_post_type,
        backlink_title_max_characters=backlink_title_max_characters,
        backlink_min_words=backlink_min_words,
        backlink_max_characters=backlink_max_characters,
        backlink_tier_level=backlink_tier_level,
        backlink_blog_name=backlink_blog_name,
        backlink_writer_name=backlink_writer_name,
        backlink_content_guidelines=backlink_content_guidelines,
    )
    return _generate_meta_descriptions_from_prompt(provider, prompt)
