import json
import re
from prompts import build_backlink_content_prompt, build_content_prompt
from utils import extract_json_string
from logger import logger
from word_bank import find_banned_terms_in_text

MIN_BLOG_WORDS = 800
MAX_GENERATION_ATTEMPTS = 3


def count_html_words(html_text: str) -> int:
    """Count words in HTML content by removing tags."""
    clean_text = re.sub(r'<[^>]+>', '', html_text)
    words = clean_text.split()
    return len(words)


def parse_generated_content(raw: str) -> tuple[str, int]:
    json_text = extract_json_string(raw)
    data = json.loads(json_text)
    content = data.get("content", "")
    word_count = count_html_words(content)
    return content, word_count


def _generate_content_from_prompt(provider, prompt: str):
    last_error = None
    last_word_count = 0

    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                f"\n\nIMPORTANT RETRY REQUIREMENT:\n"
                f"- Your previous response was too short.\n"
                f"- Return COMPLETE valid HTML content only inside JSON.\n"
                f"- The article must be at least {MIN_BLOG_WORDS} words.\n"
                f"- Expand each section with more detail, examples, and explanation.\n"
            )

        raw = provider.generate_json(prompt + retry_instruction)

        try:
            content, word_count = parse_generated_content(raw)
            last_word_count = word_count
            banned_terms = find_banned_terms_in_text(content)

            if banned_terms:
                logger.warning(
                    "Content used banned terms %s on attempt %d/%d",
                    ", ".join(banned_terms),
                    attempt,
                    MAX_GENERATION_ATTEMPTS,
                )
                continue

            if word_count < MIN_BLOG_WORDS:
                logger.warning(
                    "Content word count is %d (minimum: %d) on attempt %d/%d. Raw response length: %d chars",
                    word_count,
                    MIN_BLOG_WORDS,
                    attempt,
                    MAX_GENERATION_ATTEMPTS,
                    len(raw),
                )
                continue

            logger.info(
                "Content generated successfully with %d words on attempt %d/%d",
                word_count,
                attempt,
                MAX_GENERATION_ATTEMPTS,
            )
            return content
        except Exception as exc:
            last_error = exc
            logger.exception("generate_content failed on attempt %d. Raw response: %s", attempt, raw)

    if last_error is not None:
        raise ValueError("Could not parse JSON from model output.") from last_error

    raise ValueError(
        f"Generated article could not satisfy the rules after {MAX_GENERATION_ATTEMPTS} attempts. "
        f"Last attempt was {last_word_count} words."
    )


def generate_content(
    provider,
    title: str,
    keyword: str = "",
    supporting_keyword: str = "",
    tone: str = "natural",
    links: list = None,
    money_site_url: str = "",
    brand: str = "",
    brand_context: str = "",
):
    prompt = build_content_prompt(
        title=title,
        keyword=keyword,
        supporting_keyword=supporting_keyword,
        tone=tone,
        links=links,
        money_site_url=money_site_url,
        brand=brand,
        brand_context=brand_context,
    )
    return _generate_content_from_prompt(provider, prompt)


def generate_backlink_content(
    provider,
    title: str,
    keyword: str = "",
    supporting_keyword: str = "",
    tone: str = "natural",
    money_site_url: str = "",
    brand: str = "",
    brand_context: str = "",
    backlink_website_name: str = "",
    backlink_blog_url: str = "",
    backlink_website_type: str = "",
    backlink_max_characters: int | str = 0,
    backlink_tier_level: str = "",
    backlink_blog_name: str = "",
    backlink_writer_name: str = "",
):
    prompt = build_backlink_content_prompt(
        title=title,
        keyword=keyword,
        supporting_keyword=supporting_keyword,
        tone=tone,
        money_site_url=money_site_url,
        brand=brand,
        brand_context=brand_context,
        backlink_website_name=backlink_website_name,
        backlink_blog_url=backlink_blog_url,
        backlink_website_type=backlink_website_type,
        backlink_max_characters=backlink_max_characters,
        backlink_tier_level=backlink_tier_level,
        backlink_blog_name=backlink_blog_name,
        backlink_writer_name=backlink_writer_name,
    )
    return _generate_content_from_prompt(provider, prompt)
