import json
import re
from generation_retry_policy import max_generation_attempts, publish_generation_draft, raise_if_generation_cancelled, wait_before_retry
from prompts import build_backlink_content_prompt, build_content_prompt, build_scoped_content_revision_prompt
from utils import extract_json_string
from logger import logger
from word_bank import find_banned_terms_in_text
from content_repetition import repeated_content_issue

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


def generate_ai_content_tags(
    provider,
    title: str = "",
    keyword: str = "",
    supporting_keyword: str = "",
    brand: str = "",
    content: str = "",
    minimum: int = 10,
    language: str = "English",
    progress_callback=None,
) -> list[str]:
    fallback = suggest_content_tags(
        title=title,
        keyword=keyword,
        supporting_keyword=supporting_keyword,
        brand=brand,
        content=content,
        minimum=minimum,
    )
    prompt = f"""
Create clean publishing tags for this generated blog.

Return valid JSON only.

Selected title: {title}
Primary keyword or anchor: {keyword}
Supporting keyword: {supporting_keyword}
Brand: {brand}
Required language: {language}

Content:
{(content or '')[:6000]}

Rules:
- Use the selected title as the main context.
- Return {minimum} to 12 short tags.
- Write tags in {language}.
- Keep tags natural, useful for publishing, and lower case when possible.
- Avoid duplicate tags, banned terms, promotional hype, and generic filler.
- Do not include explanations before or after the JSON.

Return JSON only in this format:
{{
  "tags": ["tag one", "tag two"]
}}
"""
    _publish_progress(progress_callback, prompt, kind="prompt")
    raw = provider.generate_json(prompt)
    try:
        data = json.loads(extract_json_string(raw))
        tags = data.get("tags", [])
        if isinstance(tags, str):
            tags = [tag.strip() for tag in tags.split(",")]
        cleaned = []
        for tag in tags:
            value = re.sub(r"\s+", " ", str(tag).strip().lower())
            if value and value not in cleaned:
                cleaned.append(value)
        return cleaned[:12] or fallback
    except Exception:
        logger.exception("generate_ai_content_tags failed. Raw response: %s", raw)
        return fallback


def generate_blog_visual_ideas(
    provider,
    title: str,
    keyword: str = "",
    brand: str = "",
    context: str = "",
    count: int = 2,
    language: str = "English",
    progress_callback=None,
) -> list[str]:
    prompt = f"""
You are creating practical image directions for a generated blog article.

Return valid JSON only.

Selected title: {title}
Topic keyword: {keyword}
Brand: {brand}
Required language: {language}
Context:
{context}

Rules:
- Generate exactly {count} distinct visual or image descriptions.
- Write visual descriptions in {language}.
- Use the selected title as the anchor for both visual ideas.
- Make each idea useful for a designer, AI image tool, or publisher selecting a header image.
- Keep them neutral and editorial, not promotional.
- Do not include text overlays, logos, watermarks, brand marks, or UI screenshots unless the article specifically requires them.
- Avoid gambling, betting, casino, jackpot, wagering, sportsbook, lottery, poker, roulette, or bonus-focused imagery.
- Keep each visual idea to 1-2 sentences.
- No explanations before or after the JSON.

Return JSON only in this format:
{{
  "visuals": ["First visual idea.", "Second visual idea."]
}}
"""
    _publish_progress(progress_callback, prompt, kind="prompt")
    raw = provider.generate_json(prompt)
    try:
        data = json.loads(extract_json_string(raw))
        visuals = data.get("visuals", [])
        if isinstance(visuals, str):
            visuals = [visuals]
        cleaned = [str(item).strip() for item in visuals if str(item).strip()]
        return cleaned[:count]
    except Exception as exc:
        logger.exception("generate_blog_visual_ideas failed. Raw response: %s", raw)
        raise ValueError("Could not parse JSON from model output.") from exc


def generate_backlink_visual_idea(
    provider,
    title: str,
    keyword: str = "",
    brand: str = "",
    backlink_website_name: str = "",
    backlink_website_type: str = "",
    backlink_blog_name: str = "",
    backlink_content_guidelines: str = "",
    language: str = "English",
    progress_callback=None,
) -> str:
    return "\n\n".join(
        generate_blog_visual_ideas(
            provider,
            title=title,
            keyword=keyword,
            brand=brand,
            context=(
                f"Publishing medium: {backlink_website_name}\n"
                f"Publication/account: {backlink_blog_name}\n"
                f"Medium type: {backlink_website_type}\n"
                f"Medium rules: {backlink_content_guidelines}"
            ),
            count=2,
            language=language,
            progress_callback=progress_callback,
        )
    )


def parse_generated_content(raw: str) -> tuple[str, int]:
    json_text = extract_json_string(raw)
    data = json.loads(json_text)
    content = data.get("content", "")
    word_count = count_html_words(content)
    return content, word_count


