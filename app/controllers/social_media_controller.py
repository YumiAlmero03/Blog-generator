import json
import re
from html.parser import HTMLParser

from flask import render_template, request

from database import (
    delete_social_profile,
    get_backlink,
    get_generation_history_item,
    get_brand_context,
    list_backlinks,
    list_checklist_items,
    list_brand_names,
    list_social_profiles,
    record_generation,
    get_social_profile,
    save_social_profile,
)
from generators.content_generator import count_html_words
from generators.social_media_generator import generate_neutral_blog_article, generate_social_media_post
from logger import logger

from app.controllers.helpers import base_template_context
from app.services.content_quality_service import analyze_generated_content
from app.services.generation_status_service import clear_generation_status, publish_generation_draft, publish_generation_prompt, publish_generation_status
from app.services.generation_log_service import append_generation_log, generation_log_json, parse_generation_log
from app.services.locale_settings import get_default_language, language_options, normalize_language
from app.services.ollama_web_search_service import build_web_research_context
from app.services.provider_service import generation_error_message, get_provider
from app.services.social_media_settings import social_post_character_limit_for_platform
from app.services.social_publish_service import publish_facebook_page_post


SOCIAL_PLATFORM_OPTIONS = (
    ("facebook", "Facebook"),
    ("instagram", "Instagram"),
    ("linkedin", "LinkedIn"),
    ("telegram", "Telegram"),
    ("twitter", "Twitter / X"),
    ("tiktok", "TikTok"),
    ("youtube", "YouTube"),
    ("pinterest", "Pinterest"),
    ("threads", "Threads"),
    ("reddit", "Reddit"),
    ("other", "Other"),
)


def social_scheduler():
    state = _default_social_scheduler_state()
    edit_id = request.args.get("edit", "").strip()
    if request.method == "GET" and edit_id.isdigit():
        _populate_social_profile_for_edit(state, int(edit_id))

    if request.method == "POST":
        action = request.form.get("action", "save_profile").strip()
        if action == "delete_profile":
            _handle_delete_social_profile(state)
        elif action == "create_post":
            _handle_create_social_post(state)
        else:
            _handle_save_social_profile(state)

    profiles = list_social_profiles()
    total_daily_target = sum(int(profile.get("posts_per_day", 0) or 0) for profile in profiles if profile.get("is_active", 1))
    return render_template(
        "social_scheduler.html",
        **base_template_context(),
        **state,
        profiles=profiles,
        brand_names=list_brand_names(),
        platform_options=SOCIAL_PLATFORM_OPTIONS,
        platform_labels=dict(SOCIAL_PLATFORM_OPTIONS),
        masked_secret=_masked_secret,
        total_daily_target=total_daily_target,
        active_profile_count=sum(1 for profile in profiles if profile.get("is_active", 1)),
    )


def generated_social_post():
    state = _default_generated_social_post_state()
    profile_id = request.args.get("profile_id", "").strip()
    if request.method == "GET" and profile_id.isdigit():
        state["social_profile_id"] = profile_id

    if request.method == "POST":
        _hydrate_generated_social_post_state(state)
        action = request.form.get("action", "generate_social_post").strip()
        if action == "confirm_social_post":
            _handle_confirm_generated_social_post(state)
        else:
            _handle_generate_social_post_page(state)

    state["profiles"] = list_social_profiles()
    state["platform_labels"] = dict(SOCIAL_PLATFORM_OPTIONS)
    state["generation_log_json"] = generation_log_json(state.get("generation_log", []))
    return render_template("generated_social_post.html", **base_template_context(), **state)


def _default_generated_social_post_state() -> dict:
    return {
        "social_profile_id": "",
        "post_keyword": "",
        "post_link": "",
        "generated_content": "",
        "image_description": "",
        "tags": [],
        "tags_text": "",
        "character_count": 0,
        "character_limit": 0,
        "history_id": "",
        "platform": "",
        "account_name": "",
        "web_search_query": "",
        "web_search_used": False,
        "generation_log": [],
        "generation_log_json": "[]",
        "profiles": [],
        "platform_labels": dict(SOCIAL_PLATFORM_OPTIONS),
        "success": None,
        "error": None,
    }


