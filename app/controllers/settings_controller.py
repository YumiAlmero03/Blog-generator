from flask import redirect, render_template, request, url_for

from database import delete_find_replace_rule, get_find_replace_rule, get_setting, list_find_replace_rules, save_find_replace_rule, set_setting

from app.controllers.helpers import base_template_context
from app.services.locale_settings import (
    DEFAULT_COUNTRY_TARGET_KEY,
    DEFAULT_LANGUAGE_KEY,
    country_options,
    get_default_country_target,
    get_default_language,
    language_options,
    normalize_country_target,
    normalize_language,
)
from app.services.indexnow_service import DEFAULT_INDEXNOW_ENDPOINT
from app.services.ollama_web_search_service import (
    OLLAMA_API_KEY_SETTING,
    OLLAMA_WEB_SEARCH_ENABLED_SETTING,
    OLLAMA_WEB_SEARCH_MAX_RESULTS_SETTING,
    get_ollama_api_key,
    get_ollama_web_search_enabled,
    get_ollama_web_search_max_results,
)
from app.services.social_media_settings import (
    DEFAULT_SOCIAL_MEDIA_MAX_CHARACTERS,
    SOCIAL_MEDIA_MAX_CHARACTERS_KEY,
    get_social_media_max_characters,
    normalize_social_media_max_characters,
)
from app.services.social_publish_service import (
    DEFAULT_FACEBOOK_GRAPH_VERSION,
    FACEBOOK_GRAPH_VERSION_KEY,
    get_facebook_graph_api_version,
)
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
from app.services.website_planner_service import (
    WEBSITE_PLANNER_MAIN_PAGES_KEY,
    WEBSITE_PLANNER_TRUST_PAGES_KEY,
    get_main_pages_setting,
    get_trust_pages_setting,
)


def settings():
    blog_min_words, blog_max_words = get_blog_word_limits()
    page_min_words, page_max_words = get_page_word_limits()
    state = {
        "money_site": get_setting("money_site", ""),
        "indexnow_key": get_setting("indexnow_key", ""),
        "indexnow_key_location": get_setting("indexnow_key_location", ""),
        "indexnow_endpoint": get_setting("indexnow_endpoint", DEFAULT_INDEXNOW_ENDPOINT),
        "google_service_account_json": get_setting("google_service_account_json", ""),
        "google_oauth_access_token": get_setting("google_oauth_access_token", ""),
        "ollama_api_key": get_ollama_api_key(),
        "ollama_web_search_enabled": get_ollama_web_search_enabled(),
        "ollama_web_search_max_results": get_ollama_web_search_max_results(),
        "social_media_max_characters": get_social_media_max_characters(),
        "facebook_graph_api_version": get_facebook_graph_api_version(),
        "default_country_target": get_default_country_target(),
        "default_language": get_default_language(),
        "country_options": country_options(get_default_country_target()),
        "language_options": language_options(get_default_language()),
        "blog_min_words": blog_min_words,
        "blog_max_words": blog_max_words,
        "page_min_words": page_min_words,
        "page_max_words": page_max_words,
        "website_planner_main_pages": get_main_pages_setting(),
        "website_planner_trust_pages": get_trust_pages_setting(),
        "success": None,
        "error": None,
    }

    if request.method == "POST":
        state["money_site"] = request.form.get("money_site", "").strip()
        state["indexnow_key"] = request.form.get("indexnow_key", "").strip()
        state["indexnow_key_location"] = request.form.get("indexnow_key_location", "").strip()
        state["indexnow_endpoint"] = request.form.get("indexnow_endpoint", DEFAULT_INDEXNOW_ENDPOINT).strip() or DEFAULT_INDEXNOW_ENDPOINT
        state["google_service_account_json"] = request.form.get("google_service_account_json", "").strip()
        state["google_oauth_access_token"] = request.form.get("google_oauth_access_token", "").strip()
        state["ollama_api_key"] = request.form.get("ollama_api_key", "").strip()
        state["ollama_web_search_enabled"] = request.form.get("ollama_web_search_enabled") == "1"
        state["ollama_web_search_max_results"] = _normalize_ollama_max_results(
            request.form.get("ollama_web_search_max_results", "")
        )
        state["social_media_max_characters"] = normalize_social_media_max_characters(
            request.form.get("social_media_max_characters", DEFAULT_SOCIAL_MEDIA_MAX_CHARACTERS)
        )
        state["facebook_graph_api_version"] = request.form.get("facebook_graph_api_version", DEFAULT_FACEBOOK_GRAPH_VERSION).strip() or DEFAULT_FACEBOOK_GRAPH_VERSION
        state["website_planner_main_pages"] = request.form.get("website_planner_main_pages", "").strip()
        state["website_planner_trust_pages"] = request.form.get("website_planner_trust_pages", "").strip()
        state["default_country_target"] = normalize_country_target(request.form.get("default_country_target", "Worldwide"))
        state["default_language"] = normalize_language(request.form.get("default_language", "English"))
        state["country_options"] = country_options(state["default_country_target"])
        state["language_options"] = language_options(state["default_language"])
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
        set_setting("indexnow_key", state["indexnow_key"])
        set_setting("indexnow_key_location", state["indexnow_key_location"])
        set_setting("indexnow_endpoint", state["indexnow_endpoint"])
        set_setting("google_service_account_json", state["google_service_account_json"])
        set_setting("google_oauth_access_token", state["google_oauth_access_token"])
        set_setting(OLLAMA_API_KEY_SETTING, state["ollama_api_key"])
        set_setting(OLLAMA_WEB_SEARCH_ENABLED_SETTING, "true" if state["ollama_web_search_enabled"] else "false")
        set_setting(OLLAMA_WEB_SEARCH_MAX_RESULTS_SETTING, str(state["ollama_web_search_max_results"]))
        set_setting(SOCIAL_MEDIA_MAX_CHARACTERS_KEY, str(state["social_media_max_characters"]))
        set_setting(FACEBOOK_GRAPH_VERSION_KEY, state["facebook_graph_api_version"])
        set_setting(DEFAULT_COUNTRY_TARGET_KEY, state["default_country_target"])
        set_setting(DEFAULT_LANGUAGE_KEY, state["default_language"])
        set_setting(BLOG_MIN_WORDS_KEY, str(state["blog_min_words"]))
        set_setting(BLOG_MAX_WORDS_KEY, str(state["blog_max_words"]))
        set_setting(PAGE_MIN_WORDS_KEY, str(state["page_min_words"]))
        set_setting(PAGE_MAX_WORDS_KEY, str(state["page_max_words"]))
        set_setting(WEBSITE_PLANNER_MAIN_PAGES_KEY, state["website_planner_main_pages"])
        set_setting(WEBSITE_PLANNER_TRUST_PAGES_KEY, state["website_planner_trust_pages"])
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