def _generate_content_from_prompt(
    provider,
    prompt: str,
    min_words: int = MIN_BLOG_WORDS,
    max_words: int = 0,
    validator=None,
    progress_callback=None,
    target_min_words: int | None = None,
    max_attempts: int = 0,
    allow_best_effort: bool = False,
    retry_parse_errors: bool = False,
):
    last_word_count = 0
    last_validation_error = ""
    last_length_error = ""
    last_failure_detail = ""
    best_effort_content = ""
    best_effort_word_count = 0

    attempt = 0
    effective_max_attempts = max_attempts or max_generation_attempts()
    while attempt < effective_max_attempts:
        raise_if_generation_cancelled(progress_callback)
        attempt += 1
        retry_instruction = ""
        if attempt > 1:
            retry_min_words = target_min_words or min_words
            if min_words:
                retry_instruction = (
                    f"\n\nIMPORTANT RETRY REQUIREMENT:\n"
                    f"- Your previous response was too short.\n"
                    f"- Return COMPLETE content in the required selected format only inside JSON.\n"
                    f"- The article should target at least {retry_min_words} words.\n"
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
                        f"- Do not cut useful context below the validation minimum word count of {min_words} words.\n"
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
                wait_before_retry(attempt, progress_callback, "banned term match")
                continue

            repetition_issue = repeated_content_issue(content)
            if repetition_issue:
                last_validation_error = (
                    f"{repetition_issue}. Rewrite the repeated section with fresh information, "
                    "different sentence structure, and no duplicated paragraphs."
                )
                last_failure_detail = f"Content repeated text on attempt {attempt}: {repetition_issue}"
                _publish_progress(
                    progress_callback,
                    f"Content attempt {attempt}: {repetition_issue} Retrying...",
                )
                logger.warning(
                    "Content repeated text on attempt %d: %s",
                    attempt,
                    repetition_issue,
                )
                wait_before_retry(attempt, progress_callback, "repeated content")
                continue

            if word_count > best_effort_word_count:
                best_effort_content = content
                best_effort_word_count = word_count
                publish_generation_draft(
                    progress_callback,
                    content,
                    f"Showing a draft while retrying for the checklist ({word_count} words).",
                )

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
                wait_before_retry(attempt, progress_callback, "short content")
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
                wait_before_retry(attempt, progress_callback, "long content")
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
                    wait_before_retry(attempt, progress_callback, "content validation")
                    continue

            logger.info(
                "Content generated successfully with %d words on attempt %d",
                word_count,
                attempt,
            )
            return content
        except Exception as exc:
            last_failure_detail = f"Could not parse JSON from model output on attempt {attempt}."
            logger.exception("generate_content failed on attempt %d. Raw response: %s", attempt, raw)
            if retry_parse_errors:
                _publish_progress(
                    progress_callback,
                    f"Content attempt {attempt}: model returned no usable content. Retrying...",
                )
                wait_before_retry(attempt, progress_callback, "parse failure")
                continue
            raise ValueError("Could not parse JSON from model output.") from exc

    if allow_best_effort and best_effort_content:
        _publish_progress(
            progress_callback,
            f"Using best available content after {attempt} attempts ({best_effort_word_count} words).",
        )
        logger.warning(
            "Using best-effort content with %d words after %d attempts. Last failure: %s",
            best_effort_word_count,
            attempt,
            last_failure_detail,
        )
        return best_effort_content

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
    language: str = "English",
    progress_callback=None,
):
    from app.services.content_format_service import markdown_to_output

    prompt_min_words = _prompt_min_words_with_buffer(min_words)
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
        min_words=prompt_min_words,
        max_words=max_words,
        language=language,
    )
    markdown_content = _generate_content_from_prompt(
        provider,
        prompt,
        min_words=min_words,
        max_words=max_words,
        target_min_words=prompt_min_words,
        progress_callback=progress_callback,
    )
    return markdown_to_output(markdown_content, "html")


def revise_existing_content(
    provider,
    title: str,
    existing_content: str,
    change_request: str,
    scope: str = "full",
    output_format: str = "html",
    keyword: str = "",
    brand: str = "",
    required_url: str = "",
    required_anchor_text: str = "",
    language: str = "English",
    progress_callback=None,
):
    prompt = build_scoped_content_revision_prompt(
        title=title,
        existing_content=existing_content,
        change_request=change_request,
        scope=scope,
        output_format=output_format,
        keyword=keyword,
        brand=brand,
        required_url=required_url,
        required_anchor_text=required_anchor_text,
        language=language,
    )

    def validator(content: str) -> str:
        url_error = required_url_presence_error(content, required_url)
        if url_error:
            return url_error
        return required_anchor_text_presence_error(content, required_anchor_text)

    revised_content = _generate_content_from_prompt(
        provider,
        prompt,
        min_words=0,
        max_words=0,
        validator=validator if required_url or required_anchor_text else None,
        progress_callback=progress_callback,
    )
    return keep_required_url_once(revised_content, required_url)


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


def required_anchor_text_presence_error(content: str, required_anchor_text: str) -> str:
    cleaned_anchor = (required_anchor_text or "").strip()
    if not cleaned_anchor:
        return ""

    visible_text = re.sub(r"<[^>]+>", " ", content or "")
    visible_text = re.sub(r"\s+", " ", visible_text).strip()
    if cleaned_anchor.lower() not in visible_text.lower():
        return "The required anchor text must be included exactly as provided for the required link."
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


