import json
from prompts import build_backlink_meta_description_prompt, build_meta_description_prompt
from utils import extract_json_string
from logger import logger
from word_bank import find_banned_terms_in_text

MIN_META_DESCRIPTION_CHARACTERS = 120
MAX_META_DESCRIPTION_CHARACTERS = 140

def _generate_meta_descriptions_from_prompt(provider, prompt: str, target_count: int = 0, progress_callback=None):
    last_failure_detail = ""

    attempt = 0
    while True:
        attempt += 1
        retry_instruction = ""
        if attempt == 1:
            _publish_progress(progress_callback, prompt, kind="prompt")
        if attempt > 1:
            retry_instruction = (
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                "- Your previous response used banned words or phrases, missed the 120-140 character range, or returned too few usable descriptions.\n"
                "- Return fresh meta descriptions that avoid every banned term completely.\n"
                "- Make every meta description between 120 and 140 characters.\n"
                "- Count only the description text, not JSON syntax.\n"
            )
            if target_count:
                retry_instruction += f"- Return {target_count} usable meta descriptions if possible.\n"

        raw = provider.generate_json(prompt + retry_instruction)

        try:
            json_text = extract_json_string(raw)
            data = json.loads(json_text)
            meta_descriptions = data.get("meta_descriptions", [])
            valid_meta_descriptions = []
            rejected_lengths = []
            rejected_banned_terms = []

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
                text_length = len(text)
                if not MIN_META_DESCRIPTION_CHARACTERS <= text_length <= MAX_META_DESCRIPTION_CHARACTERS:
                    rejected_lengths.append(text_length)
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
                        f"Meta attempt {attempt}: ignored descriptions outside 120-140 characters ({', '.join(str(length) for length in rejected_lengths)} chars).",
                    )
                    logger.warning(
                        "Ignored meta descriptions outside %d-%d characters with lengths %s on attempt %d",
                        MIN_META_DESCRIPTION_CHARACTERS,
                        MAX_META_DESCRIPTION_CHARACTERS,
                        ", ".join(str(length) for length in rejected_lengths),
                        attempt,
                    )
                return valid_meta_descriptions[:target_count] if target_count else valid_meta_descriptions

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
                continue
            if rejected_lengths:
                last_failure_detail = (
                    f"Last meta descriptions missed {MIN_META_DESCRIPTION_CHARACTERS}-"
                    f"{MAX_META_DESCRIPTION_CHARACTERS} characters with lengths "
                    f"{', '.join(str(length) for length in rejected_lengths)}."
                )
                _publish_progress(
                    progress_callback,
                    f"Meta attempt {attempt}: descriptions missed 120-140 characters ({', '.join(str(length) for length in rejected_lengths)} chars). Retrying...",
                )
                logger.warning(
                    "Generated meta descriptions missed %d-%d characters with lengths %s on attempt %d",
                    MIN_META_DESCRIPTION_CHARACTERS,
                    MAX_META_DESCRIPTION_CHARACTERS,
                    ", ".join(str(length) for length in rejected_lengths),
                    attempt,
                )
                continue
            last_failure_detail = "Last response did not include usable meta descriptions."
            _publish_progress(
                progress_callback,
                f"Meta attempt {attempt}: no usable descriptions returned. Retrying...",
            )
        except Exception as exc:
            logger.exception("generate_meta_descriptions failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

    raise ValueError(
        "Generated meta descriptions could not satisfy banned words and length rules. "
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


def generate_meta_descriptions(
    provider,
    title: str,
    keyword: str = "",
    count: int = 3,
    brand: str = "",
    brand_context: str = "",
    progress_callback=None,
):
    prompt = build_meta_description_prompt(
        title=title,
        keyword=keyword,
        count=count,
        brand=brand,
        brand_context=brand_context,
    )
    return _generate_meta_descriptions_from_prompt(provider, prompt, target_count=count, progress_callback=progress_callback)

def generate_meta_description(
    provider,
    title: str,
    keyword: str = "",
    brand: str = "",
    brand_context: str = "",
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
    )
    return _generate_meta_descriptions_from_prompt(provider, prompt, target_count=count, progress_callback=progress_callback)
