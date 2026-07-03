import json
import random
import re

from generation_retry_policy import (
    can_accept_close_enough,
    max_generation_attempts,
    publish_generation_draft,
    raise_if_generation_cancelled,
    wait_before_retry,
)
from logger import logger
from prompts import build_page_content_prompt, build_page_meta_description_prompt, build_page_prompt, build_page_title_prompt
from utils import extract_json_string
from word_bank import find_banned_terms_in_text
from content_repetition import repeated_content_issue

MIN_PAGE_WORDS = 1000
MAX_PAGE_WORDS = 19000
MIN_PAGE_TITLE_CHARACTERS = 50
MAX_PAGE_TITLE_CHARACTERS = 60
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
    language: str = "English",
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
        language=language,
    )

    last_word_count = 0
    best_markdown_content = ""
    best_word_count = 0
    best_title = ""
    best_meta_description = ""

    attempt = 0
    while attempt < max_generation_attempts():
        raise_if_generation_cancelled(progress_callback)
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
                wait_before_retry(attempt, progress_callback, "banned term match")
                continue

            meta_description_length = len(meta_description)
            if not MIN_META_DESCRIPTION_CHARACTERS <= meta_description_length <= MAX_META_DESCRIPTION_CHARACTERS:
                if _is_close_meta_length(meta_description_length) and can_accept_close_enough(attempt):
                    _publish_progress(
                        progress_callback,
                        f"Page attempt {attempt}: accepting close meta description after strict retries.",
                    )
                else:
                    _publish_progress(
                        progress_callback,
                        f"Page attempt {attempt}: meta description is {meta_description_length} characters, target is 130-160. Retrying...",
                    )
                    logger.warning(
                        "Page meta description is %d characters (target: %d-%d) for keyword '%s' on attempt %d",
                        meta_description_length,
                        MIN_META_DESCRIPTION_CHARACTERS,
                        MAX_META_DESCRIPTION_CHARACTERS,
                        keyword,
                        attempt,
                    )
                    wait_before_retry(attempt, progress_callback, "meta length miss")
                    continue

            repetition_issue = repeated_content_issue(markdown_content)
            if repetition_issue:
                _publish_progress(
                    progress_callback,
                    f"Page content attempt {attempt}: {repetition_issue} Retrying...",
                )
                logger.warning(
                    "Page content repeated text for keyword '%s' on attempt %d: %s",
                    keyword,
                    attempt,
                    repetition_issue,
                )
                wait_before_retry(attempt, progress_callback, "repeated content")
                continue

            if word_count > best_word_count:
                best_markdown_content = markdown_content
                best_word_count = word_count
                best_title = title
                best_meta_description = meta_description
                publish_generation_draft(
                    progress_callback,
                    markdown_to_html(markdown_content),
                    f"Showing a draft while retrying for the checklist ({word_count} words).",
                )

            if word_count <= min_word_count:
                if _is_close_word_count(word_count, min_word_count) and can_accept_close_enough(attempt):
                    _publish_progress(
                        progress_callback,
                        f"Page attempt {attempt}: accepting close word count after strict retries ({word_count} words).",
                    )
                else:
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
                    wait_before_retry(attempt, progress_callback, "short page content")
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
                wait_before_retry(attempt, progress_callback, "long page content")
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

    if best_markdown_content and _is_close_word_count(best_word_count, min_word_count):
        content = markdown_to_html(best_markdown_content)
        content, injected_count = inject_image_placeholders(content)
        _publish_progress(
            progress_callback,
            f"Using best available page after {attempt} attempts ({best_word_count} words).",
        )
        logger.warning(
            "Using best-effort page for keyword '%s' with %d words after %d attempts.",
            keyword,
            best_word_count,
            attempt,
        )
        return {
            "title": best_title,
            "meta_description": best_meta_description,
            "content": content,
            "image_count": injected_count,
        }

    raise ValueError(
        "Generated page could not satisfy the rules. "
        f"Last attempt was {last_word_count} words."
    )


