import json

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


def generate_blog_rework(
    provider,
    source_url: str,
    brand: str = "",
    tone: str = "natural",
    language: str = "English",
    min_words: int = 1300,
    max_words: int = 1400,
    brand_context: str = "",
    progress_callback=None,
) -> dict:
    cleaned_url = (source_url or "").strip()
    if not cleaned_url:
        raise ValueError("Enter a source link to rework.")

    _publish_progress(progress_callback, "Fetching source article...")
    source = fetch_url_text(cleaned_url)
    source_title = source.get("title", "")
    source_text = (source.get("text", "") or "")[:MAX_SOURCE_CHARS]

    _publish_progress(progress_callback, "Generating title and keywords...")
    brief = _generate_rework_brief(
        provider,
        source_url=cleaned_url,
        source_title=source_title,
        source_text=source_text,
        brand=brand,
        tone=tone,
        language=language,
        progress_callback=progress_callback,
    )
    title = brief["title"]
    keyword = brief["keyword"]
    supporting_keyword = brief.get("supporting_keyword", "")

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
        links=[{"type": "reference", "text": source_title or "source article", "url": cleaned_url}],
        brand=brand,
        brand_context=brand_context,
        change_request=_rework_change_request(source_title, source_text),
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
    brand: str = "",
    tone: str = "natural",
    language: str = "English",
    progress_callback=None,
) -> dict:
    prompt = f"""
You are an SEO blog rework strategist.

Read the source article context and create a fresh blog direction. Do not copy the source title.

Source URL: {source_url}
Source title: {source_title}
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
- Rework the angle so it is original and not a copied headline.
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


def _rework_change_request(source_title: str, source_text: str) -> str:
    return f"""
Rework this source article into a fresh, original blog post. Use the source only as context.

Source title: {source_title}

Source excerpt:
{source_text}

Rework rules:
- Do not copy the source wording, sentence order, paragraph order, or headline.
- Preserve useful facts and topic intent, but explain them in a new structure.
- Add fresh examples, clearer explanations, and practical sections.
- Do not mention that this is a rework.
- Do not cite or link the source unless it naturally belongs as a reference link.
"""


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _publish_progress(progress_callback, message: str, kind: str = "status") -> None:
    if not progress_callback:
        return
    try:
        progress_callback(message, kind=kind)
    except TypeError:
        progress_callback(message)
    except Exception:
        logger.exception("blog rework progress callback failed")
