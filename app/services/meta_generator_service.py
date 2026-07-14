import json

from logger import logger
from prompts.shared import build_language_instruction
from utils import extract_json_string
from word_bank import build_banned_words_prompt_section, find_banned_terms_in_text


DEFAULT_META_OPTION_COUNT = 5
META_DESCRIPTION_MIN_CHARS = 130
META_DESCRIPTION_MAX_CHARS = 150
MAX_META_GENERATOR_ATTEMPTS = 3
DYNAMIC_NAME_PAGE_TYPES = {"category page", "author page"}


def generate_meta_titles_and_descriptions(
    provider,
    keyword: str,
    page_type: str = "Blog",
    brand: str = "",
    brand_context: str = "",
    count: int = DEFAULT_META_OPTION_COUNT,
    language: str = "English",
    progress_callback=None,
) -> dict:
    cleaned_page_type = _clean_text(page_type) or "Blog"
    cleaned_keyword = _clean_text(keyword) or keyword_from_page_type(cleaned_page_type)
    cleaned_brand = _clean_text(brand)
    cleaned_brand_context = _clean_text(brand_context)

    requested_count = max(1, min(10, int(count or DEFAULT_META_OPTION_COUNT)))
    base_prompt = _build_meta_generator_prompt(
        keyword=cleaned_keyword,
        page_type=cleaned_page_type,
        brand=cleaned_brand,
        brand_context=cleaned_brand_context,
        count=requested_count,
        language=language,
    )
    options = []
    last_error = ""
    for attempt in range(1, MAX_META_GENERATOR_ATTEMPTS + 1):
        prompt = base_prompt + _retry_prompt_section(attempt, requested_count)
        _publish_progress(progress_callback, prompt, kind="prompt")
        raw = provider.generate_json(prompt)

        try:
            data = json.loads(extract_json_string(raw))
        except Exception as exc:
            logger.exception("meta generator failed. Raw response: %s", raw)
            raise ValueError("Could not parse generated meta titles and descriptions.") from exc

        options, rejected_descriptions = _normalize_options(
            data.get("options", []),
            limit=requested_count,
            page_type=cleaned_page_type,
        )
        if options:
            break
        if rejected_descriptions:
            last_error = (
                "Generated meta descriptions missed the strict "
                f"{META_DESCRIPTION_MIN_CHARS}-{META_DESCRIPTION_MAX_CHARS} character range."
            )
            _publish_progress(
                progress_callback,
                f"Meta generator attempt {attempt}: rejected descriptions outside "
                f"{META_DESCRIPTION_MIN_CHARS}-{META_DESCRIPTION_MAX_CHARS} characters "
                f"({', '.join(str(length) for length in rejected_descriptions)} chars).",
            )
        else:
            last_error = "The AI did not return usable meta title and description options."

    if not options:
        raise ValueError(last_error or "The AI did not return usable meta title and description options.")

    return {
        "keyword": cleaned_keyword,
        "page_type": cleaned_page_type,
        "brand": cleaned_brand,
        "count": requested_count,
        "language": language,
        "options": options,
    }


def _build_meta_generator_prompt(keyword: str, page_type: str, brand: str, brand_context: str, count: int, language: str) -> str:
    dynamic_name_rules = ""
    if _uses_dynamic_name(page_type):
        dynamic_name_rules = """
- Use the literal placeholder %name% in every meta title and every meta description.
- Treat %name% as the dynamic category or author name. Do not replace it with an example name.
"""
    brand_section = ""
    if brand or brand_context:
        brand_section = f"""
Brand context:
- Brand: {brand or "Not specified"}
- Saved context: {brand_context or "No saved brand context."}

Use the brand context for tone, audience, and positioning. Include the brand name only when it sounds natural and helps the search snippet.
"""
    return f"""
You are an SEO metadata specialist.

Generate {count} meta title and meta description options for this page.

Keyword: {keyword}
Page type: {page_type}
{brand_section}
{build_language_instruction(language)}
{build_banned_words_prompt_section()}

Rules:
- Meta titles must be 45-60 characters when possible.
- Meta descriptions must be strictly {META_DESCRIPTION_MIN_CHARS}-{META_DESCRIPTION_MAX_CHARS} characters.
- Count the characters in each meta description before returning JSON.
- Do not return a meta description shorter than {META_DESCRIPTION_MIN_CHARS} characters or longer than {META_DESCRIPTION_MAX_CHARS} characters.
- Put the keyword naturally in each title and description.
- Match the search intent to the page type.
{dynamic_name_rules.strip()}
- Keep every option distinct.
- Avoid clickbait, exaggerated claims, and filler.
- Write in {language}.
- Return valid JSON only.
- Start with "{{" and end with "}}".

Return JSON only in this format:
{{
  "options": [
    {{
      "title": "Meta title",
      "description": "Meta description"
    }}
  ]
}}
"""


def _retry_prompt_section(attempt: int, count: int) -> str:
    if attempt <= 1:
        return ""
    return f"""

IMPORTANT RETRY REQUIREMENT:
- Your previous response missed the strict {META_DESCRIPTION_MIN_CHARS}-{META_DESCRIPTION_MAX_CHARS} character range.
- Return {count} fresh options if possible.
- Every meta description must be at least {META_DESCRIPTION_MIN_CHARS} characters and at most {META_DESCRIPTION_MAX_CHARS} characters.
- Count only the meta description text, not JSON syntax.
"""


def _normalize_options(items: list, limit: int, page_type: str = "") -> tuple[list[dict], list[int]]:
    options = []
    seen = set()
    needs_dynamic_name = _uses_dynamic_name(page_type)
    rejected_description_lengths = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title", ""))
        description = _clean_text(item.get("description", ""))
        if not title or not description:
            continue
        if needs_dynamic_name and ("%name%" not in title or "%name%" not in description):
            continue
        description_length = len(description)
        if not META_DESCRIPTION_MIN_CHARS <= description_length <= META_DESCRIPTION_MAX_CHARS:
            rejected_description_lengths.append(description_length)
            continue
        key = (title.casefold(), description.casefold())
        if key in seen:
            continue
        seen.add(key)
        options.append(
            {
                "title": title,
                "title_character_count": len(title),
                "description": description,
                "description_character_count": description_length,
                "banned_terms": sorted(set(find_banned_terms_in_text(f"{title} {description}"))),
            }
        )
        if len(options) >= limit:
            break
    return options, rejected_description_lengths


def keyword_from_page_type(page_type: str) -> str:
    cleaned = _clean_text(page_type) or "Blog"
    return cleaned.lower()


def _uses_dynamic_name(page_type: str) -> bool:
    return _clean_text(page_type).casefold() in DYNAMIC_NAME_PAGE_TYPES


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
        logger.exception("meta generator progress callback failed")