def generate_page_title(
    provider,
    keyword: str,
    supporting_keywords: str = "",
    page_type: str = "",
    expectations: str = "",
    brand: str = "",
    brand_context: str = "",
    language: str = "English",
    progress_callback=None,
) -> str:
    prompt = build_page_title_prompt(
        keyword=keyword,
        supporting_keywords=supporting_keywords,
        page_type=page_type,
        expectations=expectations,
        brand=brand,
        brand_context=brand_context,
        language=language,
    )

    attempt = 0
    while attempt < max_generation_attempts():
        raise_if_generation_cancelled(progress_callback)
        attempt += 1
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                "- Your previous title was missing, used banned words, or did not follow the page title rules.\n"
                f"- The title must start with this exact keyword: {keyword}.\n"
                f"- The title must be between {MIN_PAGE_TITLE_CHARACTERS} and {MAX_PAGE_TITLE_CHARACTERS} characters.\n"
                "- Return one fresh title in valid JSON only.\n"
            )

        full_prompt = prompt + retry_instruction
        _publish_progress(progress_callback, full_prompt, kind="prompt")
        raw = provider.generate_json(full_prompt)

        try:
            json_text = extract_json_string(raw)
            data = json.loads(json_text)
            title = (data.get("title", "") or "").strip()
            if not title:
                _publish_progress(progress_callback, f"Page title attempt {attempt}: no title returned. Retrying...")
                wait_before_retry(attempt, progress_callback, "empty title")
                continue
            if not _starts_with_keyword(title, keyword):
                _publish_progress(
                    progress_callback,
                    f"Page title attempt {attempt}: title must start with '{keyword}'. Retrying...",
                )
                logger.warning(
                    "Page title does not start with keyword '%s' for title '%s' on attempt %d",
                    keyword,
                    title,
                    attempt,
                )
                wait_before_retry(attempt, progress_callback, "page title keyword prefix miss")
                continue
            title_length = len(title)
            if not MIN_PAGE_TITLE_CHARACTERS <= title_length <= MAX_PAGE_TITLE_CHARACTERS:
                _publish_progress(
                    progress_callback,
                    (
                        f"Page title attempt {attempt}: title is {title_length} characters, "
                        f"target is {MIN_PAGE_TITLE_CHARACTERS}-{MAX_PAGE_TITLE_CHARACTERS}. Retrying..."
                    ),
                )
                logger.warning(
                    "Page title is %d characters (target: %d-%d) for keyword '%s' on attempt %d",
                    title_length,
                    MIN_PAGE_TITLE_CHARACTERS,
                    MAX_PAGE_TITLE_CHARACTERS,
                    keyword,
                    attempt,
                )
                wait_before_retry(attempt, progress_callback, "page title length miss")
                continue
            banned_terms = find_banned_terms_in_text(title)
            if banned_terms:
                _publish_progress(
                    progress_callback,
                    f"Page title attempt {attempt}: banned terms found ({', '.join(banned_terms)}). Retrying...",
                )
                logger.warning(
                    "Page title used banned terms %s for keyword '%s' on attempt %d",
                    ", ".join(banned_terms),
                    keyword,
                    attempt,
                )
                wait_before_retry(attempt, progress_callback, "banned term match")
                continue
            return title
        except Exception as exc:
            logger.exception("generate_page_title failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

    raise ValueError("Generated page title could not satisfy the rules.")


def _starts_with_keyword(title: str, keyword: str) -> bool:
    cleaned_title = (title or "").strip()
    cleaned_keyword = (keyword or "").strip()
    return bool(cleaned_keyword and cleaned_title.startswith(cleaned_keyword))


def generate_page_meta_description(
    provider,
    keyword: str,
    title: str,
    supporting_keywords: str = "",
    page_type: str = "",
    expectations: str = "",
    brand: str = "",
    brand_context: str = "",
    language: str = "English",
    progress_callback=None,
) -> str:
    prompt = build_page_meta_description_prompt(
        keyword=keyword,
        title=title,
        supporting_keywords=supporting_keywords,
        page_type=page_type,
        expectations=expectations,
        brand=brand,
        brand_context=brand_context,
        language=language,
    )

    attempt = 0
    while attempt < max_generation_attempts():
        raise_if_generation_cancelled(progress_callback)
        attempt += 1
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                "- Your previous meta description was missing, used banned words, or missed the 130-160 character range.\n"
                "- Return one fresh meta description in valid JSON only.\n"
                "- Count only the description text, not JSON syntax.\n"
            )

        full_prompt = prompt + retry_instruction
        _publish_progress(progress_callback, full_prompt, kind="prompt")
        raw = provider.generate_json(full_prompt)

        try:
            json_text = extract_json_string(raw)
            data = json.loads(json_text)
            meta_description = (data.get("meta_description", "") or "").strip()
            if not meta_description:
                _publish_progress(progress_callback, f"Page meta attempt {attempt}: no meta description returned. Retrying...")
                wait_before_retry(attempt, progress_callback, "empty meta description")
                continue
            banned_terms = find_banned_terms_in_text(meta_description)
            if banned_terms:
                _publish_progress(
                    progress_callback,
                    f"Page meta attempt {attempt}: banned terms found ({', '.join(banned_terms)}). Retrying...",
                )
                logger.warning(
                    "Page meta description used banned terms %s for keyword '%s' on attempt %d",
                    ", ".join(banned_terms),
                    keyword,
                    attempt,
                )
                wait_before_retry(attempt, progress_callback, "banned term match")
                continue
            meta_description_length = len(meta_description)
            if not MIN_META_DESCRIPTION_CHARACTERS <= meta_description_length <= MAX_META_DESCRIPTION_CHARACTERS:
                if _is_close_meta_length(meta_description_length) and can_accept_close_enough(attempt):
                    _publish_progress(
                        progress_callback,
                        f"Page meta attempt {attempt}: accepting close description after strict retries.",
                    )
                    return meta_description
                _publish_progress(
                    progress_callback,
                    f"Page meta attempt {attempt}: {meta_description_length} characters, target is 130-160. Retrying...",
                )
                logger.warning(
                    "Page meta description is %d characters (target: %d-%d) for keyword '%s' on attempt %d",
                    meta_description_length,
                    MIN_META_DESCRIPTION_CHARACTERS,
                    MAX_META_DESCRIPTION_CHARACTERS,
                    keyword,
                    attempt,
                )
                wait_before_retry(attempt, progress_callback, "meta length miss")
                continue
            return meta_description
        except Exception as exc:
            logger.exception("generate_page_meta_description failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

    raise ValueError("Generated page meta description could not satisfy the rules.")


def generate_page_content(
    provider,
    keyword: str,
    title: str,
    meta_description: str,
    supporting_keywords: str = "",
    page_type: str = "",
    expectations: str = "",
    brand: str = "",
    brand_context: str = "",
    change_request: str = "",
    min_words: int = MIN_PAGE_WORDS,
    max_words: int = MAX_PAGE_WORDS,
    language: str = "English",
    progress_callback=None,
):
    from app.services.content_format_service import count_markdown_words, markdown_to_html

    min_word_count, max_word_count = _normalize_word_limits(min_words, max_words)
    prompt = build_page_content_prompt(
        keyword=keyword,
        title=title,
        meta_description=meta_description,
        supporting_keywords=supporting_keywords,
        page_type=page_type,
        expectations=expectations,
        brand=brand,
        brand_context=brand_context,
        change_request=change_request,
        min_words=min_word_count,
        max_words=max_word_count,
        language=language,
    )

    last_word_count = 0
    best_markdown_content = ""
    best_word_count = 0
    attempt = 0
    while attempt < max_generation_attempts():
        raise_if_generation_cancelled(progress_callback)
        attempt += 1
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                f"\n\nIMPORTANT RETRY REQUIREMENT:\n"
                f"- Your previous page content did not satisfy the word-count, banned-word, or no-repetition rules.\n"
                f"- Keep the selected title exactly: {title}\n"
                f"- Return valid JSON only.\n"
                f"- The page content must be more than {min_word_count} words. Treat {max_word_count} words as a soft guide, but prioritize staying over the minimum.\n"
                f"- Do not finish at exactly {min_word_count} words; expand until the page exceeds that minimum.\n"
                f"- Do not repeat the same sentence or paragraph. Rewrite repeated ideas with fresh details.\n"
            )

        full_prompt = prompt + retry_instruction
        _publish_progress(progress_callback, full_prompt, kind="prompt")
        raw = provider.generate_json(full_prompt)

        try:
            json_text = extract_json_string(raw)
            data = json.loads(json_text)
            markdown_content = (data.get("content", "") or "").strip()
            word_count = count_markdown_words(markdown_content)
            last_word_count = word_count
            banned_terms = find_banned_terms_in_text(markdown_content)

            if banned_terms:
                _publish_progress(
                    progress_callback,
                    f"Page content attempt {attempt}: banned terms found ({', '.join(banned_terms)}). Retrying...",
                )
                logger.warning(
                    "Page content used banned terms %s for keyword '%s' on attempt %d",
                    ", ".join(banned_terms),
                    keyword,
                    attempt,
                )
                wait_before_retry(attempt, progress_callback, "banned term match")
                continue

            repetition_issue = repeated_content_issue(markdown_content)
            if repetition_issue:
                _publish_progress(
                    progress_callback,
                    f"Page content attempt {attempt}: {repetition_issue} Retrying...",
                )
                logger.warning(
                    "Page content repeated text for keyword '%s' on attempt %d: %s",
                    keyword,
                    attempt,
                    repetition_issue,
                )
                wait_before_retry(attempt, progress_callback, "repeated content")
                continue

            if word_count > best_word_count:
                best_markdown_content = markdown_content
                best_word_count = word_count
                publish_generation_draft(
                    progress_callback,
                    markdown_to_html(markdown_content),
                    f"Showing a draft while retrying for the checklist ({word_count} words).",
                )

            if word_count <= min_word_count:
                if _is_close_word_count(word_count, min_word_count) and can_accept_close_enough(attempt):
                    _publish_progress(
                        progress_callback,
                        f"Page content attempt {attempt}: accepting close word count after strict retries ({word_count} words).",
                    )
                else:
                    _publish_progress(
                        progress_callback,
                        f"Page content attempt {attempt}: {word_count} words, content must be more than {min_word_count}. Retrying...",
                    )
                    logger.warning(
                        "Page content word count is %d (must be more than: %d) for keyword '%s' on attempt %d",
                        word_count,
                        min_word_count,
                        keyword,
                        attempt,
                    )
                    wait_before_retry(attempt, progress_callback, "short page content")
                    continue

            if not min_word_count and word_count > max_word_count:
                _publish_progress(
                    progress_callback,
                    f"Page content attempt {attempt}: {word_count} words, maximum is {max_word_count}. Retrying...",
                )
                wait_before_retry(attempt, progress_callback, "long page content")
                continue

            content = markdown_to_html(markdown_content)
            content, injected_count = inject_image_placeholders(content)
            logger.info(
                "Page content generated successfully for keyword '%s' with %d words and %d image placeholders on attempt %d",
                keyword,
                word_count,
                injected_count,
                attempt,
            )
            return {
                "content": content,
                "image_count": injected_count,
            }
        except Exception as exc:
            logger.exception("generate_page_content failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

    if best_markdown_content and _is_close_word_count(best_word_count, min_word_count):
        content = markdown_to_html(best_markdown_content)
        content, injected_count = inject_image_placeholders(content)
        _publish_progress(
            progress_callback,
            f"Using best available page content after {attempt} attempts ({best_word_count} words).",
        )
        logger.warning(
            "Using best-effort page content for keyword '%s' with %d words after %d attempts.",
            keyword,
            best_word_count,
            attempt,
        )
        return {
            "content": content,
            "image_count": injected_count,
        }

    raise ValueError(
        "Generated page content could not satisfy the rules. "
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


def _is_close_meta_length(length: int) -> bool:
    return 100 <= length <= 160


def _is_close_word_count(word_count: int, min_word_count: int) -> bool:
    if not min_word_count:
        return True
    return word_count >= int(min_word_count * 0.85)


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
