from database import get_setting

BLOG_MIN_WORDS_KEY = "blog_min_words"
BLOG_MAX_WORDS_KEY = "blog_max_words"
PAGE_MIN_WORDS_KEY = "page_min_words"
PAGE_MAX_WORDS_KEY = "page_max_words"

DEFAULT_BLOG_MIN_WORDS = 1300
DEFAULT_BLOG_MAX_WORDS = 1400
DEFAULT_PAGE_MIN_WORDS = 900
DEFAULT_PAGE_MAX_WORDS = 1200


def get_blog_word_limits() -> tuple[int, int]:
    return _get_word_limits(
        BLOG_MIN_WORDS_KEY,
        BLOG_MAX_WORDS_KEY,
        DEFAULT_BLOG_MIN_WORDS,
        DEFAULT_BLOG_MAX_WORDS,
    )


def get_page_word_limits() -> tuple[int, int]:
    return _get_word_limits(
        PAGE_MIN_WORDS_KEY,
        PAGE_MAX_WORDS_KEY,
        DEFAULT_PAGE_MIN_WORDS,
        DEFAULT_PAGE_MAX_WORDS,
    )


def normalize_word_limits(min_words: str | int, max_words: str | int, default_min: int, default_max: int) -> tuple[int, int]:
    cleaned_min = _positive_int(min_words, default_min)
    cleaned_max = _positive_int(max_words, default_max)
    if cleaned_max < cleaned_min:
        cleaned_max = cleaned_min
    return cleaned_min, cleaned_max


def _get_word_limits(min_key: str, max_key: str, default_min: int, default_max: int) -> tuple[int, int]:
    return normalize_word_limits(
        get_setting(min_key, str(default_min)),
        get_setting(max_key, str(default_max)),
        default_min,
        default_max,
    )


def _positive_int(value: str | int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)
