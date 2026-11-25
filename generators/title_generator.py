import json
from generation_retry_policy import max_generation_attempts, raise_if_generation_cancelled, wait_before_retry
from prompts import build_backlink_title_prompt, build_title_prompt
from utils import extract_json_string
from logger import logger
from word_bank import find_banned_terms_in_text

def _generate_titles_from_prompt(provider, prompt: str, forbidden_phrases: list[str] | None = None, progress_callback=None):
    cleaned_forbidden_phrases = [
        phrase.strip().lower()
        for phrase in (forbidden_phrases or [])
        if phrase and phrase.strip()
    ]
    last_failure_detail = ""

    attempt = 0
    effective_max_attempts = max(1, max_generation_attempts())
    while attempt < effective_max_attempts:
        raise_if_generation_cancelled(progress_callback)
        attempt += 1
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                "- Your previous response used banned words, forbidden phrases, or did not follow the title rules.\n"
                "- Return fresh titles that avoid every banned term completely.\n"
            )
            if cleaned_forbidden_phrases:
                retry_instruction += "- Do not mention these phrases in any title: " + ", ".join(cleaned_forbidden_phrases) + ".\n"

        full_prompt = prompt + retry_instruction
        _publish_progress(progress_callback, full_prompt, kind="prompt")
        raw = provider.generate_json(full_prompt)

        try:
            json_text = extract_json_string(raw)
            data = json.loads(json_text)
            titles = data.get("titles", [])
            valid_titles = []
            rejected_banned_terms = []
            violating_titles = []

            for item in titles:
                if not isinstance(item, str):
                    continue
                cleaned_title = item.strip()
                if not cleaned_title:
                    continue
                item_banned_terms = find_banned_terms_in_text(cleaned_title)
                if item_banned_terms:
                    rejected_banned_terms.extend(
                        term for term in item_banned_terms if term not in rejected_banned_terms
                    )
                    continue
                if cleaned_forbidden_phrases and any(
                    phrase in cleaned_title.lower() for phrase in cleaned_forbidden_phrases
                ):
                    violating_titles.append(cleaned_title)
                    continue
                valid_titles.append(item)

            if valid_titles:
                if rejected_banned_terms:
                    _publish_progress(
                        progress_callback,
                        f"Title attempt {attempt}: ignored titles with banned terms ({', '.join(rejected_banned_terms)}).",
                    )
                    logger.warning(
                        "Ignored titles with banned terms %s on attempt %d",
                        ", ".join(rejected_banned_terms),
                        attempt,
                    )
                if violating_titles:
                    _publish_progress(
                        progress_callback,
                        f"Title attempt {attempt}: ignored titles with forbidden phrases.",
                    )
                    logger.warning(
                        "Ignored titles with forbidden phrases on attempt %d: %s",
                        attempt,
                        "; ".join(violating_titles),
                    )
                return valid_titles

            if rejected_banned_terms:
                last_failure_detail = f"Last titles used banned terms {', '.join(rejected_banned_terms)}."
                _publish_progress(
                    progress_callback,
                    f"Title attempt {attempt}: banned terms found ({', '.join(rejected_banned_terms)}). Retrying...",
                )
                logger.warning(
                    "Generated titles used banned terms %s on attempt %d",
                    ", ".join(rejected_banned_terms),
                    attempt,
                )
                wait_before_retry(attempt, progress_callback, "banned term match")
                continue
            if violating_titles:
                last_failure_detail = "Last titles included forbidden phrases."
                _publish_progress(
                    progress_callback,
                    f"Title attempt {attempt}: forbidden phrase found in title. Retrying...",
                )
                logger.warning(
                    "Generated titles used forbidden phrases on attempt %d: %s",
                    attempt,
                    "; ".join(violating_titles),
                )
                wait_before_retry(attempt, progress_callback, "forbidden phrase match")
                continue
            return titles
        except Exception as exc:
            logger.exception("generate_titles failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

    raise ValueError(
        "Generated titles could not satisfy banned words and title rules. "
        f"{last_failure_detail}"
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


def generate_titles(
    provider,
    keyword: str,
    supporting_keyword: str = "",
    tone: str = "natural",
    count: int = 10,
    brand: str = "",
    brand_context: str = "",
    language: str = "English",
    reference_context: str = "",
    progress_callback=None,
):
    from app.services.web_search_service import append_web_research_context

    cleaned_reference = (reference_context or "").strip()
    prompt = build_title_prompt(
        keyword=keyword,
        supporting_keyword=supporting_keyword,
        tone=tone,
        count=count,
        brand=brand,
        brand_context=brand_context,
        language=language,
        reference_context=cleaned_reference,
    )
    if not cleaned_reference:
        prompt = append_web_research_context(
            prompt,
            " ".join(part for part in [brand, keyword, supporting_keyword] if part).strip(),
            progress_callback=progress_callback,
        )
    return _generate_titles_from_prompt(provider, prompt, progress_callback=progress_callback)


def generate_backlink_titles(
    provider,
    keyword: str,
    supporting_keyword: str = "",
    tone: str = "natural",
    count: int = 10,
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
    keyword_is_anchor_text: bool = False,
    brand_topic_mode: str = "example",
    language: str = "English",
    progress_callback=None,
):
    prompt = build_backlink_title_prompt(
        keyword=keyword,
        supporting_keyword=supporting_keyword,
        tone=tone,
        count=count,
        brand=brand,
        brand_context=brand_context,
        backlink_website_name=backlink_website_name,
        backlink_blog_url=backlink_blog_url,
        backlink_website_type=backlink_website_type,
        backlink_post_type=backlink_post_type,
        backlink_title_max_characters=backlink_title_max_characters,
        backlink_min_words=backlink_min_words,
        backlink_max_characters=backlink_max_characters,
        backlink_tier_level=backlink_tier_level,
        backlink_blog_name=backlink_blog_name,
        backlink_writer_name=backlink_writer_name,
        backlink_content_guidelines=backlink_content_guidelines,
        keyword_is_anchor_text=keyword_is_anchor_text,
        brand_topic_mode=brand_topic_mode,
        language=language,
    )
    forbidden_phrases = [] if (brand_topic_mode or "").strip().lower() == "main" else [brand]
    if keyword_is_anchor_text:
        forbidden_phrases.append(keyword)
    return _generate_titles_from_prompt(provider, prompt, forbidden_phrases=forbidden_phrases, progress_callback=progress_callback)
