import json
import re
from prompts import build_backlink_content_prompt, build_content_prompt
from utils import extract_json_string
from logger import logger
from word_bank import find_banned_terms_in_text

MIN_BLOG_WORDS = 1300

def count_html_words(html_text: str) -> int:
    """Count words in HTML content by removing tags."""
    clean_text = re.sub(r'<[^>]+>', '', html_text)
    words = clean_text.split()
    return len(words)


def suggest_content_tags(
    title: str = "",
    keyword: str = "",
    supporting_keyword: str = "",
    brand: str = "",
    content: str = "",
    minimum: int = 10,
) -> list[str]:
    text_parts = [title, keyword, supporting_keyword, brand, re.sub(r"<[^>]+>", " ", content or "")]
    combined = " ".join(part for part in text_parts if part).lower()
    stop_words = {
        "about",
        "after",
        "also",
        "and",
        "are",
        "article",
        "because",
        "before",
        "blog",
        "but",
        "can",
        "content",
        "for",
        "from",
        "guide",
        "has",
        "have",
        "how",
        "into",
        "its",
        "more",
        "not",
        "that",
        "the",
        "this",
        "through",
        "tips",
        "use",
        "when",
        "where",
        "why",
        "with",
        "your",
    }
    tags = []

    def add_tag(value: str):
        cleaned = re.sub(r"[^a-zA-Z0-9 &+-]", " ", value or "")
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_").lower()
        if not cleaned or cleaned in stop_words or len(cleaned) < 3 or len(cleaned.split()) > 4:
            return
        if cleaned not in tags:
            tags.append(cleaned)

    for phrase in [brand, keyword, supporting_keyword, title]:
        for item in re.split(r"[,;/|]+", phrase or ""):
            add_tag(item)

    words = re.findall(r"[a-zA-Z][a-zA-Z0-9+-]{2,}", combined)
    word_counts = {}
    for word in words:
        if word in stop_words or len(word) < 3:
            continue
        word_counts[word] = word_counts.get(word, 0) + 1

    for word, _count in sorted(word_counts.items(), key=lambda item: (-item[1], item[0])):
        add_tag(word)
        if len(tags) >= minimum + 5:
            break

    fallback_tags = [
        "seo",
        "digital marketing",
        "online visibility",
        "brand awareness",
        "content strategy",
        "search optimization",
        "marketing guide",
        "business growth",
        "website content",
        "customer engagement",
    ]
    for fallback in fallback_tags:
        if len(tags) >= minimum:
            break
        add_tag(fallback)

    return tags[: max(minimum, len(tags))]


def parse_generated_content(raw: str) -> tuple[str, int]:
    json_text = extract_json_string(raw)
    data = json.loads(json_text)
    content = data.get("content", "")
    word_count = count_html_words(content)
    return content, word_count


