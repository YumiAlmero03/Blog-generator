import json
from html.parser import HTMLParser

from app.services.reference_link_service import fetch_url_text
from generators.content_generator import (
    generate_ai_content_tags,
    generate_blog_visual_ideas,
    generate_content,
)
from generators.meta_description_generator import generate_meta_descriptions
from logger import logger
from prompts.shared import build_language_instruction
from utils import extract_json_string
from word_bank import build_banned_words_prompt_section


MAX_SOURCE_CHARS = 12000


class _SourceContentParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if (tag or "").lower() in {"script", "style", "noscript", "svg", "canvas"}:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if (tag or "").lower() in {"script", "style", "noscript", "svg", "canvas"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        text = _clean_text(data)
        if text and not self._skip_depth:
            self.parts.append(text)


def generate_blog_rework(
    provider,
    source_url: str,
    source_content: str = "",
    content_type: str = "blog",
    manual_supporting_keywords: str = "",
    old_brand: str = "",
    brand: str = "",
    tone: str = "natural",
    language: str = "English",
    min_words: int = 1300,
    max_words: int = 1400,
    brand_context: str = "",
    progress_callback=None,
) -> dict:
    cleaned_url = (source_url or "").strip()
    cleaned_source_content = _source_content_to_text(source_content)
    cleaned_content_type = _normalize_content_type(content_type)
    cleaned_manual_supporting_keywords = _clean_text(manual_supporting_keywords)
    if not cleaned_url and not cleaned_source_content:
        raise ValueError("Enter a source link or paste source content to rework.")

    if cleaned_url:
        _publish_progress(progress_callback, "Fetching source article...")
        source = fetch_url_text(cleaned_url)
        source_title = source.get("title", "")
        source_text = (source.get("text", "") or "")[:MAX_SOURCE_CHARS]
        source_label = cleaned_url
    else:
        _publish_progress(progress_callback, "Using pasted source content...")
        source_title = "Pasted source article"
        source_text = cleaned_source_content[:MAX_SOURCE_CHARS]
        source_label = "Pasted source content"

    _publish_progress(progress_callback, "Generating title and keywords...")
    brief = _generate_rework_brief(
        provider,
        source_url=source_label,
        source_title=source_title,
        source_text=source_text,
        content_type=cleaned_content_type,
        old_brand=old_brand,
        brand=brand,
        tone=tone,
        language=language,
        progress_callback=progress_callback,
    )
    title = brief["title"]
    keyword = brief["keyword"]
    supporting_keyword = _merge_supporting_keywords(brief.get("supporting_keyword", ""), cleaned_manual_supporting_keywords)

    _publish_progress(progress_callback, "Generating meta descriptions...")
    meta_descriptions = generate_meta_descriptions(
        provider,
        title=title,
        keyword=keyword,
        count=5,
        brand=brand,
        brand_context=brand_context,
        language=language,
        progress_callback=progress_callback,
    )
    meta_description = meta_descriptions[0].get("text", "") if meta_descriptions else ""

    _publish_progress(progress_callback, "Generating visual image ideas...")
    visual = "\n\n".join(
        generate_blog_visual_ideas(
            provider,
            title=title,
            keyword=keyword,
            brand=brand,
            context=brand_context,
            count=2,
            language=language,
            progress_callback=progress_callback,
        )
    ).strip()

    _publish_progress(progress_callback, "Reworking source article content...")
    content = generate_content(
        provider,
        title=title,
        keyword=keyword,
        supporting_keyword=supporting_keyword,
        tone=tone,
        links=_source_links(cleaned_url, source_title),
        brand=brand,
        brand_context=brand_context,
        change_request=_rework_change_request(
            source_title,
            source_text,
            content_type=cleaned_content_type,
            manual_supporting_keywords=cleaned_manual_supporting_keywords,
            old_brand=old_brand,
            new_brand=brand,
        ),
        min_words=min_words,
        max_words=max_words,
        language=language,
        progress_callback=progress_callback,
    )

    _publish_progress(progress_callback, "Generating tags...")
    tags = generate_ai_content_tags(
        provider,
        title=title,
        keyword=keyword,
        supporting_keyword=supporting_keyword,
        brand=brand,
        content=content,
        minimum=10,
        language=language,
        progress_callback=progress_callback,
    )

