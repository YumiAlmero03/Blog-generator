import json
from prompts import build_backlink_title_prompt, build_title_prompt
from utils import extract_json_string
from logger import logger
from word_bank import find_banned_terms_in_text

MAX_GENERATION_ATTEMPTS = 3

def _generate_titles_from_prompt(provider, prompt: str):
    last_error = None

    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                "- Your previous response used banned words or phrases.\n"
                "- Return fresh titles that avoid every banned term completely.\n"
            )

        raw = provider.generate_json(prompt + retry_instruction)

        try:
            json_text = extract_json_string(raw)
            data = json.loads(json_text)
            titles = data.get("titles", [])
            combined_titles = "\n".join(title for title in titles if isinstance(title, str))
            banned_terms = find_banned_terms_in_text(combined_titles)
            if banned_terms:
                logger.warning(
                    "Generated titles used banned terms %s on attempt %d/%d",
                    ", ".join(banned_terms),
                    attempt,
                    MAX_GENERATION_ATTEMPTS,
                )
                continue
            return titles
        except Exception as exc:
            last_error = exc
            logger.exception("generate_titles failed on attempt %d. Raw response: %s", attempt, raw)

    if last_error is not None:
        raise ValueError("Could not parse JSON from model output.") from last_error

    raise ValueError("Generated titles kept using banned words after multiple attempts.")


def generate_titles(
    provider,
    keyword: str,
    supporting_keyword: str = "",
    tone: str = "natural",
    count: int = 10,
    brand: str = "",
    brand_context: str = "",
):
    prompt = build_title_prompt(
        keyword=keyword,
        supporting_keyword=supporting_keyword,
        tone=tone,
        count=count,
        brand=brand,
        brand_context=brand_context,
    )
    return _generate_titles_from_prompt(provider, prompt)


def generate_backlink_titles(
    provider,
    keyword: str,
    supporting_keyword: str = "",
    tone: str = "natural",
    count: int = 10,
    brand: str = "",
    brand_context: str = "",
    backlink_website_name: str = "",
    backlink_blog_url: str = "",
    backlink_tier_level: str = "",
    backlink_account_name: str = "",
):
    prompt = build_backlink_title_prompt(
        keyword=keyword,
        supporting_keyword=supporting_keyword,
        tone=tone,
        count=count,
        brand=brand,
        brand_context=brand_context,
        backlink_website_name=backlink_website_name,
        backlink_blog_url=backlink_blog_url,
        backlink_tier_level=backlink_tier_level,
        backlink_account_name=backlink_account_name,
    )
    return _generate_titles_from_prompt(provider, prompt)
