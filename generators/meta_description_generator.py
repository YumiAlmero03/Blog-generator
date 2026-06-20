import json
import re
from generation_retry_policy import can_accept_close_enough, raise_if_generation_cancelled, wait_before_retry
from prompts import build_backlink_meta_description_prompt, build_meta_description_prompt
from utils import extract_json_string
from logger import logger
from word_bank import find_banned_terms_in_text

MIN_META_DESCRIPTION_CHARACTERS = 120
MAX_META_DESCRIPTION_CHARACTERS = 140
MAX_ATTEMPTS = 5

def _generate_meta_descriptions_from_prompt(
    provider,
    prompt: str,
    target_count: int = 0,
    progress_callback=None,
    forbidden_phrases: list[str] | None = None,
):
    last_failure_detail = ""
    cleaned_forbidden_phrases = _clean_forbidden_phrases(forbidden_phrases or [])

    attempt = 0
    while attempt < MAX_ATTEMPTS:
        raise_if_generation_cancelled(progress_callback)
        attempt += 1
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                "- Your previous response used banned words or phrases, missed the 130-160 character range, or returned too few usable descriptions.\n"
                "- Return fresh meta descriptions that avoid every banned term completely.\n"
                "- Make every meta description between 130 and 160 characters.\n"
                "- Count only the description text, not JSON syntax.\n"
            )
            if cleaned_forbidden_phrases:
                retry_instruction += (
                    "- Do not include these exact phrases in any meta description: "
                    + ", ".join(cleaned_forbidden_phrases)
                    + ".\n"
                )
            if target_count:
                retry_instruction += f"- Return {target_count} usable meta descriptions if possible.\n"

        full_prompt = prompt + retry_instruction
        _publish_progress(progress_callback, full_prompt, kind="prompt")
        raw = provider.generate_json(full_prompt)

        try:
            json_text = extract_json_string(raw)
            data = json.loads(json_text)
            meta_descriptions = data.get("meta_descriptions", [])
            valid_meta_descriptions = []
            close_meta_descriptions = []
            rejected_lengths = []
            rejected_banned_terms = []
            rejected_forbidden_phrases = []

            for item in meta_descriptions:
                if not isinstance(item, dict):
                    continue
                text = (item.get("text", "") or "").strip()
                if not text:
                    continue
                banned_terms = find_banned_terms_in_text(text)
                if banned_terms:
                    rejected_banned_terms.extend(term for term in banned_terms if term not in rejected_banned_terms)
                    continue
                forbidden_matches = _matching_forbidden_phrases(text, cleaned_forbidden_phrases)
                if forbidden_matches:
                    rejected_forbidden_phrases.extend(
                        phrase for phrase in forbidden_matches if phrase not in rejected_forbidden_phrases
                    )
                    continue
                text_length = len(text)
                if not MIN_META_DESCRIPTION_CHARACTERS <= text_length <= MAX_META_DESCRIPTION_CHARACTERS:
                    rejected_lengths.append(text_length)
                    if _is_close_meta_length(text_length):
                        close_meta_descriptions.append(
                            {
                                "text": text,
                                "character_count": text_length,
                            }
                        )
                    continue
                valid_meta_descriptions.append(
                    {
                        "text": text,
                        "character_count": text_length,
                    }
                )

            if valid_meta_descriptions:
                if rejected_banned_terms:
                    _publish_progress(
                        progress_callback,
                        f"Meta attempt {attempt}: ignored descriptions with banned terms ({', '.join(rejected_banned_terms)}).",
                    )
                    logger.warning(
                        "Ignored meta descriptions with banned terms %s on attempt %d",
                        ", ".join(rejected_banned_terms),
                        attempt,
                    )
                if rejected_lengths:
                    _publish_progress(
                        progress_callback,
                        f"Meta attempt {attempt}: ignored descriptions outside 130-160 characters ({', '.join(str(length) for length in rejected_lengths)} chars).",
                    )
                    logger.warning(
                        "Ignored meta descriptions outside %d-%d characters with lengths %s on attempt %d",
                        MIN_META_DESCRIPTION_CHARACTERS,
                        MAX_META_DESCRIPTION_CHARACTERS,
                        ", ".join(str(length) for length in rejected_lengths),
                        attempt,
                    )
                if rejected_forbidden_phrases:
                    _publish_progress(
                        progress_callback,
                        f"Meta attempt {attempt}: ignored descriptions with forbidden phrases ({', '.join(rejected_forbidden_phrases)}).",
                    )
                    logger.warning(
                        "Ignored meta descriptions with forbidden phrases %s on attempt %d",
                        ", ".join(rejected_forbidden_phrases),
                        attempt,
                    )
                return valid_meta_descriptions[:target_count] if target_count else valid_meta_descriptions

            if close_meta_descriptions and can_accept_close_enough(attempt):
                selected = _rank_meta_descriptions(close_meta_descriptions)
                _publish_progress(
                    progress_callback,
                    f"Meta attempt {attempt}: accepting close descriptions after strict retries.",
                )
                logger.warning(
                    "Accepting close meta descriptions after %d attempts with lengths %s",
                    attempt,
                    ", ".join(str(item["character_count"]) for item in selected),
                )
                return selected[:target_count] if target_count else selected

            if rejected_forbidden_phrases:
                last_failure_detail = f"Last meta descriptions included forbidden phrases {', '.join(rejected_forbidden_phrases)}."
                _publish_progress(
                    progress_callback,
                    f"Meta attempt {attempt}: forbidden phrases found ({', '.join(rejected_forbidden_phrases)}). Retrying...",
                )
                logger.warning(
                    "Generated meta descriptions included forbidden phrases %s on attempt %d",
                    ", ".join(rejected_forbidden_phrases),
                    attempt,
                )
                wait_before_retry(attempt, progress_callback, "forbidden phrase match")
                continue
            if rejected_banned_terms:
                last_failure_detail = f"Last meta descriptions used banned terms {', '.join(rejected_banned_terms)}."
                _publish_progress(
                    progress_callback,
                    f"Meta attempt {attempt}: banned terms found ({', '.join(rejected_banned_terms)}). Retrying...",
                )
                logger.warning(
                    "Generated meta descriptions used banned terms %s on attempt %d",
                    ", ".join(rejected_banned_terms),
                    attempt,
                )
                wait_before_retry(attempt, progress_callback, "banned term match")
                continue
            if rejected_lengths:
                last_failure_detail = (
                    f"Last meta descriptions missed {MIN_META_DESCRIPTION_CHARACTERS}-"
                    f"{MAX_META_DESCRIPTION_CHARACTERS} characters with lengths "
                    f"{', '.join(str(length) for length in rejected_lengths)}."
                )
                _publish_progress(
                    progress_callback,
                    f"Meta attempt {attempt}: descriptions missed 130-160 characters ({', '.join(str(length) for length in rejected_lengths)} chars). Retrying...",
                )
                logger.warning(
                    "Generated meta descriptions missed %d-%d characters with lengths %s on attempt %d",
                    MIN_META_DESCRIPTION_CHARACTERS,
                    MAX_META_DESCRIPTION_CHARACTERS,
                    ", ".join(str(length) for length in rejected_lengths),
                    attempt,
                )
                wait_before_retry(attempt, progress_callback, "meta length miss")
                continue
            last_failure_detail = "Last response did not include usable meta descriptions."
            _publish_progress(
                progress_callback,
                f"Meta attempt {attempt}: no usable descriptions returned. Retrying...",
            )
            wait_before_retry(attempt, progress_callback, "empty meta response")
        except Exception as exc:
            logger.exception("generate_meta_descriptions failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

    raise ValueError(
        "Generated meta descriptions could not satisfy banned words and length rules. "
        f"{last_failure_detail}"
    )


def _clean_forbidden_phrases(phrases: list[str]) -> list[str]:
    cleaned = []
    for phrase in phrases:
        value = " ".join(str(phrase or "").split()).strip()
        if value and value.lower() not in [item.lower() for item in cleaned]:
            cleaned.append(value)
    return cleaned


def _matching_forbidden_phrases(text: str, phrases: list[str]) -> list[str]:
    normalized_text = " ".join((text or "").lower().split())
    matches = []
    for phrase in phrases:
        normalized_phrase = " ".join(phrase.lower().split())
        if not normalized_phrase:
            continue
        pattern = r"(?<![a-z0-9])" + re.escape(normalized_phrase) + r"(?![a-z0-9])"
        if re.search(pattern, normalized_text):
            matches.append(phrase)
    return matches


def _is_close_meta_length(length: int) -> bool:
    return 100 <= length <= 160


def _rank_meta_descriptions(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda item: (
            0
            if MIN_META_DESCRIPTION_CHARACTERS <= int(item.get("character_count", 0)) <= MAX_META_DESCRIPTION_CHARACTERS
            else 1,
            abs(130 - int(item.get("character_count", 0))),
        ),
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


def generate_meta_descriptions(
    provider,
    title: str,
    keyword: str = "",
    count: int = 3,
    brand: str = "",
    brand_context: str = "",
    language: str = "English",
    progress_callback=None,
):
    prompt = build_meta_description_prompt(
        title=title,
        keyword=keyword,
        count=count,
        brand=brand,
        brand_context=brand_context,
        language=language,
    )
    return _generate_meta_descriptions_from_prompt(provider, prompt, target_count=count, progress_callback=progress_callback)

def generate_meta_description(
    provider,
    title: str,
    keyword: str = "",
    brand: str = "",
    brand_context: str = "",
    language: str = "English",
    progress_callback=None,
):
    """Legacy function for single meta description"""
    descriptions = generate_meta_descriptions(
        provider,
        title,
        keyword,
        count=1,
        brand=brand,
        brand_context=brand_context,
        language=language,
        progress_callback=progress_callback,
    )
    return descriptions[0]["text"] if descriptions else ""


def generate_backlink_meta_descriptions(
    provider,
    title: str,
    keyword: str = "",
    count: int = 3,
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
    brand_topic_mode: str = "example",
    language: str = "English",
    progress_callback=None,
):
    prompt = build_backlink_meta_description_prompt(
        title=title,
        keyword=keyword,
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
        brand_topic_mode=brand_topic_mode,
        language=language,
    )
    forbidden_phrases = [keyword]
    if (brand_topic_mode or "").strip().lower() != "main":
        forbidden_phrases.append(brand)
    return _generate_meta_descriptions_from_prompt(
        provider,
        prompt,
        target_count=count,
        progress_callback=progress_callback,
        forbidden_phrases=forbidden_phrases,
    )