def _hydrate_generated_social_post_state(state: dict) -> None:
    state["social_profile_id"] = request.form.get("social_profile_id", "").strip()
    state["post_keyword"] = request.form.get("post_keyword", "").strip()
    state["post_link"] = request.form.get("post_link", "").strip()
    state["generated_content"] = request.form.get("generated_content", "").strip()
    state["image_description"] = request.form.get("image_description", "").strip()
    state["tags_text"] = request.form.get("tags_text", "").strip()
    state["tags"] = _split_tags(state["tags_text"])
    state["character_count"] = len(state["generated_content"])
    state["character_limit"] = _int_or_zero(request.form.get("character_limit", "0"))
    state["history_id"] = request.form.get("history_id", "").strip()
    state["platform"] = request.form.get("platform", "").strip()
    state["account_name"] = request.form.get("account_name", "").strip()
    state["web_search_query"] = request.form.get("web_search_query", "").strip()
    state["web_search_used"] = request.form.get("web_search_used") == "1"
    state["generation_log"] = parse_generation_log(request.form.get("generation_log_json", ""))
    state["generation_log_json"] = generation_log_json(state["generation_log"])


def _handle_generate_social_post_page(state: dict) -> None:
    profile = _selected_social_profile(state)
    if not profile:
        state["error"] = "Choose a social media account."
        return

    search_query = state["post_link"] or state["post_keyword"]
    if not search_query:
        state["error"] = "Add a link or keyword for the social post."
        return

    try:
        provider = get_provider()
        social_type = profile.get("social_type", "")
        state["platform"] = _platform_label(social_type)
        state["account_name"] = profile.get("account_name", "")
        state["character_limit"] = social_post_character_limit_for_platform(social_type)
        state["web_search_query"] = search_query
        progress = _social_post_progress_callback(request.form.get("generation_status_token", ""), state["generation_log"])
        progress("Generation started.")
        research_context = build_web_research_context(search_query, progress_callback=progress)
        result = generate_social_media_post(
            provider,
            focus_word=state["post_keyword"] or state["post_link"],
            brand_name=profile.get("brand_name", ""),
            social_type=social_type,
            brand_context=get_brand_context(profile.get("brand_name", "")),
            reference_link=state["post_link"],
            research_context=research_context,
            max_characters=state["character_limit"],
            progress_callback=progress,
        )
        state["generated_content"] = _apply_matchup_reaction_lines(
            result.get("post_content", ""),
            state["post_keyword"],
            state["character_limit"],
        )
        state["image_description"] = result.get("image_description", "")
        state["tags"] = result.get("tags", [])
        state["tags_text"] = ", ".join(state["tags"])
        state["character_count"] = len(state["generated_content"])
        state["character_limit"] = result.get("character_limit", state["character_limit"])
        state["web_search_used"] = bool(research_context)
        if _matchup_teams(state["post_keyword"]):
            append_generation_log(state["generation_log"], "status", "Added matchup reaction lines for the vs keyword.")
        state["history_id"] = str(_record_social_post_generation(state, profile, confirmed=False))
        progress("Generation complete. Review and confirm before posting.")
        clear_generation_status(request.form.get("generation_status_token", ""))
        state["success"] = "Social post generated. Review it before confirming."
    except Exception as exc:
        logger.exception("generated social post action failed")
        append_generation_log(state["generation_log"], "error", str(exc) or "Generation failed.")
        state["error"] = generation_error_message(
            "Could not generate the social post. Check logs/app.log for details.",
            exc,
        )


def _handle_confirm_generated_social_post(state: dict) -> None:
    profile = _selected_social_profile(state)
    if not profile:
        state["error"] = "Choose a social media account."
        return
    if not state["generated_content"]:
        state["error"] = "Generate a social post before confirming."
        return

    state["character_count"] = len(state["generated_content"])
    if state["character_limit"] and state["character_count"] > state["character_limit"]:
        state["error"] = f"Post is {state['character_count']} characters, above the {state['character_limit']} character limit."
        return

    state["platform"] = _platform_label(profile.get("social_type", ""))
    state["account_name"] = profile.get("account_name", "")
    publish_result = None
    if (profile.get("social_type") or "").strip().lower() == "facebook":
        try:
            publish_result = publish_facebook_page_post(
                profile,
                message=state["generated_content"],
                link=state["post_link"],
            )
            append_generation_log(state["generation_log"], "status", f"Facebook publish complete: {publish_result.remote_post_id}")
        except Exception as exc:
            logger.exception("facebook social post publish failed")
            append_generation_log(state["generation_log"], "error", str(exc) or "Facebook publish failed.")
            detail = str(exc).strip()
            state["error"] = "Could not post to Facebook. Check the Page ID, Page access token, and Facebook app permissions."
            if detail:
                state["error"] = f"{state['error']} Facebook said: {detail}"
            return
    else:
        append_generation_log(state["generation_log"], "status", "Confirmed by user. Ready for platform publishing adapter.")

    state["history_id"] = str(_record_social_post_generation(state, profile, confirmed=True, publish_result=publish_result))
    if publish_result:
        state["success"] = f"Social post confirmed and posted to Facebook. Post ID: {publish_result.remote_post_id}"
    else:
        state["success"] = "Social post confirmed. It is saved as ready for posting."


