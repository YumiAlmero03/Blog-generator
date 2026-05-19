import json

from flask import render_template, request

from database import get_backlink, get_generation_history_item, list_backlinks, record_generation
from generators.content_generator import count_html_words, generate_ai_content_tags, generate_backlink_visual_idea, generate_tier2_content, revise_existing_content, suggest_content_tags
from generators.meta_description_generator import generate_backlink_meta_descriptions
from generators.title_generator import generate_backlink_titles
from logger import logger

from app.controllers.helpers import base_template_context
from app.services.content_quality_service import analyze_generated_content
from app.services.generation_status_service import clear_generation_status, publish_generation_prompt, publish_generation_status
from app.services.provider_service import generation_error_message, get_provider


def tier2_blog_generator():
    state = _initial_state()
    selected_medium = request.args.get("medium_id", "").strip()
    if request.method == "GET" and selected_medium.isdigit():
        state["selected_backlink_id"] = selected_medium
    edit_history_id = request.args.get("edit_history_id", "").strip()
    if request.method == "GET" and edit_history_id.isdigit():
        _load_history_item(state, int(edit_history_id))

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        if action == "generate_titles":
            _handle_generate_titles(state)
        elif action == "generate_content":
            _handle_generate_content(state)
        elif action == "save_generated_blog":
            _handle_save_generated_blog(state)

    return render_template("tier2_blog_generator.html", **base_template_context(), **state)


def _load_history_item(state: dict, history_id: int):
    item = get_generation_history_item(history_id)
    if not item:
        return
    prompt_inputs = _loads(item.get("prompt_inputs", "{}"))
    selected_backlink = _find_backlink_from_history(prompt_inputs, item.get("medium_name", ""))
    state["history_id"] = str(item.get("id", ""))
    state["selected_backlink"] = selected_backlink
    state["selected_backlink_id"] = str(selected_backlink.get("id", "")) if selected_backlink else str(prompt_inputs.get("publishing_medium_id", ""))
    state["anchor_text"] = prompt_inputs.get("anchor_text") or item.get("primary_keyword", "") or ""
    state["link"] = prompt_inputs.get("link", "")
    state["tone"] = prompt_inputs.get("tone", state["tone"])
    state["suggested_content"] = prompt_inputs.get("suggested_content", "")
    state["visual"] = prompt_inputs.get("visual", "")
    state["post_link"] = item.get("post_link", "") or ""
    state["titles"] = [item.get("title", "")] if item.get("title") else []
    state["selected_title"] = item.get("title", "") or ""
    state["meta_description"] = item.get("meta_description", "") or ""
    state["meta_descriptions"] = [{"text": state["meta_description"], "character_count": len(state["meta_description"])}] if state["meta_description"] else []
    state["content"] = item.get("content", "") or ""
    state["quality_report"] = _loads(item.get("quality_report", "{}"))
    state["tag_suggestions"] = [tag.strip() for tag in (item.get("tags", "") or "").split(",") if tag.strip()]
    state["step"] = "content"


def _find_backlink_from_history(prompt_inputs: dict, medium_name: str) -> dict | None:
    medium_id = str(prompt_inputs.get("publishing_medium_id", "") or prompt_inputs.get("medium_id", "")).strip()
    if medium_id.isdigit():
        backlink = get_backlink(int(medium_id))
        if backlink:
            return backlink
    return _find_backlink_by_name(medium_name)


def _find_backlink_by_name(medium_name: str) -> dict | None:
    cleaned = (medium_name or "").strip().lower()
    normalized = cleaned.replace(" · ", " ").replace(" - ", " ")
    for backlink in list_backlinks():
        website_name = (backlink.get("website_name", "") or "").strip().lower()
        account_name = (backlink.get("blog_name", "") or backlink.get("account_name", "") or "").strip().lower()
        display_name = _medium_display_name(backlink).lower()
        if display_name == cleaned or (website_name == cleaned and not account_name):
            return backlink
        if website_name and account_name and website_name in normalized and account_name in normalized:
            return backlink
    return None


