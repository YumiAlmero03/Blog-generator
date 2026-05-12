import json
import random
import re

from logger import logger
from prompts import build_page_prompt
from utils import extract_json_string
from word_bank import find_banned_terms_in_text

MIN_PAGE_WORDS = 1000
MAX_PAGE_WORDS = 19000
MIN_META_DESCRIPTION_CHARACTERS = 120
MAX_META_DESCRIPTION_CHARACTERS = 140


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

    processed = re.sub(r"<p>\s*\[IMAGE:\s*(.*?)\s*\]\s*</p>", replace, content, flags=re.IGNORECASE)
    processed = re.sub(r"\[IMAGE:\s*(.*?)\s*\]", replace, processed, flags=re.IGNORECASE)
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
    progress_callback=None,
):
    from app.services.content_format_service import count_markdown_words, markdown_to_html

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

    last_word_count = 0

    attempt = 0
    while True:
        attempt += 1
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                f"\n\nIMPORTANT RETRY REQUIREMENT:\n"
                f"- Your previous page did not satisfy the word-count or meta description rules.\n"
                f"- Keep the same keyword intent and return valid JSON only.\n"
                f"- The page content must be more than {min_word_count} words. Treat {max_word_count} words as a soft guide, but prioritize staying over the minimum.\n"
                f"- Do not finish at exactly {min_word_count} words; expand until the page exceeds that minimum.\n"
                f"- The meta_description must be between {MIN_META_DESCRIPTION_CHARACTERS} and {MAX_META_DESCRIPTION_CHARACTERS} characters.\n"
                f"- Adjust the section depth until the page is complete and over the minimum naturally.\n"
            )

        full_prompt = prompt + retry_instruction
        _publish_progress(progress_callback, full_prompt, kind="prompt")
        raw = provider.generate_json(full_prompt)

        try:
            json_text = extract_json_string(raw)
            data = json.loads(json_text)
            title = data.get("title", "").strip()
            meta_description = data.get("meta_description", "").strip()
            markdown_content = data.get("content", "").strip()
            word_count = count_markdown_words(markdown_content)
            last_word_count = word_count
            banned_terms = find_banned_terms_in_text("\n".join([title, meta_description, markdown_content]))

            if banned_terms:
                _publish_progress(
                    progress_callback,
                    f"Page attempt {attempt}: banned terms found ({', '.join(banned_terms)}). Retrying...",
                )
                logger.warning(
                    "Page output used banned terms %s for keyword '%s' on attempt %d",
                    ", ".join(banned_terms),
                    keyword,
                    attempt,
                )
                continue

            meta_description_length = len(meta_description)
            if not MIN_META_DESCRIPTION_CHARACTERS <= meta_description_length <= MAX_META_DESCRIPTION_CHARACTERS:
                _publish_progress(
                    progress_callback,
                    f"Page attempt {attempt}: meta description is {meta_description_length} characters, target is 120-140. Retrying...",
                )
                logger.warning(
                    "Page meta description is %d characters (target: %d-%d) for keyword '%s' on attempt %d",
                    meta_description_length,
                    MIN_META_DESCRIPTION_CHARACTERS,
                    MAX_META_DESCRIPTION_CHARACTERS,
                    keyword,
                    attempt,
                )
                continue

            if word_count <= min_word_count:
                _publish_progress(
                    progress_callback,
                    f"Page attempt {attempt}: {word_count} words, content must be more than {min_word_count}. Retrying...",
                )
                logger.warning(
                    "Page word count is %d (must be more than: %d) for keyword '%s' on attempt %d",
                    word_count,
                    min_word_count,
                    keyword,
                    attempt,
                )
                continue

            if not min_word_count and word_count > max_word_count:
                _publish_progress(
                    progress_callback,
                    f"Page attempt {attempt}: {word_count} words, maximum is {max_word_count}. Retrying...",
                )
                logger.warning(
                    "Page word count is %d (maximum: %d) for keyword '%s' on attempt %d",
                    word_count,
                    max_word_count,
                    keyword,
                    attempt,
                )
                continue

            content = markdown_to_html(markdown_content)
            content, injected_count = inject_image_placeholders(content)
            logger.info(
                "Page generated successfully for keyword '%s' with %d words and %d image placeholders on attempt %d",
                keyword,
                word_count,
                injected_count,
                attempt,
            )
            return {
                "title": title,
                "meta_description": meta_description,
                "content": content,
                "image_count": injected_count,
            }
        except Exception as exc:
            logger.exception("generate_page failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

    raise ValueError(
        "Generated page could not satisfy the rules. "
        f"Last attempt was {last_word_count} words."
    )


def _publish_progress(progress_callback, message: str, kind: str = "status") -> None:
    if not progress_callback:
        return
    try:
        progress_callback(message, kind=kind)
    except TypeError:
        progress_callback(message)
    except Exception:
        logger.exception("generation progress callback failed")


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