    return {
        "source_url": cleaned_url,
        "source_content": source_content if not cleaned_url else "",
        "content_type": cleaned_content_type,
        "manual_supporting_keywords": cleaned_manual_supporting_keywords,
        "source_title": source_title,
        "title": title,
        "keyword": keyword,
        "supporting_keyword": supporting_keyword,
        "meta_descriptions": meta_descriptions,
        "meta_description": meta_description,
        "visual": visual,
        "content": content,
        "tag_suggestions": tags,
    }


def _generate_rework_brief(
    provider,
    source_url: str,
    source_title: str,
    source_text: str,
    content_type: str = "blog",
    manual_supporting_keywords: str = "",
    old_brand: str = "",
    brand: str = "",
    tone: str = "natural",
    language: str = "English",
    progress_callback=None,
) -> dict:
    cleaned_content_type = _normalize_content_type(content_type)
    content_type_label = "WordPress page" if cleaned_content_type == "page" else "blog post"
    prompt = f"""
You are an SEO {content_type_label} rework strategist.

Read the source article context and create a fresh {content_type_label} direction. Do not copy the source title.

Source URL: {source_url}
Source title: {source_title}
Output type: {content_type_label}
Old brand to replace: {old_brand}
Brand: {brand}
Tone: {tone}
{build_language_instruction(language)}
{build_banned_words_prompt_section()}

Source article excerpt:
{source_text}

Rules:
- Create one fresh SEO-friendly title, 45-65 characters when possible.
- Create one main keyword and one supporting keyword.
- Keep the title and keywords aligned with the source topic.
- Rework the angle so it is original and suitable for a {content_type_label}.
- If old brand and brand are both provided, replace old brand references with the brand in the title and keyword strategy.
- Write in {language}.
- Return valid JSON only.
- Start with "{{" and end with "}}".

Return JSON only in this format:
{{
  "title": "Fresh title",
  "keyword": "main keyword",
  "supporting_keyword": "supporting keyword"
}}
"""
    _publish_progress(progress_callback, prompt, kind="prompt")
    raw = provider.generate_json(prompt)
    try:
        data = json.loads(extract_json_string(raw))
    except Exception as exc:
        logger.exception("blog rework brief failed. Raw response: %s", raw)
        raise ValueError("Could not parse blog rework title and keyword output.") from exc

    title = _clean_text(data.get("title", ""))
    keyword = _clean_text(data.get("keyword", ""))
    supporting_keyword = _clean_text(data.get("supporting_keyword", ""))
    if not title or not keyword:
        raise ValueError("Blog rework needs a generated title and keyword.")
    return {
        "title": title,
        "keyword": keyword,
        "supporting_keyword": supporting_keyword,
    }


def _rework_change_request(
    source_title: str,
    source_text: str,
    content_type: str = "blog",
    manual_supporting_keywords: str = "",
    old_brand: str = "",
    new_brand: str = "",
) -> str:
    cleaned_content_type = _normalize_content_type(content_type)
    content_type_label = "WordPress page" if cleaned_content_type == "page" else "blog post"
    manual_keyword_rule = _manual_supporting_keyword_rule(manual_supporting_keywords)
    brand_replacement_rule = _brand_replacement_rule(old_brand, new_brand)
    return f"""
Rework this source article into a fresh, original {content_type_label}. Use the source only as context.

Source title: {source_title}

Source excerpt:
{source_text}

Rework rules:
- Do not copy the source wording, sentence order, paragraph order, or headline.
- Preserve useful facts and topic intent, but explain them in a new structure.
- Add fresh examples, clearer explanations, and practical sections.
- Match the selected output type: {content_type_label}.
- Do not mention that this is a rework.
- Do not cite or link the source unless it naturally belongs as a reference link.
{manual_keyword_rule}
{brand_replacement_rule}
"""


def _brand_replacement_rule(old_brand: str, new_brand: str) -> str:
    cleaned_old = _clean_text(old_brand)
    cleaned_new = _clean_text(new_brand)
    if not cleaned_old or not cleaned_new:
        return ""
    if cleaned_old.casefold() == cleaned_new.casefold():
        return ""
    return (
        f"- Replace every reference to {cleaned_old} with {cleaned_new}. "
        f"Do not keep {cleaned_old} as the article brand, sponsor, product, or example brand."
    )


def _manual_supporting_keyword_rule(value: str) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        return ""
    return (
        f"- Include these user-provided supporting keywords only where natural: {cleaned}. "
        "Use each one no more than once or twice in the content."
    )


def _merge_supporting_keywords(generated_keyword: str, manual_keywords: str) -> str:
    keywords = []
    seen = set()
    for raw_value in (generated_keyword, manual_keywords):
        for item in _split_keyword_items(raw_value):
            normalized = item.casefold()
            if normalized and normalized not in seen:
                seen.add(normalized)
                keywords.append(item)
    return ", ".join(keywords)


def _split_keyword_items(value: str) -> list[str]:
    items = []
    for line in str(value or "").replace(";", ",").splitlines():
        for part in line.split(","):
            cleaned = _clean_text(part)
            if cleaned:
                items.append(cleaned)
    return items


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _source_content_to_text(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    parser = _SourceContentParser()
    parser.feed(cleaned)
    text = _clean_text(" ".join(parser.parts))
    if text:
        return text
    return _clean_text(cleaned)


def _source_links(source_url: str, source_title: str) -> list[dict]:
    cleaned_url = (source_url or "").strip()
    if not cleaned_url:
        return []
    return [{"type": "reference", "text": source_title or "source article", "url": cleaned_url}]


def _normalize_content_type(value: str) -> str:
    cleaned = (value or "blog").strip().lower()
    return cleaned if cleaned in {"blog", "page"} else "blog"


def _publish_progress(progress_callback, message: str, kind: str = "status") -> None:
    if not progress_callback:
        return
    try:
        progress_callback(message, kind=kind)
    except TypeError:
        progress_callback(message)
    except Exception:
        logger.exception("blog rework progress callback failed")
