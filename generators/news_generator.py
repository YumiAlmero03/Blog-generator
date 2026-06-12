import json
import re

from app.services.content_format_service import markdown_to_output
from generators.content_generator import _generate_content_from_prompt, count_html_words, suggest_content_tags
from generators.meta_description_generator import _generate_meta_descriptions_from_prompt
from generators.title_generator import _generate_titles_from_prompt
from logger import logger
from prompts.news import (
    build_news_content_prompt,
    build_news_meta_description_prompt,
    build_news_tags_prompt,
    build_news_title_prompt,
    build_news_visual_prompt,
    current_news_date,
)
from utils import extract_json_string


OLD_NEWS_YEARS = ["2020", "2021", "2022", "2023", "2024", "2025"]


def generate_news_titles(
    provider,
    keyword: str,
    target_audience: str = "",
    target_country: str = "Worldwide",
    reference_context: str = "",
    tone: str = "news",
    count: int = 10,
    brand: str = "",
    brand_context: str = "",
    current_date: str = "",
    progress_callback=None,
) -> list[str]:
    prompt = build_news_title_prompt(
        keyword=keyword,
        target_audience=target_audience,
        target_country=target_country,
        reference_context=reference_context,
        tone=tone,
        count=count,
        brand=brand,
        brand_context=brand_context,
        current_date=current_date or current_news_date(),
    )
    return _generate_titles_from_prompt(
        provider,
        prompt,
        forbidden_phrases=OLD_NEWS_YEARS,
        progress_callback=progress_callback,
    )


def generate_news_meta_descriptions(
    provider,
    title: str,
    keyword: str = "",
    target_audience: str = "",
    target_country: str = "Worldwide",
    reference_context: str = "",
    count: int = 5,
    brand: str = "",
    brand_context: str = "",
    current_date: str = "",
    progress_callback=None,
) -> list[dict]:
    prompt = build_news_meta_description_prompt(
        title=title,
        keyword=keyword,
        target_audience=target_audience,
        target_country=target_country,
        reference_context=reference_context,
        count=count,
        brand=brand,
        brand_context=brand_context,
        current_date=current_date or current_news_date(),
    )
    return _generate_meta_descriptions_from_prompt(
        provider,
        prompt,
        target_count=count,
        progress_callback=progress_callback,
        forbidden_phrases=OLD_NEWS_YEARS,
    )


def generate_news_visual_ideas(
    provider,
    title: str,
    keyword: str = "",
    target_audience: str = "",
    target_country: str = "Worldwide",
    reference_context: str = "",
    count: int = 3,
    brand: str = "",
    brand_context: str = "",
    current_date: str = "",
    progress_callback=None,
) -> list[str]:
    prompt = build_news_visual_prompt(
        title=title,
        keyword=keyword,
        target_audience=target_audience,
        target_country=target_country,
        reference_context=reference_context,
        count=count,
        brand=brand,
        brand_context=brand_context,
        current_date=current_date or current_news_date(),
    )
    attempt = 0
    while True:
        attempt += 1
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = "\n\nIMPORTANT RETRY REQUIREMENT:\n- Do not include any 2020, 2021, 2022, 2023, 2024, or 2025 references.\n"
        _publish_progress(progress_callback, prompt + retry_instruction, kind="prompt")
        raw = provider.generate_json(prompt + retry_instruction)
        try:
            data = json.loads(extract_json_string(raw))
            visuals = data.get("visuals", [])
            if isinstance(visuals, str):
                visuals = [visuals]
            cleaned = [str(item).strip() for item in visuals if str(item).strip()]
            combined = "\n".join(cleaned)
            if _contains_old_news_year(combined):
                _publish_progress(
                    progress_callback,
                    f"Visual attempt {attempt}: old-news year reference found. Retrying...",
                )
                continue
            return cleaned[:count]
        except Exception as exc:
            logger.exception("generate_news_visual_ideas failed. Raw response: %s", raw)
            raise ValueError("Could not parse JSON from model output.") from exc


def generate_news_content(
    provider,
    title: str,
    keyword: str = "",
    target_audience: str = "",
    target_country: str = "Worldwide",
    reference_context: str = "",
    tone: str = "news",
    brand: str = "",
    brand_context: str = "",
    min_words: int = 800,
    max_words: int = 1400,
    current_date: str = "",
    progress_callback=None,
) -> str:
    prompt = build_news_content_prompt(
        title=title,
        keyword=keyword,
        target_audience=target_audience,
        target_country=target_country,
        reference_context=reference_context,
        tone=tone,
        brand=brand,
        brand_context=brand_context,
        min_words=min_words,
        max_words=max_words,
        current_date=current_date or current_news_date(),
    )
    def validator(content: str) -> str:
        for year in OLD_NEWS_YEARS:
            if re.search(rf"(?<!\d){year}(?!\d)", content or ""):
                return f"Do not include old-news year references like {year}; keep the article focused on current 2026 events."
        return ""

    markdown_content = _generate_content_from_prompt(
        provider,
        prompt,
        min_words=min_words,
        max_words=max_words,
        validator=validator,
        progress_callback=progress_callback,
    )
    return markdown_to_output(markdown_content, "html")


def generate_news_tags(
    provider,
    title: str,
    keyword: str = "",
    target_audience: str = "",
    target_country: str = "Worldwide",
    reference_context: str = "",
    brand: str = "",
    content: str = "",
    minimum: int = 10,
    current_date: str = "",
    progress_callback=None,
) -> list[str]:
    fallback = suggest_content_tags(
        title=title,
        keyword=keyword,
        brand=brand,
        content=content,
        minimum=minimum,
    )
    prompt = build_news_tags_prompt(
        title=title,
        keyword=keyword,
        target_audience=target_audience,
        target_country=target_country,
        reference_context=reference_context,
        brand=brand,
        content=content,
        minimum=minimum,
        current_date=current_date or current_news_date(),
    )
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
        cleaned = [tag for tag in cleaned if not _contains_old_news_year(tag)]
        return cleaned[:12] or fallback
    except Exception:
        logger.exception("generate_news_tags failed. Raw response: %s", raw)
        return fallback


def _publish_progress(progress_callback, message: str, kind: str = "status") -> None:
    if not progress_callback:
        return
    try:
        progress_callback(message, kind=kind)
    except TypeError:
        progress_callback(message)
    except Exception:
        logger.exception("generation progress callback failed")


def _contains_old_news_year(text: str) -> bool:
    return any(re.search(rf"(?<!\d){year}(?!\d)", text or "") for year in OLD_NEWS_YEARS)
