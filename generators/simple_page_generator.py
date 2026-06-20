import json

from generation_retry_policy import (
    can_accept_close_enough,
    max_generation_attempts,
    publish_generation_draft,
    raise_if_generation_cancelled,
    wait_before_retry,
)
from logger import logger
from prompts import (
    build_simple_page_content_prompt,
    build_simple_page_meta_prompt,
    build_simple_page_prompt,
    build_simple_page_title_prompt,
)
from utils import extract_json_string
from word_bank import find_banned_terms_in_text
from content_repetition import repeated_content_issue

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
    language: str = "English",
    progress_callback=None,
):
    from app.services.content_format_service import count_markdown_heading_level, count_markdown_words, markdown_to_html

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
        language=language,
    )

    last_word_count = 0

    attempt = 0
    while attempt < max_generation_attempts():
        raise_if_generation_cancelled(progress_callback)
        attempt += 1
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                "- Your previous response used banned words, repeated content, missed required ### subheadings, missed the word-count range, or missed the meta description character range.\n"
                f"- The page content must be at least {min_word_count} words. Treat {max_word_count} words as a soft guide, but prioritize staying over the minimum.\n"
                f"- Every meta description must be between {MIN_META_DESCRIPTION_CHARACTERS} and {MAX_META_DESCRIPTION_CHARACTERS} characters.\n"
                "- Include at least 3 ### subheadings.\n"
                "- Do not repeat the same sentence or paragraph. Rewrite repeated ideas with fresh details.\n"
                "- Return a fresh simple page and avoid every banned term completely.\n"
            )

        full_prompt = prompt + retry_instruction
        _publish_progress(progress_callback, full_prompt, kind="prompt")
        raw = provider.generate_json(full_prompt)

        try:
            json_text = extract_json_string(raw)
            data = json.loads(json_text)
            title = data.get("title", "").strip()
            markdown_content = data.get("content", "").strip()
            word_count = count_markdown_words(markdown_content)
            last_word_count = word_count
            meta_descriptions = _normalize_meta_descriptions(data.get("meta_descriptions", []))
            meta_text = "\n".join(item.get("text", "") for item in meta_descriptions)
            banned_terms = find_banned_terms_in_text("\n".join([title, markdown_content, meta_text]))
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
                wait_before_retry(attempt, progress_callback, "banned term match")
                continue
            repetition_issue = repeated_content_issue(markdown_content)
            if repetition_issue:
                _publish_progress(
                    progress_callback,
                    f"Simple page attempt {attempt}: {repetition_issue} Retrying...",
                )
                logger.warning(
                    "Simple page repeated content on attempt %d: %s",
                    attempt,
                    repetition_issue,
                )
                wait_before_retry(attempt, progress_callback, "repeated content")
                continue
            invalid_meta_lengths = [
                len(item.get("text", ""))
                for item in meta_descriptions
                if not MIN_META_DESCRIPTION_CHARACTERS <= len(item.get("text", "")) <= MAX_META_DESCRIPTION_CHARACTERS
            ]
            if invalid_meta_lengths:
                _publish_progress(
                    progress_callback,
                    f"Simple page attempt {attempt}: meta descriptions missed 130-160 characters ({', '.join(str(length) for length in invalid_meta_lengths)} chars). Retrying...",
                )
                logger.warning(
                    "Simple page meta descriptions missed %d-%d characters with lengths %s on attempt %d",
                    MIN_META_DESCRIPTION_CHARACTERS,
                    MAX_META_DESCRIPTION_CHARACTERS,
                    ", ".join(str(length) for length in invalid_meta_lengths),
                    attempt,
                )
                wait_before_retry(attempt, progress_callback, "meta length miss")
                continue
            h3_count = count_markdown_heading_level(markdown_content, 3)
            if h3_count < 3:
                _publish_progress(
                    progress_callback,
                    f"Simple page attempt {attempt}: only {h3_count} ### subheadings, minimum is 3. Retrying...",
                )
                logger.warning(
                    "Simple page used only %d ### subheadings on attempt %d",
                    h3_count,
                    attempt,
                )
                wait_before_retry(attempt, progress_callback, "missing subheadings")
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
                wait_before_retry(attempt, progress_callback, "short simple page")
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
                wait_before_retry(attempt, progress_callback, "long simple page")
                continue

            logger.info("Simple page generated successfully for '%s' with %d words", page_title, word_count)
            return {
                "title": title,
                "meta_descriptions": meta_descriptions,
                "content": markdown_to_html(markdown_content),
            }
        except Exception as exc:
            logger.exception("generate_simple_page failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

    raise ValueError(
        "Generated simple page could not satisfy the rules. "
        f"Last attempt was {last_word_count} words."
    )


def generate_simple_page_title(
    provider,
    page_title: str,
    page_type: str = "",
    brand: str = "",
    expectations: str = "",
    brand_context: str = "",
    language: str = "English",
    progress_callback=None,
) -> str:
    prompt = build_simple_page_title_prompt(
        page_title=page_title,
        page_type=page_type,
        brand=brand,
        expectations=expectations,
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
                "- Your previous title was missing or used banned words.\n"
                "- Return one fresh title in valid JSON only.\n"
            )
        full_prompt = prompt + retry_instruction
        _publish_progress(progress_callback, full_prompt, kind="prompt")
        raw = provider.generate_json(full_prompt)
        try:
            data = json.loads(extract_json_string(raw))
            title = (data.get("title", "") or "").strip()
            if not title:
                _publish_progress(progress_callback, f"Simple page title attempt {attempt}: no title returned. Retrying...")
                wait_before_retry(attempt, progress_callback, "empty title")
                continue
            banned_terms = find_banned_terms_in_text(title)
            if banned_terms:
                _publish_progress(
                    progress_callback,
                    f"Simple page title attempt {attempt}: banned terms found ({', '.join(banned_terms)}). Retrying...",
                )
                wait_before_retry(attempt, progress_callback, "banned term match")
                continue
            return title
        except Exception as exc:
            logger.exception("generate_simple_page_title failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

    raise ValueError("Generated simple page title could not satisfy the rules.")


def generate_simple_page_meta_descriptions(
    provider,
    page_title: str,
    generated_title: str,
    page_type: str = "",
    brand: str = "",
    expectations: str = "",
    brand_context: str = "",
    language: str = "English",
    progress_callback=None,
) -> list[dict]:
    prompt = build_simple_page_meta_prompt(
        page_title=page_title,
        generated_title=generated_title,
        page_type=page_type,
        brand=brand,
        expectations=expectations,
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
                "- Your previous response used banned words, missed the 130-160 character range, or returned too few descriptions.\n"
                "- Return exactly 3 fresh meta descriptions in valid JSON only.\n"
            )
        full_prompt = prompt + retry_instruction
        _publish_progress(progress_callback, full_prompt, kind="prompt")
        raw = provider.generate_json(full_prompt)
        try:
            data = json.loads(extract_json_string(raw))
            meta_descriptions = _normalize_meta_descriptions(data.get("meta_descriptions", []))
            if len(meta_descriptions) < 3:
                _publish_progress(
                    progress_callback,
                    f"Simple page meta attempt {attempt}: returned {len(meta_descriptions)} usable descriptions, target is 3. Retrying...",
                )
                wait_before_retry(attempt, progress_callback, "too few meta descriptions")
                continue
            meta_text = "\n".join(item.get("text", "") for item in meta_descriptions)
            banned_terms = find_banned_terms_in_text(meta_text)
            if banned_terms:
                _publish_progress(
                    progress_callback,
                    f"Simple page meta attempt {attempt}: banned terms found ({', '.join(banned_terms)}). Retrying...",
                )
                wait_before_retry(attempt, progress_callback, "banned term match")
                continue
            invalid_lengths = [
                len(item.get("text", ""))
                for item in meta_descriptions
                if not MIN_META_DESCRIPTION_CHARACTERS <= len(item.get("text", "")) <= MAX_META_DESCRIPTION_CHARACTERS
            ]
            if invalid_lengths:
                if all(_is_close_meta_length(length) for length in invalid_lengths) and can_accept_close_enough(attempt):
                    _publish_progress(
                        progress_callback,
                        f"Simple page meta attempt {attempt}: accepting close descriptions after strict retries.",
                    )
                    return meta_descriptions[:3]
                _publish_progress(
                    progress_callback,
                    f"Simple page meta attempt {attempt}: descriptions missed 130-160 characters ({', '.join(str(length) for length in invalid_lengths)} chars). Retrying...",
                )
                wait_before_retry(attempt, progress_callback, "meta length miss")
                continue
            return meta_descriptions[:3]
        except Exception as exc:
            logger.exception("generate_simple_page_meta_descriptions failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

    raise ValueError("Generated simple page meta descriptions could not satisfy the rules.")


def generate_simple_page_content(
    provider,
    page_title: str,
    generated_title: str,
    selected_meta_description: str = "",
    page_type: str = "",
    brand: str = "",
    expectations: str = "",
    brand_context: str = "",
    change_request: str = "",
    min_words: int = MIN_SIMPLE_PAGE_WORDS,
    max_words: int = MAX_SIMPLE_PAGE_WORDS,
    language: str = "English",
    progress_callback=None,
):
    from app.services.content_format_service import count_markdown_heading_level, count_markdown_words, markdown_to_html

    min_word_count, max_word_count = _normalize_word_limits(min_words, max_words)
    prompt = build_simple_page_content_prompt(
        page_title=page_title,
        generated_title=generated_title,
        selected_meta_description=selected_meta_description,
        page_type=page_type,
        brand=brand,
        expectations=expectations,
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
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                "- Your previous content used banned words, repeated content, missed required ### subheadings, or missed the word-count range.\n"
                f"- The page content must be at least {min_word_count} words.\n"
                "- Include at least 3 ### subheadings.\n"
                "- Do not repeat the same sentence or paragraph. Rewrite repeated ideas with fresh details.\n"
                "- Return corrected content in valid JSON only.\n"
            )
        full_prompt = prompt + retry_instruction
        _publish_progress(progress_callback, full_prompt, kind="prompt")
        raw = provider.generate_json(full_prompt)
        try:
            data = json.loads(extract_json_string(raw))
            markdown_content = (data.get("content", "") or "").strip()
            word_count = count_markdown_words(markdown_content)
            last_word_count = word_count
            banned_terms = find_banned_terms_in_text(markdown_content)
            if banned_terms:
                _publish_progress(
                    progress_callback,
                    f"Simple page content attempt {attempt}: banned terms found ({', '.join(banned_terms)}). Retrying...",
                )
                wait_before_retry(attempt, progress_callback, "banned term match")
                continue
            repetition_issue = repeated_content_issue(markdown_content)
            if repetition_issue:
                _publish_progress(
                    progress_callback,
                    f"Simple page content attempt {attempt}: {repetition_issue} Retrying...",
                )
                wait_before_retry(attempt, progress_callback, "repeated content")
                continue
            h3_count = count_markdown_heading_level(markdown_content, 3)
            if h3_count < 3:
                _publish_progress(
                    progress_callback,
                    f"Simple page content attempt {attempt}: only {h3_count} ### subheadings, minimum is 3. Retrying...",
                )
                wait_before_retry(attempt, progress_callback, "missing subheadings")
                continue
            if word_count > best_word_count:
                best_markdown_content = markdown_content
                best_word_count = word_count
                publish_generation_draft(
                    progress_callback,
                    markdown_to_html(markdown_content),
                    f"Showing a draft while retrying for the checklist ({word_count} words).",
                )
            if word_count < min_word_count:
                if _is_close_word_count(word_count, min_word_count) and can_accept_close_enough(attempt):
                    _publish_progress(
                        progress_callback,
                        f"Simple page content attempt {attempt}: accepting close word count after strict retries ({word_count} words).",
                    )
                else:
                    _publish_progress(
                        progress_callback,
                        f"Simple page content attempt {attempt}: {word_count} words, minimum is {min_word_count}. Retrying...",
                    )
                    wait_before_retry(attempt, progress_callback, "short simple page content")
                    continue
            if not min_word_count and word_count > max_word_count:
                _publish_progress(
                    progress_callback,
                    f"Simple page content attempt {attempt}: {word_count} words, maximum is {max_word_count}. Retrying...",
                )
                wait_before_retry(attempt, progress_callback, "long simple page content")
                continue
            return markdown_to_html(markdown_content)
        except Exception as exc:
            logger.exception("generate_simple_page_content failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

    if best_markdown_content and _is_close_word_count(best_word_count, min_word_count):
        _publish_progress(
            progress_callback,
            f"Using best available simple page content after {attempt} attempts ({best_word_count} words).",
        )
        logger.warning(
            "Using best-effort simple page content with %d words after %d attempts.",
            best_word_count,
            attempt,
        )
        return markdown_to_html(best_markdown_content)

    raise ValueError(
        "Generated simple page content could not satisfy the rules. "
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


def _is_close_meta_length(length: int) -> bool:
    return 100 <= length <= 160


def _is_close_word_count(word_count: int, min_word_count: int) -> bool:
    if not min_word_count:
        return True
    return word_count >= int(min_word_count * 0.85)


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