def find_replace_settings():
    editing_rule = None
    edit_id = _parse_int(request.args.get("edit", ""))
    if edit_id:
        editing_rule = get_find_replace_rule(edit_id)

    state = {
        "rules": list_find_replace_rules(),
        "editing_rule": editing_rule,
        "find_text": editing_rule["find_text"] if editing_rule else "",
        "replace_text": editing_rule["replace_text"] if editing_rule else "",
        "notes": editing_rule["notes"] if editing_rule else "",
        "is_active": bool(editing_rule["is_active"]) if editing_rule else True,
        "success": None,
        "error": None,
    }

    if request.method == "POST":
        action = request.form.get("action", "save")
        rule_id = _parse_int(request.form.get("rule_id", ""))

        if action == "delete" and rule_id:
            delete_find_replace_rule(rule_id)
            return redirect(url_for("web.find_replace_settings"))

        state["find_text"] = request.form.get("find_text", "").strip()
        state["replace_text"] = request.form.get("replace_text", "").strip()
        state["notes"] = request.form.get("notes", "").strip()
        state["is_active"] = request.form.get("is_active") == "1"

        try:
            saved_id = save_find_replace_rule(
                state["find_text"],
                state["replace_text"],
                notes=state["notes"],
                is_active=state["is_active"],
                rule_id=rule_id,
            )
            state["success"] = "Find and replace rule saved."
            state["editing_rule"] = get_find_replace_rule(saved_id)
            state["rules"] = list_find_replace_rules()
        except ValueError as exc:
            state["error"] = str(exc)

    return render_template("find_replace_settings.html", **base_template_context(), **state)


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


def _normalize_ollama_max_results(value: str) -> int:
    try:
        return max(1, min(10, int(value)))
    except (TypeError, ValueError):
        return get_ollama_web_search_max_results()


def _parse_int(value: str) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