def _record_social_post_generation(state: dict, profile: dict, confirmed: bool, publish_result=None) -> int:
    social_type = profile.get("social_type", "")
    status = "posted" if publish_result else ("confirmed_ready_to_post" if confirmed else "draft_awaiting_confirmation")
    return record_generation(
        content_type="Social Post",
        brand_name=profile.get("brand_name", ""),
        title=f"{_platform_label(social_type)} post for {profile.get('brand_name', '')}".strip(),
        primary_keyword=state["post_keyword"] or state["post_link"],
        medium_name=f"{_platform_label(social_type)} · {profile.get('account_name', '')}".strip(" ·"),
        word_count=len((state["generated_content"] or "").split()),
        meta_description=state["image_description"],
        post_link=publish_result.url if publish_result else "",
        tags=state["tags"],
        prompt_inputs={
            "social_profile_id": profile.get("id"),
            "brand_name": profile.get("brand_name", ""),
            "platform": social_type,
            "account_name": profile.get("account_name", ""),
            "platform_account_id": profile.get("platform_account_id", ""),
            "profile_url": profile.get("profile_url", ""),
            "post_keyword": state["post_keyword"],
            "reference_link": state["post_link"],
            "web_search_query": state["web_search_query"],
            "web_search_used": bool(state["web_search_used"]),
            "character_limit": state["character_limit"],
            "publish_status": status,
            "confirmed": bool(confirmed),
            "auto_publish_attempted": bool(publish_result),
            "remote_post_id": publish_result.remote_post_id if publish_result else "",
            "remote_post_url": publish_result.url if publish_result else "",
        },
        content=state["generated_content"],
        history_id=state["history_id"],
    )


def _apply_matchup_reaction_lines(content: str, keyword: str, max_characters: int = 0) -> str:
    teams = _matchup_teams(keyword)
    cleaned_content = (content or "").strip()
    if not teams:
        return cleaned_content
    team_1, team_2 = teams
    reaction_lines = f"React \U0001f49f for Team #{_team_hashtag(team_1)}\nReact \U0001f44d for Team #{_team_hashtag(team_2)}"
    if reaction_lines in cleaned_content:
        return cleaned_content
    separator = "\n\n" if cleaned_content else ""
    candidate = f"{cleaned_content}{separator}{reaction_lines}"
    limit = _int_or_zero(max_characters)
    if not limit or len(candidate) <= limit:
        return candidate

    allowed_content_length = limit - len(reaction_lines) - len(separator)
    if allowed_content_length <= 0:
        return reaction_lines[:limit] if limit else reaction_lines
    trimmed = cleaned_content[:allowed_content_length].rstrip()
    trimmed = re.sub(r"\s+\S*$", "", trimmed).strip() or cleaned_content[:allowed_content_length].rstrip()
    return f"{trimmed}{separator}{reaction_lines}"


def _matchup_teams(keyword: str) -> tuple[str, str] | None:
    match = re.search(r"^\s*(.+?)\s+vs\.?\s+(.+?)\s*$", str(keyword or "").strip(), flags=re.IGNORECASE)
    if not match:
        return None
    team_1 = _clean_matchup_team(match.group(1))
    team_2 = _clean_matchup_team(match.group(2))
    if not team_1 or not team_2:
        return None
    return team_1, team_2