def medium_brand_usage_error(content: str, brand: str = "", keyword: str = "", brand_topic_mode: str = "example") -> str:
    if (brand_topic_mode or "").strip().lower() == "main":
        return ""
    return medium_example_mention_error(content, brand=brand, keyword=keyword)


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
    selected_meta_description: str = "",
    required_anchor_text: str = "",
    brand_topic_mode: str = "example",
    language: str = "English",
    progress_callback=None,
):
    from app.services.content_format_service import markdown_to_output

    effective_max_words = _effective_medium_max_words(
        backlink_website_name,
        backlink_blog_name,
        backlink_website_type,
        backlink_max_characters,
    )
    effective_min_words = _effective_medium_min_words(backlink_min_words)
    validation_min_words = effective_min_words
    prompt_min_words = _prompt_min_words_with_buffer(validation_min_words)
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
        backlink_min_words=prompt_min_words,
        backlink_max_characters=effective_max_words,
        backlink_tier_level=backlink_tier_level,
        backlink_blog_name=backlink_blog_name,
        backlink_writer_name=backlink_writer_name,
        backlink_content_guidelines=backlink_content_guidelines,
        suggested_content=suggested_content,
        change_request=change_request,
        selected_meta_description=selected_meta_description,
        required_anchor_text=required_anchor_text,
        brand_topic_mode=brand_topic_mode,
        language=language,
    )
    def validator(content: str) -> str:
        url_error = required_url_presence_error(content, money_site_url)
        if url_error:
            return url_error
        anchor_error = required_anchor_text_presence_error(content, required_anchor_text)
        if anchor_error:
            return anchor_error
        return medium_brand_usage_error(content, brand=brand, keyword=keyword, brand_topic_mode=brand_topic_mode)

    markdown_content = _generate_content_from_prompt(
        provider,
        prompt,
        min_words=validation_min_words ,
        max_words=effective_max_words,
        validator=validator,
        target_min_words=prompt_min_words,
        progress_callback=progress_callback,
    )
    markdown_content = keep_required_url_once(markdown_content, money_site_url)
    return markdown_to_output(markdown_content, backlink_post_type)


def generate_tier2_content(
    provider,
    title: str,
    anchor_text: str = "",
    link: str = "",
    tone: str = "natural",
    backlink_website_name: str = "",
    backlink_blog_url: str = "",
    backlink_website_type: str = "blog",
    backlink_post_type: str = "html",
    backlink_title_max_characters: int | str = 0,
    backlink_min_words: int | str = 0,
    backlink_max_characters: int | str = 0,
    backlink_tier_level: str = "Tier 2",
    backlink_blog_name: str = "",
    backlink_writer_name: str = "",
    backlink_content_guidelines: str = "",
    suggested_content: str = "",
    change_request: str = "",
    language: str = "English",
    progress_callback=None,
):
    from app.services.content_format_service import markdown_to_output

    effective_max_words = _effective_medium_max_words(
        backlink_website_name,
        backlink_blog_name,
        backlink_website_type,
        backlink_max_characters,
    )
    effective_min_words = _effective_medium_min_words(backlink_min_words)
    prompt_min_words = _prompt_min_words_with_buffer(effective_min_words)
    prompt = build_backlink_content_prompt(
        title=title,
        keyword=anchor_text,
        tone=tone,
        money_site_url=link,
        brand="",
        brand_context="",
        backlink_website_name=backlink_website_name,
        backlink_blog_url=backlink_blog_url,
        backlink_website_type=backlink_website_type,
        backlink_post_type=backlink_post_type,
        backlink_title_max_characters=backlink_title_max_characters,
        backlink_min_words=prompt_min_words,
        backlink_max_characters=effective_max_words,
        backlink_tier_level=backlink_tier_level or "Tier 2",
        backlink_blog_name=backlink_blog_name,
        backlink_writer_name=backlink_writer_name,
        backlink_content_guidelines=backlink_content_guidelines,
        suggested_content=suggested_content,
        change_request=change_request,
        required_anchor_text=anchor_text,
        required_link_label="Tier 2",
        language=language,
    )

    def validator(content: str) -> str:
        url_error = required_url_presence_error(content, link)
        if url_error:
            return url_error
        return required_anchor_text_presence_error(content, anchor_text)

    markdown_content = _generate_content_from_prompt(
        provider,
        prompt,
        min_words=effective_min_words,
        max_words=effective_max_words,
        validator=validator,
        target_min_words=prompt_min_words,
        progress_callback=progress_callback,
    )
    markdown_content = keep_required_url_once(markdown_content, link)
    return markdown_to_output(markdown_content, backlink_post_type)


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


def _prompt_min_words_with_buffer(min_words: int | str, buffer_words: int = 100) -> int:
    try:
        cleaned = max(0, int(min_words or 0))
    except (TypeError, ValueError):
        cleaned = 0
    if not cleaned:
        return 0
    return cleaned + max(0, int(buffer_words or 0))
