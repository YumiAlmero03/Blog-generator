from flask import render_template, request

from database import get_setting, set_setting

from app.controllers.helpers import base_template_context
from app.services.word_limit_settings import (
    BLOG_MAX_WORDS_KEY,
    BLOG_MIN_WORDS_KEY,
    DEFAULT_BLOG_MAX_WORDS,
    DEFAULT_BLOG_MIN_WORDS,
    DEFAULT_PAGE_MAX_WORDS,
    DEFAULT_PAGE_MIN_WORDS,
    PAGE_MAX_WORDS_KEY,
    PAGE_MIN_WORDS_KEY,
    get_blog_word_limits,
    get_page_word_limits,
    normalize_word_limits,
)


def settings():
    blog_min_words, blog_max_words = get_blog_word_limits()
    page_min_words, page_max_words = get_page_word_limits()
    state = {
        "money_site": get_setting("money_site", ""),
        "blog_min_words": blog_min_words,
        "blog_max_words": blog_max_words,
        "page_min_words": page_min_words,
        "page_max_words": page_max_words,
        "success": None,
        "error": None,
    }

    if request.method == "POST":
        state["money_site"] = request.form.get("money_site", "").strip()
        state["blog_min_words"], state["blog_max_words"] = normalize_word_limits(
            request.form.get("blog_min_words", ""),
            request.form.get("blog_max_words", ""),
            DEFAULT_BLOG_MIN_WORDS,
            DEFAULT_BLOG_MAX_WORDS,
        )
        state["page_min_words"], state["page_max_words"] = normalize_word_limits(
            request.form.get("page_min_words", ""),
            request.form.get("page_max_words", ""),
            DEFAULT_PAGE_MIN_WORDS,
            DEFAULT_PAGE_MAX_WORDS,
        )
        set_setting("money_site", state["money_site"])
        set_setting(BLOG_MIN_WORDS_KEY, str(state["blog_min_words"]))
        set_setting(BLOG_MAX_WORDS_KEY, str(state["blog_max_words"]))
        set_setting(PAGE_MIN_WORDS_KEY, str(state["page_min_words"]))
        set_setting(PAGE_MAX_WORDS_KEY, str(state["page_max_words"]))
        state["success"] = "Settings saved."

    return render_template("settings.html", **base_template_context(), **state)


def banned_words():
    state = {
        "custom_banned_words": "\n".join(_load_banned_words_file_terms()),
        "default_banned_words": _load_banned_words_file_terms(),
        "success": None,
        "error": None,
    }

    if request.method == "POST":
        raw_terms = request.form.get("custom_banned_words", "")
        saved_terms = _write_banned_words_file(raw_terms.splitlines())
        state["custom_banned_words"] = "\n".join(saved_terms)
        state["default_banned_words"] = saved_terms
        state["success"] = "Banned words saved to banned_words.txt."

    return render_template("banned_words.html", **base_template_context(), **state)


def _load_banned_words_file_terms() -> list[str]:
    from word_bank import WORD_BANK_FILE

    if not WORD_BANK_FILE.exists():
        return []

    terms = []
    for raw_line in WORD_BANK_FILE.read_text(encoding="utf-8").splitlines():
        cleaned = raw_line.strip()
        if cleaned and not cleaned.startswith("#"):
            terms.append(cleaned)
    return terms


def _write_banned_words_file(raw_terms: list[str]) -> list[str]:
    from word_bank import WORD_BANK_FILE

    cleaned_terms = []
    seen = set()
    for raw_term in raw_terms:
        cleaned = " ".join((raw_term or "").strip().split())
        normalized = cleaned.lower()
        if not normalized or cleaned.startswith("#") or normalized in seen:
            continue
        seen.add(normalized)
        cleaned_terms.append(cleaned)

    file_content = "\n".join(
        [
            "# Add one banned word or phrase per line.",
            "# Lines starting with # are treated as comments.",
            "",
            *cleaned_terms,
        ]
    )
    WORD_BANK_FILE.write_text(file_content.rstrip() + "\n", encoding="utf-8")
    return cleaned_terms