def _initial_state() -> dict:
    return {
        "selected_backlink_id": "",
        "selected_backlink": None,
        "anchor_text": "",
        "link": "",
        "tone": "natural",
        "count": 10,
        "titles": [],
        "selected_title": "",
        "custom_title": "",
        "meta_descriptions": [],
        "meta_description": "",
        "content": "",
        "post_link": "",
        "visual": "",
        "history_id": "",
        "quality_report": None,
        "tag_suggestions": [],
        "suggested_content": "",
        "change_request": "",
        "regenerate_scope": "full",
        "error": None,
        "success": None,
        "step": "title",
        "backlinks": list_backlinks(),
    }


def _read_common_state(state: dict):
    state["selected_backlink_id"] = request.form.get("selected_backlink_id", "").strip()
    state["anchor_text"] = request.form.get("anchor_text", "").strip()
    state["link"] = request.form.get("link", "").strip()
    state["tone"] = request.form.get("tone", "natural").strip() or "natural"
    state["suggested_content"] = request.form.get("suggested_content", "").strip()
    state["change_request"] = request.form.get("change_request", "").strip()
    state["regenerate_scope"] = request.form.get("regenerate_scope", "full").strip() or "full"
    state["visual"] = request.form.get("visual", "").strip()
    state["history_id"] = request.form.get("history_id", "").strip()

    if state["selected_backlink_id"].isdigit():
        state["selected_backlink"] = get_backlink(int(state["selected_backlink_id"]))


def _validate_required_inputs(state: dict) -> bool:
    if not state["selected_backlink"]:
        state["error"] = "Please choose a publishing medium."
        return False
    if not state["anchor_text"]:
        state["error"] = "Please enter anchor text."
        return False
    if not state["link"]:
        state["error"] = "Please enter the link."
        return False
    return True


def _backlink_context(state: dict) -> dict:
    selected = state["selected_backlink"] or {}
    return {
        "backlink_website_name": selected.get("website_name", ""),
        "backlink_blog_url": "",
        "backlink_website_type": selected.get("website_type", "blog"),
        "backlink_post_type": selected.get("post_type", "html") or "html",
        "backlink_title_max_characters": selected.get("title_max_characters", 0) or 0,
        "backlink_min_words": selected.get("min_words", 0) or 0,
        "backlink_max_characters": selected.get("max_characters", 0) or 0,
        "backlink_tier_level": "Tier 2",
        "backlink_blog_name": selected.get("blog_name", "") or selected.get("account_name", ""),
        "backlink_writer_name": selected.get("writer_name", ""),
        "backlink_content_guidelines": selected.get("content_guidelines", ""),
    }


def _handle_generate_titles(state: dict):
    _read_common_state(state)
    count_raw = request.form.get("count", "10").strip()
    try:
        state["count"] = int(count_raw)
    except ValueError:
        state["count"] = 10

    if not _validate_required_inputs(state):
        return

    try:
        provider = get_provider()
        progress = _progress_callback("Tier 2 titles", request.form.get("generation_status_token", ""))
        progress("Starting Tier 2 title generation...")
        state["titles"] = generate_backlink_titles(
            provider,
            keyword=state["anchor_text"],
            tone=state["tone"],
            count=state["count"],
            brand="",
            brand_context="",
            **_backlink_context(state),
            keyword_is_anchor_text=True,
            progress_callback=progress,
        )
        progress("Tier 2 titles passed validation.")
        state["step"] = "title"
    except Exception as exc:
        logger.exception("tier2 generate_titles action failed")
        state["error"] = generation_error_message(
            "An error occurred while generating Tier 2 titles. Check logs/app.log for details.",
            exc,
        )


