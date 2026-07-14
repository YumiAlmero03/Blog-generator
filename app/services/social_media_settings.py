from database import get_setting
from generators.social_media_generator import get_social_post_character_limit


SOCIAL_MEDIA_MAX_CHARACTERS_KEY = "social_media_max_characters"
DEFAULT_SOCIAL_MEDIA_MAX_CHARACTERS = 1000


def get_social_media_max_characters() -> int:
    raw = get_setting(SOCIAL_MEDIA_MAX_CHARACTERS_KEY, str(DEFAULT_SOCIAL_MEDIA_MAX_CHARACTERS))
    return normalize_social_media_max_characters(raw)


def normalize_social_media_max_characters(value: str | int) -> int:
    try:
        return max(80, min(6000, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_SOCIAL_MEDIA_MAX_CHARACTERS


def social_post_character_limit_for_platform(social_type: str) -> int:
    return min(get_social_media_max_characters(), get_social_post_character_limit(social_type))
