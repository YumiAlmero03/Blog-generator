import json
import random
import re

from generators.content_generator import count_html_words
from logger import logger
from prompts import build_page_prompt
from utils import extract_json_string
from word_bank import find_banned_terms_in_text

MIN_PAGE_WORDS = 900
MAX_PAGE_WORDS = 1200
MAX_GENERATION_ATTEMPTS = 3


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
    brand_context: str = "",
    change_request: str = "",
    min_words: int = MIN_PAGE_WORDS,
    max_words: int = MAX_PAGE_WORDS,
):
    min_word_count, max_word_count = _normalize_word_limits(min_words, max_words)
    prompt = build_page_prompt(
        keyword=keyword,
        supporting_keywords=supporting_keywords,
        page_type=page_type,
        expectations=expectations,
        brand=brand,
        brand_context=brand_context,
        change_request=change_request,
        min_words=min_word_count,
        max_words=max_word_count,
    )

    last_error = None
    last_word_count = 0

    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                f"\n\nIMPORTANT RETRY REQUIREMENT:\n"
                f"- Your previous page did not satisfy the word-count rules.\n"
                f"- Keep the same keyword intent and return valid JSON only.\n"
                f"- The page content must be between {min_word_count} and {max_word_count} words.\n"
                f"- Adjust the section depth until the page fits that range naturally.\n"
            )

        raw = provider.generate_json(prompt + retry_instruction)

        try:
            json_text = extract_json_string(raw)
            data = json.loads(json_text)
            title = data.get("title", "").strip()
            meta_description = data.get("meta_description", "").strip()
            content = data.get("content", "").strip()
            word_count = count_html_words(content)
            last_word_count = word_count
            banned_terms = find_banned_terms_in_text("\n".join([title, meta_description, content]))

            if banned_terms:
                logger.warning(
                    "Page output used banned terms %s for keyword '%s' on attempt %d/%d",
                    ", ".join(banned_terms),
                    keyword,
                    attempt,
                    MAX_GENERATION_ATTEMPTS,
                )
                continue

            if word_count < min_word_count:
                logger.warning(
                    "Page word count is %d (minimum: %d) for keyword '%s' on attempt %d/%d",
                    word_count,
                    min_word_count,
                    keyword,
                    attempt,
                    MAX_GENERATION_ATTEMPTS,
                )
                continue

            if word_count > max_word_count:
                logger.warning(
                    "Page word count is %d (maximum: %d) for keyword '%s' on attempt %d/%d",
                    word_count,
                    max_word_count,
                    keyword,
                    attempt,
                    MAX_GENERATION_ATTEMPTS,
                )
                continue

            content, injected_count = inject_image_placeholders(content)
            logger.info(
                "Page generated successfully for keyword '%s' with %d words and %d image placeholders on attempt %d/%d",
                keyword,
                word_count,
                injected_count,
                attempt,
                MAX_GENERATION_ATTEMPTS,
            )
            return {
                "title": title,
                "meta_description": meta_description,
                "content": content,
                "image_count": injected_count,
            }
        except Exception as exc:
            last_error = exc
            logger.exception("generate_page failed on attempt %d. Raw response: %s", attempt, raw)

    if last_error is not None:
        raise ValueError("Could not parse JSON from model output.") from last_error

    raise ValueError(
        f"Generated page could not satisfy the rules after {MAX_GENERATION_ATTEMPTS} attempts. "
        f"Last attempt was {last_word_count} words."
    )


def _normalize_word_limits(min_words: int, max_words: int) -> tuple[int, int]:
    try:
        cleaned_min = max(1, int(min_words or MIN_PAGE_WORDS))
    except (TypeError, ValueError):
        cleaned_min = MIN_PAGE_WORDS
    try:
        cleaned_max = max(1, int(max_words or MAX_PAGE_WORDS))
    except (TypeError, ValueError):
        cleaned_max = MAX_PAGE_WORDS
    if cleaned_max < cleaned_min:
        cleaned_max = cleaned_min
    return cleaned_min, cleaned_max