def _handle_generate_content(state: dict):
    _read_common_state(state)
    state["custom_title"] = request.form.get("custom_title", "").strip()
    state["selected_title"] = state["custom_title"] or request.form.get("selected_title", "").strip()
    titles_raw = request.form.get("titles_json", "").strip()
    meta_descriptions_raw = request.form.get("meta_descriptions_json", "").strip()
    selected_meta_description = request.form.get("meta_description_choice", "").strip()
    existing_content = request.form.get("content_html", "").strip()

    state["titles"] = _json_list(titles_raw)
    state["meta_descriptions"] = _json_list(meta_descriptions_raw)

    if not _validate_required_inputs(state):
        return
    if not state["selected_title"]:
        state["error"] = "Please select a title first."
        return

    try:
        provider = get_provider()
        progress = _progress_callback("Tier 2 blog", request.form.get("generation_status_token", ""))
        backlink_context = _backlink_context(state)
        is_minor_revision = bool(existing_content and state["change_request"])
        if not is_minor_revision:
            progress("Generating meta descriptions...")
            state["meta_descriptions"] = generate_backlink_meta_descriptions(
                provider,
                title=state["selected_title"],
                keyword=state["anchor_text"],
                count=5,
                brand="",
                brand_context="",
                **backlink_context,
                progress_callback=progress,
            )
        if state["meta_descriptions"]:
            selected_match = next(
                (item for item in state["meta_descriptions"] if item.get("text", "").strip() == selected_meta_description),
                None,
            )
            state["meta_description"] = (selected_match or state["meta_descriptions"][0]).get("text", "")
        else:
            state["meta_description"] = selected_meta_description

        if not is_minor_revision:
            progress("Generating 2 visual ideas...")
            state["visual"] = generate_backlink_visual_idea(
                provider,
                title=state["selected_title"],
                keyword=state["anchor_text"],
                brand="",
                backlink_website_name=backlink_context.get("backlink_website_name", ""),
                backlink_website_type=backlink_context.get("backlink_website_type", ""),
                backlink_blog_name=backlink_context.get("backlink_blog_name", ""),
                backlink_content_guidelines=backlink_context.get("backlink_content_guidelines", ""),
                progress_callback=progress,
            )
        if is_minor_revision:
            progress("Applying minor Tier 2 content changes...")
            state["content"] = revise_existing_content(
                provider,
                title=state["selected_title"],
                existing_content=existing_content,
                change_request=state["change_request"],
                scope=state["regenerate_scope"],
                output_format=backlink_context.get("backlink_post_type", "html"),
                keyword=state["anchor_text"],
                required_url=state["link"],
                required_anchor_text=state["anchor_text"],
                progress_callback=progress,
            )
        else:
            progress("Generating Tier 2 content...")
            state["content"] = generate_tier2_content(
                provider,
                title=state["selected_title"],
                anchor_text=state["anchor_text"],
                link=state["link"],
                tone=state["tone"],
                suggested_content=state["suggested_content"],
                change_request=_scoped_change_request(state["change_request"], state["regenerate_scope"]),
                **backlink_context,
                progress_callback=progress,
            )
        _prepare_quality_and_tags(state, provider=provider, progress=progress)
        _record_tier2_generation(state, manual_save=False)
        clear_generation_status(request.form.get("generation_status_token", ""))
        state["step"] = "content"
    except Exception as exc:
        logger.exception("tier2 generate_content action failed")
        state["error"] = generation_error_message(
            "An error occurred while generating Tier 2 content. Check logs/app.log for details.",
            exc,
        )


def _handle_save_generated_blog(state: dict):
    _read_common_state(state)
    state["custom_title"] = request.form.get("custom_title", "").strip()
    state["selected_title"] = state["custom_title"] or request.form.get("selected_title", "").strip()
    state["content"] = request.form.get("content_html", "").strip()
    state["post_link"] = _normalize_post_link(request.form.get("post_link", ""))
    titles_raw = request.form.get("titles_json", "").strip()
    state["meta_description"] = request.form.get("meta_description_choice", "").strip()

    try:
        state["titles"] = json.loads(titles_raw) if titles_raw else []
    except json.JSONDecodeError:
        state["titles"] = []

    if not _validate_required_inputs(state):
        return
    if not state["selected_title"]:
        state["error"] = "Please select a title before saving."
        return
    if not state["content"]:
        state["error"] = "There is no generated Tier 2 content to save."
        return
    if not _valid_post_link(state["post_link"]):
        state["error"] = "Please enter a valid post link before saving."
        state["step"] = "content"
        return

    _prepare_quality_and_tags(state)
    _record_tier2_generation(state, manual_save=True)
    state["success"] = "Generated Tier 2 blog saved to history."
    state["step"] = "content"


