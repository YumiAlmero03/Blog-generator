import json

from logger import logger
from prompts.shared import build_language_instruction
from utils import extract_json_string
from word_bank import build_banned_words_prompt_section, find_banned_terms_in_text


DEFAULT_META_OPTION_COUNT = 5
META_DESCRIPTION_MIN_CHARS = 130
META_DESCRIPTION_MAX_CHARS = 150
DYNAMIC_NAME_PAGE_TYPES = {"category page", "author page"}


def generate_meta_titles_and_descriptions(
    provider,
    keyword: str,
    page_type: str = "Blog",
    count: int = DEFAULT_META_OPTION_COUNT,
    language: str = "English",
    progress_callback=None,
) -> dict:
    cleaned_page_type = _clean_text(page_type) or "Blog"
    cleaned_keyword = _clean_text(keyword) or keyword_from_page_type(cleaned_page_type)

    requested_count = max(1, min(10, int(count or DEFAULT_META_OPTION_COUNT)))
    prompt = _build_meta_generator_prompt(
        keyword=cleaned_keyword,
        page_type=cleaned_page_type,
        count=requested_count,
        language=language,
    )
    _publish_progress(progress_callback, prompt, kind="prompt")
    raw = provider.generate_json(prompt)

    try:
        data = json.loads(extract_json_string(raw))
    except Exception as exc:
        logger.exception("meta generator failed. Raw response: %s", raw)
        raise ValueError("Could not parse generated meta titles and descriptions.") from exc

    options = _normalize_options(data.get("options", []), limit=requested_count, page_type=cleaned_page_type)
    if not options:
        raise ValueError("The AI did not return usable meta title and description options.")

    return {
        "keyword": cleaned_keyword,
        "page_type": cleaned_page_type,
        "count": requested_count,
        "language": language,
        "options": options,
    }


def _build_meta_generator_prompt(keyword: str, page_type: str, count: int, language: str) -> str:
    dynamic_name_rules = ""
    if _uses_dynamic_name(page_type):
        dynamic_name_rules = """
- Use the literal placeholder %name% in every meta title and every meta description.
- Treat %name% as the dynamic category or author name. Do not replace it with an example name.
"""
    return f"""
You are an SEO metadata specialist.

Generate {count} meta title and meta description options for this page.

Keyword: {keyword}
Page type: {page_type}
{build_language_instruction(language)}
{build_banned_words_prompt_section()}

Rules:
- Meta titles must be 45-60 characters when possible.
- Meta descriptions must be {META_DESCRIPTION_MIN_CHARS}-{META_DESCRIPTION_MAX_CHARS} characters when possible.
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


def _normalize_options(items: list, limit: int, page_type: str = "") -> list[dict]:
    options = []
    seen = set()
    needs_dynamic_name = _uses_dynamic_name(page_type)
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title", ""))
        description = _clean_text(item.get("description", ""))
        if not title or not description:
            continue
        if needs_dynamic_name and ("%name%" not in title or "%name%" not in description):
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
                "description_character_count": len(description),
                "banned_terms": sorted(set(find_banned_terms_in_text(f"{title} {description}"))),
            }
        )
        if len(options) >= limit:
            break
    return options


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
