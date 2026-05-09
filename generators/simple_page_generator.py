import json

from generators.content_generator import count_html_words
from logger import logger
from prompts import build_simple_page_prompt
from utils import extract_json_string
from word_bank import find_banned_terms_in_text

MIN_SIMPLE_PAGE_WORDS = 900
MAX_SIMPLE_PAGE_WORDS = 1200
MIN_META_DESCRIPTION_CHARACTERS = 120
MAX_META_DESCRIPTION_CHARACTERS = 140


def generate_simple_page(
    provider,
    page_title: str,
    page_type: str = "",
    brand: str = "",
    expectations: str = "",
    brand_context: str = "",
    change_request: str = "",
    min_words: int = MIN_SIMPLE_PAGE_WORDS,
    max_words: int = MAX_SIMPLE_PAGE_WORDS,
    progress_callback=None,
):
    min_word_count, max_word_count = _normalize_word_limits(min_words, max_words)
    prompt = build_simple_page_prompt(
        page_title=page_title,
        page_type=page_type,
        brand=brand,
        expectations=expectations,
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
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                "- Your previous response used banned words, missed required <h3> tags, missed the word-count range, or missed the meta description character range.\n"
                f"- The page content must be at least {min_word_count} words. Treat {max_word_count} words as a soft guide, but prioritize staying over the minimum.\n"
                f"- Every meta description must be between {MIN_META_DESCRIPTION_CHARACTERS} and {MAX_META_DESCRIPTION_CHARACTERS} characters.\n"
                "- Include at least 3 <h3> subheadings.\n"
                "- Return a fresh simple page and avoid every banned term completely.\n"
            )

        full_prompt = prompt + retry_instruction
        _publish_progress(progress_callback, full_prompt, kind="prompt")
        raw = provider.generate_json(full_prompt)

        try:
            json_text = extract_json_string(raw)
            data = json.loads(json_text)
            title = data.get("title", "").strip()
            content = data.get("content", "").strip()
            word_count = count_html_words(content)
            last_word_count = word_count
            meta_descriptions = _normalize_meta_descriptions(data.get("meta_descriptions", []))
            meta_text = "\n".join(item.get("text", "") for item in meta_descriptions)
            banned_terms = find_banned_terms_in_text("\n".join([title, content, meta_text]))
            if banned_terms:
                _publish_progress(
                    progress_callback,
                    f"Simple page attempt {attempt}: banned terms found ({', '.join(banned_terms)}). Retrying...",
                )
                logger.warning(
                    "Simple page used banned terms %s on attempt %d",
                    ", ".join(banned_terms),
                    attempt,
                )
                continue
            invalid_meta_lengths = [
                len(item.get("text", ""))
                for item in meta_descriptions
                if not MIN_META_DESCRIPTION_CHARACTERS <= len(item.get("text", "")) <= MAX_META_DESCRIPTION_CHARACTERS
            ]
            if invalid_meta_lengths:
                _publish_progress(
                    progress_callback,
                    f"Simple page attempt {attempt}: meta descriptions missed 120-140 characters ({', '.join(str(length) for length in invalid_meta_lengths)} chars). Retrying...",
                )
                logger.warning(
                    "Simple page meta descriptions missed %d-%d characters with lengths %s on attempt %d",
                    MIN_META_DESCRIPTION_CHARACTERS,
                    MAX_META_DESCRIPTION_CHARACTERS,
                    ", ".join(str(length) for length in invalid_meta_lengths),
                    attempt,
                )
                continue
            h3_count = _count_h3_tags(content)
            if h3_count < 3:
                _publish_progress(
                    progress_callback,
                    f"Simple page attempt {attempt}: only {h3_count} <h3> tags, minimum is 3. Retrying...",
                )
                logger.warning(
                    "Simple page used only %d <h3> tags on attempt %d",
                    h3_count,
                    attempt,
                )
                continue

            if word_count < min_word_count:
                _publish_progress(
                    progress_callback,
                    f"Simple page attempt {attempt}: {word_count} words, minimum is {min_word_count}. Retrying...",
                )
                logger.warning(
                    "Simple page word count is %d (minimum: %d) on attempt %d",
                    word_count,
                    min_word_count,
                    attempt,
                )
                continue

            if not min_word_count and word_count > max_word_count:
                _publish_progress(
                    progress_callback,
                    f"Simple page attempt {attempt}: {word_count} words, maximum is {max_word_count}. Retrying...",
                )
                logger.warning(
                    "Simple page word count is %d (maximum: %d) on attempt %d",
                    word_count,
                    max_word_count,
                    attempt,
                )
                continue

            logger.info("Simple page generated successfully for '%s' with %d words", page_title, word_count)
            return {
                "title": title,
                "meta_descriptions": meta_descriptions,
                "content": content,
            }
        except Exception as exc:
            logger.exception("generate_simple_page failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

    raise ValueError(
        "Generated simple page could not satisfy the rules. "
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


def _normalize_word_limits(min_words: int, max_words: int) -> tuple[int, int]:
    try:
        cleaned_min = max(1, int(min_words or MIN_SIMPLE_PAGE_WORDS))
    except (TypeError, ValueError):
        cleaned_min = MIN_SIMPLE_PAGE_WORDS
    try:
        cleaned_max = max(1, int(max_words or MAX_SIMPLE_PAGE_WORDS))
    except (TypeError, ValueError):
        cleaned_max = MAX_SIMPLE_PAGE_WORDS
    if cleaned_max < cleaned_min:
        cleaned_max = cleaned_min
    return cleaned_min, cleaned_max
