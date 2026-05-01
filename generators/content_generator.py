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


def _generate_content_from_prompt(provider, prompt: str, min_words: int = MIN_BLOG_WORDS, validator=None):
    last_error = None
    last_word_count = 0
    last_validation_error = ""

    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        retry_instruction = ""
        if attempt > 1:
            if min_words:
                retry_instruction = (
                    f"\n\nIMPORTANT RETRY REQUIREMENT:\n"
                    f"- Your previous response was too short.\n"
                    f"- Return COMPLETE valid HTML content only inside JSON.\n"
                    f"- The article must be at least {min_words} words.\n"
                    f"- Expand each section with more detail, examples, and explanation.\n"
                )
            else:
                retry_instruction = (
                    "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                    "- Return COMPLETE valid HTML content only inside JSON.\n"
                    "- Respect the selected medium's shorter content limit.\n"
                    "- Keep the output concise, complete, and suitable for the medium.\n"
                )
            if last_validation_error:
                retry_instruction += (
                    "\nIMPORTANT RETRY REQUIREMENT:\n"
                    f"- {last_validation_error}\n"
                    "- Return corrected valid HTML content only inside JSON.\n"
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

            if min_words and word_count < min_words:
                logger.warning(
                    "Content word count is %d (minimum: %d) on attempt %d/%d. Raw response length: %d chars",
                    word_count,
                    min_words,
                    attempt,
                    MAX_GENERATION_ATTEMPTS,
                    len(raw),
                )
                continue

            if validator:
                validation_error = validator(content)
                if validation_error:
                    last_validation_error = validation_error
                    logger.warning(
                        "Content validation failed on attempt %d/%d: %s",
                        attempt,
                        MAX_GENERATION_ATTEMPTS,
                        validation_error,
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
    change_request: str = "",
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
    )
    return _generate_content_from_prompt(provider, prompt)


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


def required_url_in_first_paragraph_error(content: str, required_url: str) -> str:
    cleaned_url = (required_url or "").strip()
    if not cleaned_url:
        return ""

    first_paragraph = re.search(r"<p\b[^>]*>.*?</p>", content or "", flags=re.IGNORECASE | re.DOTALL)
    if not first_paragraph:
        return "The generated content must start with a first <p> paragraph that contains the required brand link."
    if cleaned_url not in first_paragraph.group(0):
        return "The required brand URL must be inserted inside the first paragraph and must not be placed later in the article."
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
    backlink_title_max_characters: int | str = 0,
    backlink_max_characters: int | str = 0,
    backlink_tier_level: str = "",
    backlink_blog_name: str = "",
    backlink_writer_name: str = "",
    backlink_content_guidelines: str = "",
    change_request: str = "",
):
    effective_max_characters = _effective_medium_max_characters(
        backlink_website_name,
        backlink_blog_name,
        backlink_website_type,
        backlink_max_characters,
    )
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
        backlink_title_max_characters=backlink_title_max_characters,
        backlink_max_characters=effective_max_characters,
        backlink_tier_level=backlink_tier_level,
        backlink_blog_name=backlink_blog_name,
        backlink_writer_name=backlink_writer_name,
        backlink_content_guidelines=backlink_content_guidelines,
        change_request=change_request,
    )
    validator = None
    if (money_site_url or "").strip():
        validator = lambda content: required_url_in_first_paragraph_error(content, money_site_url)
    content = _generate_content_from_prompt(
        provider,
        prompt,
        min_words=0 if effective_max_characters else MIN_BLOG_WORDS,
        validator=validator,
    )
    return keep_required_url_once(content, money_site_url)


def _effective_medium_max_characters(
    website_name: str,
    blog_name: str,
    website_type: str,
    max_characters: int | str,
) -> int:
    try:
        cleaned = max(0, int(max_characters or 0))
    except (TypeError, ValueError):
        cleaned = 0
    if cleaned:
        return cleaned

    target = f"{website_name or ''} {blog_name or ''} {website_type or ''}".lower()
    if "twitter" in target or "x.com" in target or target.strip() == "x":
        return 280
    if "social_media" in target or "social media" in target:
        return 700
    return 0
