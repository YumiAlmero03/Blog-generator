import json
import re

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
MAX_META_DESCRIPTION_CHARACTERS = 160


def _heading_paragraph_issues(markdown_content: str) -> list[str]:
    blocks = []
    paragraph_lines = []

    def flush_paragraph():
        if paragraph_lines:
            blocks.append(("paragraph", " ".join(paragraph_lines)))
            paragraph_lines.clear()

    for raw_line in (markdown_content or "").replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if not line:
            flush_paragraph()
        elif heading:
            flush_paragraph()
            blocks.append(("heading", heading.group(1)))
        elif re.match(r"^(?:[-*]\s+|\d+\.\s+|>)", line):
            flush_paragraph()
            blocks.append(("other", ""))
        else:
            paragraph_lines.append(line)
    flush_paragraph()

    issues = []
    h2_count = sum(kind == "heading" and value == "##" for kind, value in blocks)
    h3_count = sum(kind == "heading" and value == "###" for kind, value in blocks)
    if h2_count < 1:
        issues.append("missing an ## H2 heading")
    if h3_count < 1:
        issues.append("missing a ### H3 heading")

    for index, (kind, value) in enumerate(blocks):
        if kind != "heading" or value not in {"##", "###"}:
            continue
        paragraph_count = 0
        for following_kind, following_value in blocks[index + 1:]:
            if following_kind == "heading":
                break
            if following_kind == "paragraph":
                paragraph_count += 1
        if paragraph_count < 1 or paragraph_count > 2:
            issues.append(f"{value} heading has {paragraph_count} paragraphs; expected 1 or 2")
    issues.extend(_introduction_issues(blocks))
    return issues


def _introduction_issues(blocks: list[tuple[str, str]]) -> list[str]:
    h1_index = next((index for index, (kind, value) in enumerate(blocks) if kind == "heading" and value == "#"), None)
    if h1_index is None:
        return ["missing the # H1 heading required before the introduction"]

    introduction_blocks = []
    for kind, value in blocks[h1_index + 1:]:
        if kind == "heading":
            break
        if kind == "paragraph":
            introduction_blocks.append(value)
    if len(introduction_blocks) != 1:
        return [f"introduction has {len(introduction_blocks)} paragraphs; expected exactly 1"]

    sentence_count = len([sentence for sentence in re.split(r"[.!?]+(?:\s+|$)", introduction_blocks[0]) if sentence.strip()])
    if not 1 <= sentence_count <= 3:
        return [f"introduction has {sentence_count} sentences; expected 1 to 3"]
    return []


def generate_simple_page(
    provider,
    page_title: str,
    page_type: str = "",
    brand: str = "",
    supporting_keywords: str = "",
    expectations: str = "",
    brand_context: str = "",
    change_request: str = "",
    min_words: int = MIN_SIMPLE_PAGE_WORDS,
    max_words: int = MAX_SIMPLE_PAGE_WORDS,
    language: str = "English",
    progress_callback=None,
):
    from app.services.content_format_service import count_markdown_words, markdown_to_html

    min_word_count, max_word_count = _normalize_word_limits(min_words, max_words)
    prompt = build_simple_page_prompt(
        page_title=page_title,
        page_type=page_type,
        brand=brand,
        supporting_keywords=supporting_keywords,
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
                "- The introduction immediately after the H1 must be exactly one paragraph containing 1 to 3 sentences.\n"
                "- Include at least one ## H2 heading and at least one ### H3 heading.\n"
                "- Follow every ## H2 and ### H3 heading with 1 or 2 paragraphs before the next heading.\n"
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
                    f"Simple page attempt {attempt}: meta descriptions missed 120-160 characters ({', '.join(str(length) for length in invalid_meta_lengths)} chars). Retrying...",
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
            heading_issues = _heading_paragraph_issues(markdown_content)
            if heading_issues:
                _publish_progress(
                    progress_callback,
                    f"Simple page attempt {attempt}: {'; '.join(heading_issues)}. Retrying...",
                )
                logger.warning(
                    "Simple page heading structure failed on attempt %d: %s",
                    attempt,
                    "; ".join(heading_issues),
                )
                wait_before_retry(attempt, progress_callback, "invalid heading structure")
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
    supporting_keywords: str = "",
    expectations: str = "",
    brand_context: str = "",
    language: str = "English",
    progress_callback=None,
) -> str:
    prompt = build_simple_page_title_prompt(
        page_title=page_title,
        page_type=page_type,
        brand=brand,
        supporting_keywords=supporting_keywords,
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
                f"- The title must start with this exact page title: {page_title}.\n"
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
            if not _starts_with_page_title(title, page_title):
                _publish_progress(
                    progress_callback,
                    f"Simple page title attempt {attempt}: title must start with '{page_title}'. Retrying...",
                )
                wait_before_retry(attempt, progress_callback, "simple page title prefix miss")
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


def _starts_with_page_title(title: str, page_title: str) -> bool:
    cleaned_title = (title or "").strip()
    cleaned_page_title = (page_title or "").strip()
    return bool(cleaned_page_title and cleaned_title.startswith(cleaned_page_title))


def generate_simple_page_meta_descriptions(
    provider,
    page_title: str,
    generated_title: str,
    page_type: str = "",
    brand: str = "",
    supporting_keywords: str = "",
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
        supporting_keywords=supporting_keywords,
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
                "- Your previous response used banned words, missed the 120-160 character range, or returned too few descriptions.\n"
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
                    f"Simple page meta attempt {attempt}: descriptions missed 120-160 characters ({', '.join(str(length) for length in invalid_lengths)} chars). Retrying...",
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
    supporting_keywords: str = "",
    expectations: str = "",
    brand_context: str = "",
    change_request: str = "",
    min_words: int = MIN_SIMPLE_PAGE_WORDS,
    max_words: int = MAX_SIMPLE_PAGE_WORDS,
    language: str = "English",
    progress_callback=None,
):
    from app.services.content_format_service import count_markdown_words, markdown_to_html

    min_word_count, max_word_count = _normalize_word_limits(min_words, max_words)
    prompt = build_simple_page_content_prompt(
        page_title=page_title,
        generated_title=generated_title,
        selected_meta_description=selected_meta_description,
        page_type=page_type,
        brand=brand,
        supporting_keywords=supporting_keywords,
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
                "- The introduction immediately after the H1 must be exactly one paragraph containing 1 to 3 sentences.\n"
                "- Include at least one ## H2 heading and at least one ### H3 heading.\n"
                "- Follow every ## H2 and ### H3 heading with 1 or 2 paragraphs before the next heading.\n"
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
            heading_issues = _heading_paragraph_issues(markdown_content)
            if heading_issues:
                _publish_progress(
                    progress_callback,
                    f"Simple page content attempt {attempt}: {'; '.join(heading_issues)}. Retrying...",
                )
                wait_before_retry(attempt, progress_callback, "invalid heading structure")
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
