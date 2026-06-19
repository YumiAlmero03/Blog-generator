from database import get_setting


DEFAULT_COUNTRY_TARGET_KEY = "default_country_target"
DEFAULT_LANGUAGE_KEY = "default_language"

COUNTRY_OPTIONS = (
    "Worldwide",
    "Philippines",
)

LANGUAGE_OPTIONS = (
    "English",
    "Taglish",
    "Tagalog",
)


def get_default_country_target() -> str:
    return normalize_country_target(get_setting(DEFAULT_COUNTRY_TARGET_KEY, "Worldwide"))


def get_default_language() -> str:
    return normalize_language(get_setting(DEFAULT_LANGUAGE_KEY, "English"))


def normalize_country_target(value: str) -> str:
    cleaned = " ".join(str(value or "Worldwide").split()).strip() or "Worldwide"
    options_by_lower = {item.lower(): item for item in COUNTRY_OPTIONS}
    return options_by_lower.get(cleaned.lower(), cleaned)


def normalize_language(value: str) -> str:
    cleaned = " ".join(str(value or "English").split()).strip() or "English"
    options_by_lower = {item.lower(): item for item in LANGUAGE_OPTIONS}
    return options_by_lower.get(cleaned.lower(), cleaned)


def country_options(selected: str | None = None) -> list[str]:
    return _options_with_selected(COUNTRY_OPTIONS, selected)


def language_options(selected: str | None = None) -> list[str]:
    return _options_with_selected(LANGUAGE_OPTIONS, selected)


def _options_with_selected(options: tuple[str, ...], selected: str | None) -> list[str]:
    values = list(options)
    cleaned = " ".join(str(selected or "").split()).strip()
    if cleaned and cleaned.lower() not in {item.lower() for item in values}:
        values.append(cleaned)
    return values