def _generate_content_from_prompt(provider, prompt: str, min_words: int = MIN_BLOG_WORDS, max_words: int = 0, validator=None, progress_callback=None):
    last_word_count = 0
    last_validation_error = ""
    last_length_error = ""
    last_failure_detail = ""

    attempt = 0
    while True:
        attempt += 1
        retry_instruction = ""
        if attempt > 1:
            if min_words:
                retry_instruction = (
                    f"\n\nIMPORTANT RETRY REQUIREMENT:\n"
                    f"- Your previous response was too short.\n"
                    f"- Return COMPLETE content in the required selected format only inside JSON.\n"
                    f"- The article must be at least {min_words} words.\n"
                    f"- Expand each section with more detail, examples, and explanation.\n"
                )
            else:
                retry_instruction = (
                    "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                    "- Return COMPLETE content in the required selected format only inside JSON.\n"
                    "- Respect the selected medium's shorter content limit.\n"
                    "- Keep the output concise, complete, and suitable for the medium.\n"
                )
            if last_length_error:
                retry_instruction += (
                    "\nIMPORTANT RETRY REQUIREMENT:\n"
                    f"- {last_length_error}\n"
                    "- Return corrected content in the required selected format only inside JSON.\n"
                )
                if min_words:
                    retry_instruction += (
                        f"- Do not cut useful context below the minimum word count of {min_words} words.\n"
                    )
            if last_validation_error:
                retry_instruction += (
                    "\nIMPORTANT RETRY REQUIREMENT:\n"
                    f"- {last_validation_error}\n"
                    "- Return corrected content in the required selected format only inside JSON.\n"
                )

        full_prompt = prompt + retry_instruction
        _publish_progress(progress_callback, full_prompt, kind="prompt")
        raw = provider.generate_json(full_prompt)

        try:
            content, word_count = parse_generated_content(raw)
            last_word_count = word_count
            banned_terms = find_banned_terms_in_text(content)

            if banned_terms:
                last_failure_detail = f"Content used banned terms {', '.join(banned_terms)} on attempt {attempt}."
                _publish_progress(
                    progress_callback,
                    f"Content attempt {attempt}: banned terms found ({', '.join(banned_terms)}). Retrying...",
                )
                logger.warning(
                    "Content used banned terms %s on attempt %d",
                    ", ".join(banned_terms),
                    attempt,
                )
                continue

            if min_words and word_count < min_words:
                last_failure_detail = (
                    f"Content word count is {word_count} (minimum: {min_words}) "
                    f"on attempt {attempt}. Raw response length: {len(raw)} chars."
                )
                _publish_progress(
                    progress_callback,
                    f"Content attempt {attempt}: {word_count} words, minimum is {min_words}. Retrying with more detail...",
                )
                logger.warning(
                    "Content word count is %d (minimum: %d) on attempt %d. Raw response length: %d chars",
                    word_count,
                    min_words,
                    attempt,
                    len(raw),
                )
                continue

            if max_words and not min_words and word_count > max_words:
                last_length_error = f"Your previous response was long at {word_count} words. Aim closer to {max_words} words, but prioritize staying over the minimum word count."
                last_failure_detail = (
                    f"Content word count is {word_count} (maximum: {max_words}) "
                    f"on attempt {attempt}. Raw response length: {len(raw)} chars."
                )
                _publish_progress(
                    progress_callback,
                    f"Content attempt {attempt}: {word_count} words, soft maximum is {max_words}. Retrying more concise while staying over the minimum...",
                )
                logger.warning(
                    "Content word count is %d (maximum: %d) on attempt %d. Raw response length: %d chars",
                    word_count,
                    max_words,
                    attempt,
                    len(raw),
                )
                continue

            if validator:
                validation_error = validator(content)
                if validation_error:
                    last_validation_error = validation_error
                    last_failure_detail = (
                        f"Content validation failed on attempt {attempt}: {validation_error}"
                    )
                    _publish_progress(
                        progress_callback,
                        f"Content attempt {attempt}: {validation_error} Retrying...",
                    )
                    logger.warning(
                        "Content validation failed on attempt %d: %s",
                        attempt,
                        validation_error,
                    )
                    continue

            logger.info(
                "Content generated successfully with %d words on attempt %d",
                word_count,
                attempt,
            )
            return content
        except Exception as exc:
            logger.exception("generate_content failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

    raise ValueError(
        "Generated article could not satisfy the rules. "
        f"{last_failure_detail or f'Last attempt was {last_word_count} words.'}"
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
    change_request: str = "",
    min_words: int = MIN_BLOG_WORDS,
    max_words: int = 1400,
    progress_callback=None,
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
        change_request=change_request,
        min_words=min_words,
        max_words=max_words,
    )
    return _generate_content_from_prompt(
        provider,
        prompt,
        min_words=min_words,
        max_words=max_words,
        progress_callback=progress_callback,
    )


def keep_required_url_once(content: str, required_url: str) -> str:
    cleaned_url = (required_url or "").strip()
    if not cleaned_url:
        return content

    escaped_url = re.escape(cleaned_url)
    link_pattern = re.compile(
        rf"<a\b(?P<attrs>[^>]*\bhref=(?P<quote>['\"]){escaped_url}(?P=quote)[^>]*)>(?P<text>.*?)</a>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    link_count = 0

    def replace_duplicate_link(match: re.Match) -> str:
        nonlocal link_count
        link_count += 1
        if link_count == 1:
            return match.group(0)
        return match.group("text")

    cleaned_content = link_pattern.sub(replace_duplicate_link, content or "")

    if link_count:
        return cleaned_content

    plain_count = 0

    def replace_duplicate_plain_url(match: re.Match) -> str:
        nonlocal plain_count
        plain_count += 1
        if plain_count == 1:
            return match.group(0)
        return ""

    return re.sub(escaped_url, replace_duplicate_plain_url, cleaned_content)


def required_url_presence_error(content: str, required_url: str) -> str:
    cleaned_url = (required_url or "").strip()
    if not cleaned_url:
        return ""

    if cleaned_url not in (content or ""):
        return "The required brand URL must be inserted exactly once anywhere in the article."
    return ""


def medium_example_mention_error(content: str, brand: str = "", keyword: str = "") -> str:
    visible_text = re.sub(r"<[^>]+>", " ", content or "")
    visible_text = re.sub(r"https?://\S+|www\.\S+", " ", visible_text)
    checks = [
        ("brand name", (brand or "").strip()),
        ("primary keyword", (keyword or "").strip()),
    ]
    for label, phrase in checks:
        if not phrase:
            continue
        phrase_pattern = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", flags=re.IGNORECASE)
        count = len(phrase_pattern.findall(visible_text))
        if count > 1:
            return f"The generated medium content mentioned the {label} {count} times. Mention it no more than once as a natural example."
    return ""


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
    backlink_post_type: str = "html",
    backlink_title_max_characters: int | str = 0,
    backlink_min_words: int | str = 0,
    backlink_max_characters: int | str = 0,
    backlink_tier_level: str = "",
    backlink_blog_name: str = "",
    backlink_writer_name: str = "",
    backlink_content_guidelines: str = "",
    suggested_content: str = "",
    change_request: str = "",
    progress_callback=None,
):
    effective_max_words = _effective_medium_max_words(
        backlink_website_name,
        backlink_blog_name,
        backlink_website_type,
        backlink_max_characters,
    )
    effective_min_words = _effective_medium_min_words(backlink_min_words)
    validation_min_words = effective_min_words
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
        backlink_post_type=backlink_post_type,
        backlink_title_max_characters=backlink_title_max_characters,
        backlink_min_words=effective_min_words,
        backlink_max_characters=effective_max_words,
        backlink_tier_level=backlink_tier_level,
        backlink_blog_name=backlink_blog_name,
        backlink_writer_name=backlink_writer_name,
        backlink_content_guidelines=backlink_content_guidelines,
        suggested_content=suggested_content,
        change_request=change_request,
    )
    def validator(content: str) -> str:
        url_error = required_url_presence_error(content, money_site_url)
        if url_error:
            return url_error
        return medium_example_mention_error(content, brand=brand, keyword=keyword)

    content = _generate_content_from_prompt(
        provider,
        prompt,
        min_words=validation_min_words ,
        max_words=effective_max_words,
        validator=validator,
        progress_callback=progress_callback,
    )
    return keep_required_url_once(content, money_site_url)


def _effective_medium_max_words(
    website_name: str,
    blog_name: str,
    website_type: str,
    max_words: int | str,
) -> int:
    try:
        cleaned = max(0, int(max_words or 0))
    except (TypeError, ValueError):
        cleaned = 0
    if cleaned:
        return cleaned

    target = f"{website_name or ''} {blog_name or ''} {website_type or ''}".lower()
    if "twitter" in target or "x.com" in target or target.strip() == "x":
        return 40
    if "social_media" in target or "social media" in target:
        return 120
    return 0


def _effective_medium_min_words(min_words: int | str) -> int:
    try:
        return max(0, int(min_words or 0))
    except (TypeError, ValueError):
        return 0