def _prepare_quality_and_tags(state: dict, provider=None, progress=None):
    selected = state["selected_backlink"] or {}
    min_words = _int_or_zero(selected.get("min_words", 0))
    max_words = _int_or_zero(selected.get("max_characters", 0))
    if provider:
        progress("Generating tags...")
        state["tag_suggestions"] = generate_ai_content_tags(
            provider,
            title=state["selected_title"],
            keyword=state["anchor_text"],
            content=state["content"],
            minimum=10,
            progress_callback=progress,
        )
    else:
        state["tag_suggestions"] = suggest_content_tags(
            title=state["selected_title"],
            keyword=state["anchor_text"],
            content=state["content"],
            minimum=10,
        )
    state["quality_report"] = analyze_generated_content(
        state["content"],
        title=state["selected_title"],
        keyword=state["anchor_text"],
        meta_description=state["meta_description"],
        min_words=min_words,
        max_words=max_words,
        required_url=state["link"],
    )


def _record_tier2_generation(state: dict, manual_save: bool):
    state["history_id"] = str(record_generation(
        content_type="Tier 2 Blog",
        title=state["selected_title"],
        primary_keyword=state["anchor_text"],
        medium_name=_medium_display_name(state["selected_backlink"] or {}),
        word_count=state["quality_report"].get("word_count", count_html_words(state["content"])),
        meta_description=state["meta_description"],
        post_link=state.get("post_link", ""),
        tags=state["tag_suggestions"],
        prompt_inputs={
            "publishing_medium_id": state["selected_backlink_id"],
            "anchor_text": state["anchor_text"],
            "link": state["link"],
            "tone": state["tone"],
            "suggested_content": state["suggested_content"],
            "regenerate_scope": state["regenerate_scope"],
            "change_request": state["change_request"],
            "manual_save": manual_save,
            "visual": state["visual"],
        },
        content=state["content"],
        quality_report=state["quality_report"],
        history_id=state.get("history_id", ""),
    ))


def _scoped_change_request(change_request: str, scope: str) -> str:
    cleaned = (change_request or "").strip()
    cleaned_scope = (scope or "full").strip().lower()
    scope_labels = {
        "intro": "Regenerate only the first paragraph/introduction and keep the required Tier 2 URL exactly once anywhere in the article.",
        "section": "Regenerate the weakest body section while keeping the selected medium format and required Tier 2 link rule.",
        "conclusion": "Regenerate only the ending section without adding the required Tier 2 URL again.",
        "tags": "Refresh the tag angle and make the content naturally support better tags.",
    }
    prefix = scope_labels.get(cleaned_scope, "")
    if not prefix:
        return cleaned
    return f"{prefix}\n{cleaned}".strip()


def _medium_display_name(medium: dict) -> str:
    name = (medium.get("website_name") or "").strip()
    account = (medium.get("blog_name") or medium.get("account_name") or "").strip()
    if name and account:
        return f"{name} · {account}"
    return name


def _int_or_zero(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


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


def _json_list(raw: str) -> list:
    try:
        parsed = json.loads(raw) if raw else []
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _loads(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _progress_callback(label: str, token: str):
    cleaned_label = (label or "Generation").strip()

    def publish(message: str, kind: str = "status"):
        if kind == "prompt":
            publish_generation_prompt(token, message)
            return
        publish_generation_status(token, f"{cleaned_label}: {message}")

    return publish