def _clean_matchup_team(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip(" -:|")
    cleaned = re.sub(r"\b(live|prediction|preview|odds|score|stream|highlights|today|tonight)\b", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip(" -:|")


def _team_hashtag(team: str) -> str:
    hashtag = re.sub(r"[^A-Za-z0-9]+", "", team.title())
    return hashtag or "Team"


def _selected_social_profile(state: dict) -> dict | None:
    profile_id = state.get("social_profile_id", "")
    if not str(profile_id).isdigit():
        return None
    return get_social_profile(int(profile_id))


def _default_social_scheduler_state() -> dict:
    return {
        "profile_id": "",
        "brand_name": "",
        "social_type": "facebook",
        "account_name": "",
        "platform_account_id": "",
        "profile_url": "",
        "api_key": "",
        "api_secret": "",
        "access_token": "",
        "refresh_token": "",
        "posts_per_day": 1,
        "is_active": True,
        "notes": "",
        "success": None,
        "error": None,
        "post_result": None,
        "post_error": None,
        "post_keyword": "",
        "post_link": "",
        "post_profile_id": "",
    }


def _populate_social_profile_for_edit(state: dict, profile_id: int) -> None:
    profile = get_social_profile(profile_id)
    if not profile:
        return
    state["profile_id"] = str(profile.get("id", ""))
    state["brand_name"] = profile.get("brand_name", "")
    state["social_type"] = profile.get("social_type", "facebook") or "facebook"
    state["account_name"] = profile.get("account_name", "")
    state["platform_account_id"] = profile.get("platform_account_id", "")
    state["profile_url"] = profile.get("profile_url", "")
    state["api_key"] = profile.get("api_key", "")
    state["api_secret"] = profile.get("api_secret", "")
    state["access_token"] = profile.get("access_token", "")
    state["refresh_token"] = profile.get("refresh_token", "")
    state["posts_per_day"] = profile.get("posts_per_day", 0) or 0
    state["is_active"] = bool(profile.get("is_active", 1))
    state["notes"] = profile.get("notes", "")


def _handle_save_social_profile(state: dict) -> None:
    state["profile_id"] = request.form.get("profile_id", "").strip()
    state["brand_name"] = request.form.get("brand_name", "").strip()
    state["social_type"] = request.form.get("social_type", "facebook").strip() or "facebook"
    state["account_name"] = request.form.get("account_name", "").strip()
    state["platform_account_id"] = request.form.get("platform_account_id", "").strip()
    state["profile_url"] = request.form.get("profile_url", "").strip()
    state["api_key"] = request.form.get("api_key", "").strip()
    state["api_secret"] = request.form.get("api_secret", "").strip()
    state["access_token"] = request.form.get("access_token", "").strip()
    state["refresh_token"] = request.form.get("refresh_token", "").strip()
    state["posts_per_day"] = request.form.get("posts_per_day", "0").strip()
    state["is_active"] = request.form.get("is_active") == "1"
    state["notes"] = request.form.get("notes", "").strip()

    if not state["brand_name"]:
        state["error"] = "Choose or enter the brand for this social account."
        return
    if not state["account_name"]:
        state["error"] = "Enter the social account name or handle."
        return
    valid_platforms = {value for value, _label in SOCIAL_PLATFORM_OPTIONS}
    if state["social_type"] not in valid_platforms:
        state["social_type"] = "other"
    try:
        state["posts_per_day"] = max(0, int(state["posts_per_day"] or 0))
    except ValueError:
        state["posts_per_day"] = 0

    profile_id = int(state["profile_id"]) if state["profile_id"].isdigit() else None
    save_social_profile(
        brand_name=state["brand_name"],
        social_type=state["social_type"],
        account_name=state["account_name"],
        platform_account_id=state["platform_account_id"],
        profile_url=state["profile_url"],
        api_key=state["api_key"],
        api_secret=state["api_secret"],
        access_token=state["access_token"],
        refresh_token=state["refresh_token"],
        posts_per_day=state["posts_per_day"],
        is_active=state["is_active"],
        notes=state["notes"],
        profile_id=profile_id,
    )
    state.update(_default_social_scheduler_state())
    state["success"] = "Social account saved."


def _handle_delete_social_profile(state: dict) -> None:
    profile_id = request.form.get("profile_id", "").strip()
    if not profile_id.isdigit():
        state["error"] = "Select a social account to delete."
        return
    delete_social_profile(int(profile_id))
    state["success"] = "Social account deleted."


def _handle_create_social_post(state: dict) -> None:
    state["post_profile_id"] = request.form.get("profile_id", "").strip()
    state["post_keyword"] = request.form.get("post_keyword", "").strip()
    state["post_link"] = request.form.get("post_link", "").strip()
    if not state["post_profile_id"].isdigit():
        state["post_error"] = "Select a social account before creating a post."
        return
    profile = get_social_profile(int(state["post_profile_id"]))
    if not profile:
        state["post_error"] = "The selected social account could not be found."
        return

    search_query = state["post_link"] or state["post_keyword"]
    if not search_query:
        state["post_error"] = "Add a link or keyword for the social post."
        return

    try:
        provider = get_provider()
        social_type = profile.get("social_type", "")
        character_limit = social_post_character_limit_for_platform(social_type)
        research_context = build_web_research_context(search_query)
        result = generate_social_media_post(
            provider,
            focus_word=state["post_keyword"] or state["post_link"],
            brand_name=profile.get("brand_name", ""),
            social_type=social_type,
            brand_context=get_brand_context(profile.get("brand_name", "")),
            reference_link=state["post_link"],
            research_context=research_context,
            max_characters=character_limit,
        )
        history_id = record_generation(
            content_type="Social Post",
            title=f"{_platform_label(social_type)} post for {profile.get('brand_name', '')}".strip(),
            primary_keyword=state["post_keyword"] or state["post_link"],
            medium_name=f"{_platform_label(social_type)} · {profile.get('account_name', '')}".strip(" ·"),
            word_count=len((result.get("post_content") or "").split()),
            meta_description=result.get("image_description", ""),
            tags=result.get("tags", []),
            prompt_inputs={
                "social_profile_id": profile.get("id"),
                "brand_name": profile.get("brand_name", ""),
                "platform": social_type,
                "account_name": profile.get("account_name", ""),
                "profile_url": profile.get("profile_url", ""),
                "post_keyword": state["post_keyword"],
                "reference_link": state["post_link"],
                "web_search_query": search_query,
                "web_search_used": bool(research_context),
                "character_limit": character_limit,
                "auto_publish_attempted": False,
            },
            content=result.get("post_content", ""),
        )
        state["post_result"] = {
            **result,
            "history_id": history_id,
            "platform": _platform_label(social_type),
            "account_name": profile.get("account_name", ""),
            "reference_link": state["post_link"],
            "web_search_query": search_query,
            "web_search_used": bool(research_context),
        }
        state["success"] = "Social post created and saved to history."
    except Exception as exc:
        logger.exception("social scheduler create post failed")
        state["post_error"] = generation_error_message(
            "Could not create the social post. Check logs/app.log for details.",
            exc,
        )


def _platform_label(social_type: str) -> str:
    labels = dict(SOCIAL_PLATFORM_OPTIONS)
    return labels.get(social_type, (social_type or "Social").replace("_", " ").title())


def _social_post_progress_callback(token: str, log_entries: list[dict] | None = None):
    cleaned_token = (token or "").strip()

    def progress(message: str, kind: str = "status") -> None:
        if log_entries is not None:
            append_generation_log(log_entries, kind, message)
        if not cleaned_token:
            return
        if kind == "prompt":
            publish_generation_prompt(cleaned_token, message)
            return
        if kind == "draft":
            publish_generation_draft(cleaned_token, message, "Generated Social Post: Draft available while retrying...")
            return
        publish_generation_status(cleaned_token, f"Generated Social Post: {message}")

    progress.generation_token = cleaned_token
    return progress


def _split_tags(value: str) -> list[str]:
    tags = []
    seen = set()
    for item in str(value or "").replace("\n", ",").split(","):
        cleaned = item.strip()
        normalized = cleaned.lower()
        if cleaned and normalized not in seen:
            seen.add(normalized)
            tags.append(cleaned)
    return tags[:12]


def _masked_secret(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= 4:
        return "Set"
    return f"...{cleaned[-4:]}"


def neutral_blog_generator():
    state = {
        "topic": "",
        "suggested_content": "",
        "language": get_default_language(),
        "selected_medium_id": "",
        "selected_medium": None,
        "selected_title": "",
        "meta_description": "",
        "content": "",
        "visual": "",
        "post_link": "",
        "history_id": "",
        "tag_suggestions": [],
        "reference_links": [],
        "quality_report": None,
        "error": None,
        "success": None,
        "mediums": list_backlinks(),
        "content_checklist_items": list_checklist_items("blog", active_only=True),
        "language_options": language_options(get_default_language()),
    }
    selected_medium = request.args.get("medium_id", "").strip()
    if request.method == "GET" and selected_medium.isdigit():
        state["selected_medium_id"] = selected_medium
    edit_history_id = request.args.get("edit_history_id", "").strip()
    if request.method == "GET" and edit_history_id.isdigit():
        _load_history_item(state, int(edit_history_id))

    if request.method == "POST":
        action = request.form.get("action", "generate_content").strip()
        if action == "save_generated_blog":
            _handle_save_neutral_post(state)
        else:
            _handle_generate_neutral_article(state)

    state["language_options"] = language_options(state["language"])
    return render_template("social_media_activator.html", **base_template_context(), **state)


def _load_history_item(state: dict, history_id: int):
    item = get_generation_history_item(history_id)
    if not item:
        return
    prompt_inputs = _loads(item.get("prompt_inputs", "{}"))
    selected_medium = _find_medium_from_history(prompt_inputs, item.get("medium_name", ""))
    state["history_id"] = str(item.get("id", ""))
    state["topic"] = item.get("primary_keyword", "") if item.get("primary_keyword") != "random topic" else prompt_inputs.get("topic", "")
    state["suggested_content"] = prompt_inputs.get("suggested_content", "") or ""
    state["language"] = prompt_inputs.get("language", state["language"]) or "English"
    state["selected_medium"] = selected_medium
    state["selected_medium_id"] = str(selected_medium.get("id", "")) if selected_medium else str(prompt_inputs.get("medium_id", ""))
    state["selected_title"] = item.get("title", "") or ""
    state["meta_description"] = item.get("meta_description", "") or ""
    state["content"] = item.get("content", "") or ""
    state["visual"] = prompt_inputs.get("visual", "") or ""
    state["post_link"] = item.get("post_link", "") or ""
    state["tag_suggestions"] = [tag.strip() for tag in (item.get("tags", "") or "").split(",") if tag.strip()]
    state["reference_links"] = prompt_inputs.get("reference_links", []) if isinstance(prompt_inputs.get("reference_links", []), list) else []
    state["quality_report"] = _loads(item.get("quality_report", "{}"))


def _find_medium_from_history(prompt_inputs: dict, medium_name: str) -> dict | None:
    medium_id = str(prompt_inputs.get("medium_id", "") or prompt_inputs.get("publishing_medium_id", "")).strip()
    if medium_id.isdigit():
        medium = get_backlink(int(medium_id))
        if medium:
            return medium
    return _find_medium_by_name(medium_name)


def _find_medium_by_name(medium_name: str) -> dict | None:
    cleaned = (medium_name or "").strip().lower()
    normalized = cleaned.replace(" · ", " ").replace(" - ", " ")
    for medium in list_backlinks():
        website_name = (medium.get("website_name", "") or "").strip().lower()
        account_name = (medium.get("blog_name", "") or medium.get("account_name", "") or "").strip().lower()
        display_name = _medium_display_name(medium).lower()
        if display_name == cleaned or (website_name == cleaned and not account_name):
            return medium
        if website_name and account_name and website_name in normalized and account_name in normalized:
            return medium
    return None


def _handle_generate_neutral_article(state: dict):
    state["topic"] = request.form.get("topic", "").strip()
    state["suggested_content"] = request.form.get("suggested_content", "").strip()
    state["language"] = _language_from_request()
    state["selected_medium_id"] = request.form.get("selected_medium_id", "").strip()
    state["history_id"] = request.form.get("history_id", "").strip()

    if not state["selected_medium_id"].isdigit():
        state["error"] = "Please select a medium."
        return

    state["selected_medium"] = get_backlink(int(state["selected_medium_id"]))
    if not state["selected_medium"]:
        state["error"] = "The selected medium could not be found."
        return

    try:
        provider = get_provider()
        progress = _progress_callback("Neutral blog", request.form.get("generation_status_token", ""))
        progress("Generating neutral title...")
        result = generate_neutral_blog_article(
            provider,
            topic=state["topic"],
            suggested_content=state["suggested_content"],
            medium=state["selected_medium"],
            language=state["language"],
            progress_callback=progress,
        )
        state["selected_title"] = result.get("title", "")
        state["meta_description"] = result.get("meta_description", "")
        state["content"] = result.get("content", "")
        state["visual"] = result.get("visual", "")
        state["tag_suggestions"] = result.get("tags", [])
        state["reference_links"] = result.get("reference_links", [])
        state["quality_report"] = _quality_report(state)
        state["history_id"] = str(record_generation(
            content_type="Neutral Post",
            title=state["selected_title"],
            primary_keyword=state["topic"] or "random topic",
            medium_name=_medium_display_name(state["selected_medium"]),
            word_count=state["quality_report"]["word_count"],
            meta_description=state["meta_description"],
            tags=state["tag_suggestions"],
            prompt_inputs={
                "topic": state["topic"],
                "suggested_content": state["suggested_content"],
                "language": state["language"],
                "medium_id": state["selected_medium_id"],
                "medium": _medium_context(state["selected_medium"]),
                "visual": state["visual"],
                "reference_links": state["reference_links"],
            },
            content=state["content"],
            quality_report=state["quality_report"],
            history_id=state["history_id"],
        ))
        clear_generation_status(request.form.get("generation_status_token", ""))
    except Exception as exc:
        logger.exception("neutral_blog_generator generation failed")
        state["error"] = generation_error_message(
            "An error occurred while generating the neutral post. Check logs/app.log for details.",
            exc,
        )


def _handle_save_neutral_post(state: dict):
    state["topic"] = request.form.get("topic", "").strip()
    state["suggested_content"] = request.form.get("suggested_content", "").strip()
    state["language"] = _language_from_request()
    state["selected_medium_id"] = request.form.get("selected_medium_id", "").strip()
    state["selected_title"] = request.form.get("selected_title", "").strip()
    state["meta_description"] = request.form.get("meta_description", "").strip()
    state["content"] = request.form.get("content_html", "").strip()
    state["visual"] = request.form.get("visual", "").strip()
    state["post_link"] = _normalize_post_link(request.form.get("post_link", ""))
    state["history_id"] = request.form.get("history_id", "").strip()
    tags = [tag.strip() for tag in request.form.get("tags", "").split(",") if tag.strip()]
    state["tag_suggestions"] = tags
    state["reference_links"] = _parse_reference_links(request.form.get("reference_links", ""))

    if state["selected_medium_id"].isdigit():
        state["selected_medium"] = get_backlink(int(state["selected_medium_id"]))

    if not state["selected_medium"]:
        state["error"] = "The selected medium could not be found."
        return
    if not state["selected_title"]:
        state["error"] = "There is no generated neutral title to save."
        return
    if not state["content"]:
        state["error"] = "There is no generated neutral post to save."
        return
    if not _valid_post_link(state["post_link"]):
        state["error"] = "Please enter a valid post link before saving."
        return

    state["quality_report"] = _quality_report(state)
    failed_checks = [
        check.get("name", "Validator")
        for check in state["quality_report"].get("checks", [])
        if check.get("status") == "fail"
    ]
    if failed_checks:
        state["error"] = "Please fix the neutral post validator before saving: " + ", ".join(failed_checks)
        return

    state["history_id"] = str(record_generation(
        content_type="Neutral Post",
        title=state["selected_title"],
        primary_keyword=state["topic"] or "random topic",
        medium_name=_medium_display_name(state["selected_medium"]),
        word_count=state["quality_report"].get("word_count", count_html_words(state["content"])),
        meta_description=state["meta_description"],
        post_link=state["post_link"],
        tags=state["tag_suggestions"],
        prompt_inputs={
            "topic": state["topic"],
            "suggested_content": state["suggested_content"],
            "language": state["language"],
            "medium_id": state["selected_medium_id"],
            "medium": _medium_context(state["selected_medium"]),
            "visual": state["visual"],
            "reference_links": state["reference_links"],
            "manual_save": True,
        },
        content=state["content"],
        quality_report=state["quality_report"],
        history_id=state["history_id"],
    ))
    state["success"] = "Generated neutral post saved to history."


def _quality_report(state: dict) -> dict:
    medium = state["selected_medium"] or {}
    report = analyze_generated_content(
        state["content"],
        title=state["selected_title"],
        keyword=state["topic"],
        meta_description=state["meta_description"],
        min_words=_int_or_zero(medium.get("min_words", 0)),
        max_words=_int_or_zero(medium.get("max_characters", 0)),
        required_url="",
    )
    report["checks"].extend(_neutral_validator_checks(state, report))
    return report


def _neutral_validator_checks(state: dict, report: dict) -> list[dict]:
    title = (state.get("selected_title") or "").strip()
    meta_description = (state.get("meta_description") or "").strip()
    visual = (state.get("visual") or "").strip()
    tags = state.get("tag_suggestions") or []
    references = state.get("reference_links") or []
    content = state.get("content") or ""
    content_links = _extract_links(content)
    reference_urls = [item.get("url", "").strip() for item in references if item.get("url", "").strip()]
    missing_reference_urls = [url for url in reference_urls if url not in content_links and url not in content]
    reference_positions = sorted(content.find(url) for url in reference_urls if url and url in content)
    references_are_clustered = len(reference_positions) >= 2 and reference_positions[-1] - reference_positions[0] < 200

    return [
        _validator_check(
            "Neutral title",
            "pass" if title else "fail",
            title or "Missing generated title",
            "Generate or add a clear neutral title before saving.",
        ),
        _validator_check(
            "Neutral meta",
            "pass" if 120 <= len(meta_description) <= 140 else "fail",
            f"{len(meta_description)} characters",
            "Keep the generated meta description between 120 and 140 characters.",
        ),
        _validator_check(
            "Neutral tags",
            "pass" if len(tags) >= 3 else "warn",
            f"{len(tags)} tag(s)",
            "Keep at least a few relevant tags for organization and publishing.",
        ),
        _validator_check(
            "Visual ideas",
            "pass" if visual else "warn",
            "Present" if visual else "Missing visual ideas",
            "Add visual or image directions before publishing when the medium benefits from it.",
        ),
        _validator_check(
            "Reference links in content",
            "pass" if not missing_reference_urls and not references_are_clustered else "fail",
            _reference_detail(reference_urls, missing_reference_urls, references_are_clustered),
            "Place every reference URL naturally inside the article body and spread links across relevant sections.",
        ),
        _validator_check(
            "Neutral link policy",
            "pass",
            f"{report.get('link_count', 0)} editorial link(s); no required target link",
            "Neutral Blog should use only editorial/reference links, not a required promotional post link.",
        ),
    ]


def _validator_check(name: str, status: str, detail: str, recommendation: str) -> dict:
    return {"name": name, "status": status, "detail": detail, "recommendation": recommendation}


def _reference_detail(reference_urls: list[str], missing_urls: list[str], clustered: bool) -> str:
    if not reference_urls:
        return "No reference links supplied"
    if missing_urls:
        return f"{len(missing_urls)} reference URL(s) missing from content"
    if clustered:
        return "Reference links are too close together"
    return f"{len(reference_urls)} reference URL(s) placed in content"


def _extract_links(content: str) -> list[str]:
    parser = _LinkParser()
    parser.feed(content or "")
    return parser.links


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attrs_dict = {name.lower(): (value or "") for name, value in attrs}
        href = attrs_dict.get("href", "").strip()
        if href:
            self.links.append(href)


def _medium_context(medium: dict) -> dict:
    return {
        "website_name": medium.get("website_name", ""),
        "blog_name": medium.get("blog_name", "") or medium.get("account_name", ""),
        "website_type": medium.get("website_type", ""),
        "post_type": medium.get("post_type", ""),
        "min_words": medium.get("min_words", 0),
        "max_words": medium.get("max_characters", 0),
        "content_guidelines": medium.get("content_guidelines", ""),
    }


def _medium_display_name(medium: dict) -> str:
    name = (medium.get("website_name") or "").strip()
    account = (medium.get("blog_name") or medium.get("account_name") or "").strip()
    if name and account:
        return f"{name} · {account}"
    return name


def _parse_reference_links(raw: str) -> list[dict]:
    items = []
    for line in (raw or "").splitlines():
        title, _separator, url = line.partition("|")
        if title.strip() and url.strip():
            items.append({"title": title.strip(), "url": url.strip()})
    return items


def _int_or_zero(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _loads(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _language_from_request() -> str:
    return normalize_language(request.form.get("language", get_default_language()))


def _valid_post_link(value: str) -> bool:
    cleaned = (value or "").strip().lower()
    return cleaned.startswith("https://") or cleaned.startswith("http://")


def _normalize_post_link(value: str) -> str:
    cleaned = (value or "").strip()
    lowered = cleaned.lower()
    if lowered.startswith(("http://", "https://")):
        return cleaned
    if "." in cleaned and " " not in cleaned:
        return f"https://{cleaned}"
    return cleaned


def _progress_callback(label: str, token: str):
    cleaned_label = (label or "Generation").strip()

    def publish(message: str, kind: str = "status"):
        if kind == "prompt":
            publish_generation_prompt(token, message)
            return
        if kind == "draft":
            publish_generation_draft(token, message, f"{cleaned_label}: Draft available while retrying...")
            return
        publish_generation_status(token, f"{cleaned_label}: {message}")

    publish.generation_token = token
    return publish
