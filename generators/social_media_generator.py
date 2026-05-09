import json

from logger import logger
from prompts import build_social_media_post_prompt
from utils import extract_json_string
from word_bank import find_banned_terms_in_text


MAX_SOCIAL_POST_CHARACTERS = 220
GAMBLING_RELATED_TERMS = (
    "slot",
    "slots",
    "casino",
    "casinos",
    "gambling",
    "gamble",
    "bet",
    "bets",
    "betting",
    "wager",
    "wagering",
    "jackpot",
    "poker",
    "roulette",
    "blackjack",
    "sportsbook",
    "lottery",
    "bingo",
)


def generate_social_media_post(
    provider,
    focus_word: str,
    brand_name: str,
    social_type: str,
    brand_context: str = "",
    progress_callback=None,
) -> dict:
    prompt = build_social_media_post_prompt(
        focus_word=focus_word,
        brand_name=brand_name,
        social_type=social_type,
        brand_context=brand_context,
    )
    attempt = 0
    while True:
        attempt += 1
        retry_instruction = ""
        if attempt > 1:
            retry_instruction = (
                "\n\nIMPORTANT RETRY REQUIREMENT:\n"
                f"- The post_content must be {MAX_SOCIAL_POST_CHARACTERS} characters or fewer.\n"
                "- Avoid every term in the forbidden word bank from the original prompt.\n"
                "- Do not use slot, casino, gambling, betting, jackpot, wager, poker, roulette, sportsbook, lottery, or related terms anywhere.\n"
                "- Return fresh valid JSON only.\n"
            )

        full_prompt = prompt + retry_instruction
        _publish_progress(progress_callback, full_prompt, kind="prompt")
        raw = provider.generate_json(full_prompt)
        try:
            data = json.loads(extract_json_string(raw))
            post_content = str(data.get("post_content", "")).strip()
            image_description = str(data.get("image_description", "")).strip()
            tags = data.get("tags", [])
            if isinstance(tags, str):
                tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
            tags = [str(tag).strip() for tag in tags if str(tag).strip()]

            if len(post_content) > MAX_SOCIAL_POST_CHARACTERS:
                _publish_progress(
                    progress_callback,
                    f"Social attempt {attempt}: post has {len(post_content)} characters, maximum is {MAX_SOCIAL_POST_CHARACTERS}. Retrying...",
                )
                logger.warning(
                    "Social media post exceeded %d characters on attempt %d: %d",
                    MAX_SOCIAL_POST_CHARACTERS,
                    attempt,
                    len(post_content),
                )
                continue

            restricted_terms = _find_gambling_related_terms(
                " ".join([post_content, image_description, " ".join(tags)])
            )
            banned_terms = find_banned_terms_in_text(
                " ".join([post_content, image_description, " ".join(tags)])
            )
            if restricted_terms:
                _publish_progress(
                    progress_callback,
                    f"Social attempt {attempt}: restricted terms found ({', '.join(restricted_terms)}). Retrying...",
                )
                logger.warning(
                    "Social media post used restricted terms %s on attempt %d",
                    ", ".join(restricted_terms),
                    attempt,
                )
                continue
            if banned_terms:
                _publish_progress(
                    progress_callback,
                    f"Social attempt {attempt}: banned terms found ({', '.join(banned_terms)}). Retrying...",
                )
                logger.warning(
                    "Social media post used banned terms %s on attempt %d",
                    ", ".join(banned_terms),
                    attempt,
                )
                continue

            return {
                "post_content": post_content,
                "image_description": image_description,
                "tags": tags[:8],
                "character_count": len(post_content),
            }
        except Exception as exc:
            logger.exception("generate_social_media_post failed on attempt %d. Raw response: %s", attempt, raw)
            raise ValueError("Could not parse JSON from model output.") from exc

    raise ValueError("Generated social media post could not satisfy the 220 character limit.")


def _publish_progress(progress_callback, message: str, kind: str = "status") -> None:
    if not progress_callback:
        return
    try:
        progress_callback(message, kind=kind)
    except TypeError:
        progress_callback(message)
    except Exception:
        logger.exception("generation progress callback failed")


def _find_gambling_related_terms(text: str) -> list[str]:
    lowered = f" {text or ''} ".lower()
    found = []
    for term in GAMBLING_RELATED_TERMS:
        if f" {term} " in lowered or f"#{term}" in lowered:
            found.append(term)
    return found
