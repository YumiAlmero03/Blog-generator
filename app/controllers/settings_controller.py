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
