import json

from flask import render_template, request

from database import get_backlink, get_brand_context, get_brand_record, get_generation_history_item, list_backlinks, list_brand_names, list_checklist_items, record_blog, record_generation, upsert_brand
from generators.content_generator import count_html_words, generate_ai_content_tags, generate_backlink_content, generate_backlink_visual_idea, revise_existing_content, suggest_content_tags
from generators.meta_description_generator import generate_backlink_meta_descriptions
from generators.title_generator import generate_backlink_titles
from logger import logger

from app.controllers.helpers import base_template_context
from app.services.content_quality_service import analyze_generated_content
from app.services.generation_status_service import clear_generation_status, publish_generation_draft, publish_generation_prompt, publish_generation_status
from app.services.locale_settings import get_default_language, language_options, normalize_language
from app.services.provider_service import generation_error_message, get_provider


def backlink_blog_generator():
    state = {
        "keyword": "",
        "brand": "",
        "language": get_default_language(),
        "tone": "natural",
        "count": 10,
        "titles": [],
        "selected_title": "",
        "custom_title": "",
        "meta_descriptions": [],
        "meta_description": "",
        "content": "",
        "visual": "",
        "quality_report": None,
        "tag_suggestions": [],
        "suggested_content": "",
        "change_request": "",
        "regenerate_scope": "full",
        "error": None,
        "success": None,
        "step": "title",
        "brand_website_url": "",
        "post_link": "",
        "history_id": "",
        "selected_backlink_id": "",
        "selected_backlink": None,
        "brand_names": list_brand_names(),
        "backlinks": list_backlinks(),
        "content_checklist_items": list_checklist_items("blog", active_only=True),
        "language_options": language_options(get_default_language()),
    }
    selected_medium = request.args.get("medium_id", "").strip()
    if request.method == "GET" and selected_medium.isdigit():
        state["selected_backlink_id"] = selected_medium
    selected_brand = request.args.get("brand", "").strip()
    if request.method == "GET" and selected_brand:
        state["brand"] = selected_brand
        brand_record = get_brand_record(selected_brand) or {}
        state["brand_website_url"] = brand_record.get("website", "").strip()
    edit_history_id = request.args.get("edit_history_id", "").strip()
    if request.method == "GET" and edit_history_id.isdigit():
        _load_history_item(state, int(edit_history_id))

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        if action == "generate_titles":
            _handle_generate_titles(state)
        elif action == "generate_meta_descriptions":
            _handle_generate_meta_descriptions(state)
        elif action == "generate_content":
            _handle_generate_content(state)
        elif action == "save_generated_blog":
            _handle_save_generated_blog(state)

    state["language_options"] = language_options(state["language"])
    return render_template("backlink_blog_generator.html", **base_template_context(), **state)


def _load_history_item(state: dict, history_id: int):
    item = get_generation_history_item(history_id)
    if not item:
        return
    prompt_inputs = _loads(item.get("prompt_inputs", "{}"))
    medium_name = item.get("medium_name", "") or ""
    selected_backlink = _find_backlink_from_history(prompt_inputs, medium_name)
    state["history_id"] = str(item.get("id", ""))
    state["selected_backlink"] = selected_backlink
    state["selected_backlink_id"] = str(selected_backlink.get("id", "")) if selected_backlink else ""
    state["brand"] = item.get("brand_name", "") or ""
    state["keyword"] = item.get("primary_keyword", "") or ""
    state["language"] = prompt_inputs.get("language", state["language"]) or "English"
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
    if state["brand"]:
        brand_record = get_brand_record(state["brand"]) or {}
        state["brand_website_url"] = brand_record.get("website", "").strip()
    state["step"] = "content"


def _find_backlink_from_history(prompt_inputs: dict, medium_name: str) -> dict | None:
    medium_id = str(prompt_inputs.get("medium_id", "") or prompt_inputs.get("publishing_medium_id", "")).strip()
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


def _handle_generate_titles(state: dict):
    state["brand"] = request.form.get("brand", "").strip()
    state["keyword"] = request.form.get("keyword", "").strip()
    state["language"] = _language_from_request()
    state["tone"] = request.form.get("tone", "natural").strip() or "natural"
    state["selected_backlink_id"] = request.form.get("selected_backlink_id", "").strip()
    count_raw = request.form.get("count", "10").strip()

    if not state["brand"]:
        state["error"] = "Please select a brand for the medium content."
        return

    if not state["selected_backlink_id"].isdigit():
        state["error"] = "Please choose a medium first."
        return

    state["selected_backlink"] = get_backlink(int(state["selected_backlink_id"]))
    if not state["selected_backlink"]:
        state["error"] = "The selected medium could not be found."
        return

    upsert_brand(state["brand"])
    brand_record = get_brand_record(state["brand"]) or {}
    state["brand_website_url"] = brand_record.get("website", "").strip()

    if not state["keyword"]:
        state["keyword"] = brand_record.get("main_keywords", "").strip()

    if not state["keyword"]:
        state["error"] = "The selected brand needs main keywords saved in Brands before generating medium titles."
        return

    if not state["brand_website_url"]:
        state["error"] = "The selected brand needs a website saved in Brands before generating medium content."
        return

    try:
        state["count"] = int(count_raw)
    except ValueError:
        state["count"] = 10

    try:
        provider = get_provider()
        brand_context = get_brand_context(state["brand"])
        progress = _progress_callback("Medium titles", request.form.get("generation_status_token", ""))
        progress("Starting title generation...")
        state["titles"] = generate_backlink_titles(
            provider,
            keyword=state["keyword"],
            tone=state["tone"],
            count=state["count"],
            brand=state["brand"],
            brand_context=brand_context,
            backlink_website_name=state["selected_backlink"].get("website_name", ""),
            backlink_blog_url="",
            backlink_website_type=state["selected_backlink"].get("website_type", "blog"),
            backlink_post_type=state["selected_backlink"].get("post_type", "html") or "html",
            backlink_title_max_characters=state["selected_backlink"].get("title_max_characters", 0) or 0,
            backlink_min_words=state["selected_backlink"].get("min_words", 0) or 0,
            backlink_max_characters=state["selected_backlink"].get("max_characters", 0) or 0,
            backlink_tier_level="Tier 1",
            backlink_blog_name=state["selected_backlink"].get("blog_name", "") or state["selected_backlink"].get("account_name", ""),
            backlink_writer_name=state["selected_backlink"].get("writer_name", ""),
            backlink_content_guidelines=state["selected_backlink"].get("content_guidelines", ""),
            brand_topic_mode=state["selected_backlink"].get("brand_topic_mode", "example"),
            language=state["language"],
            progress_callback=progress,
        )
        progress("Titles passed validation.")
        state["step"] = "title"
    except Exception as exc:
        logger.exception("backlink generate_titles action failed")
        state["error"] = generation_error_message(
            "An error occurred while generating medium titles. Check logs/app.log for details.",
            exc,
        )


def _handle_generate_meta_descriptions(state: dict):
    state["custom_title"] = request.form.get("custom_title", "").strip()
    state["selected_title"] = state["custom_title"] or request.form.get("selected_title", "").strip()
    state["keyword"] = request.form.get("keyword", "").strip()
    state["brand"] = request.form.get("brand", "").strip()
    state["language"] = _language_from_request()
    state["tone"] = request.form.get("tone", "natural").strip() or "natural"
    state["brand_website_url"] = request.form.get("brand_website_url", "").strip()
    state["history_id"] = request.form.get("history_id", "").strip()
    state["selected_backlink_id"] = request.form.get("selected_backlink_id", "").strip()
    state["titles"] = _json_list(request.form.get("titles_json", "").strip())
    state["meta_descriptions"] = _json_list(request.form.get("meta_descriptions_json", "").strip())

    if not state["selected_title"]:
        state["error"] = "Please select a title first."
        return

    if not state["selected_backlink_id"].isdigit():
        state["error"] = "Please choose a medium first."
        return

    state["selected_backlink"] = get_backlink(int(state["selected_backlink_id"]))
    if not state["selected_backlink"]:
        state["error"] = "The selected medium could not be found."
        return

    if not state["brand"]:
        state["error"] = "Please select a brand for the medium content."
        return

    if not state["brand_website_url"]:
        brand_record = get_brand_record(state["brand"])
        state["brand_website_url"] = (brand_record or {}).get("website", "").strip()
    if not state["brand_website_url"]:
        state["error"] = "The selected brand needs a website saved in Brands before generating medium content."
        return

    try:
        provider = get_provider()
        progress = _progress_callback("Medium meta descriptions", request.form.get("generation_status_token", ""))
        if state["brand"]:
            upsert_brand(state["brand"])
        brand_context = get_brand_context(state["brand"])
        backlink_context = {
            "backlink_website_name": state["selected_backlink"].get("website_name", ""),
            "backlink_blog_url": "",
            "backlink_website_type": state["selected_backlink"].get("website_type", "blog"),
            "backlink_post_type": state["selected_backlink"].get("post_type", "html") or "html",
            "backlink_title_max_characters": state["selected_backlink"].get("title_max_characters", 0) or 0,
            "backlink_min_words": state["selected_backlink"].get("min_words", 0) or 0,
            "backlink_max_characters": state["selected_backlink"].get("max_characters", 0) or 0,
            "backlink_tier_level": "Tier 1",
            "backlink_blog_name": state["selected_backlink"].get("blog_name", "") or state["selected_backlink"].get("account_name", ""),
            "backlink_writer_name": state["selected_backlink"].get("writer_name", ""),
            "backlink_content_guidelines": state["selected_backlink"].get("content_guidelines", ""),
            "brand_topic_mode": state["selected_backlink"].get("brand_topic_mode", "example"),
        }
        state["meta_descriptions"] = generate_backlink_meta_descriptions(
            provider,
            title=state["selected_title"],
            keyword=state["keyword"],
            count=5,
            brand=state["brand"],
            brand_context=brand_context,
            **backlink_context,
            language=state["language"],
            progress_callback=progress,
        )
        if state["meta_descriptions"]:
            state["meta_description"] = state["meta_descriptions"][0].get("text", "")
        state["step"] = "meta"
    except Exception as exc:
        logger.exception("backlink generate_meta_descriptions action failed")
        state["error"] = generation_error_message(
            "An error occurred while generating medium meta descriptions. Check logs/app.log for details.",
            exc,
        )


def _handle_generate_content(state: dict):
    state["custom_title"] = request.form.get("custom_title", "").strip()
    state["selected_title"] = state["custom_title"] or request.form.get("selected_title", "").strip()
    state["keyword"] = request.form.get("keyword", "").strip()
    state["brand"] = request.form.get("brand", "").strip()
    state["language"] = _language_from_request()
    state["tone"] = request.form.get("tone", "natural").strip() or "natural"
    state["suggested_content"] = request.form.get("suggested_content", "").strip()
    state["change_request"] = request.form.get("change_request", "").strip()
    state["regenerate_scope"] = request.form.get("regenerate_scope", "full").strip() or "full"
    state["visual"] = request.form.get("visual", "").strip()
    state["brand_website_url"] = request.form.get("brand_website_url", "").strip()
    state["post_link"] = _normalize_post_link(request.form.get("post_link", ""))
    state["history_id"] = request.form.get("history_id", "").strip()
    state["selected_backlink_id"] = request.form.get("selected_backlink_id", "").strip()
    titles_raw = request.form.get("titles_json", "").strip()
    meta_descriptions_raw = request.form.get("meta_descriptions_json", "").strip()
    selected_meta_description = request.form.get("meta_description_choice", "").strip()
    existing_content = request.form.get("content_html", "").strip()

    if not state["selected_title"]:
        state["error"] = "Please select a title first."
        return

    if not state["selected_backlink_id"].isdigit():
        state["error"] = "Please choose a medium first."
        return

    state["selected_backlink"] = get_backlink(int(state["selected_backlink_id"]))
    if not state["selected_backlink"]:
        state["error"] = "The selected medium could not be found."
        return

    if not state["brand"]:
        state["error"] = "Please select a brand for the medium content."
        return

    if not state["brand_website_url"]:
        brand_record = get_brand_record(state["brand"])
        state["brand_website_url"] = (brand_record or {}).get("website", "").strip()
    if not state["brand_website_url"]:
        state["error"] = "The selected brand needs a website saved in Brands before generating medium content."
        return

    try:
        state["titles"] = _json_list(request.form.get("titles_json", "").strip())
        state["meta_descriptions"] = _json_list(request.form.get("meta_descriptions_json", "").strip())
        provider = get_provider()
        progress = _progress_callback("Medium blog", request.form.get("generation_status_token", ""))
        if state["brand"]:
            upsert_brand(state["brand"])
        brand_context = get_brand_context(state["brand"])
        backlink_context = {
            "backlink_website_name": state["selected_backlink"].get("website_name", ""),
            "backlink_blog_url": "",
            "backlink_website_type": state["selected_backlink"].get("website_type", "blog"),
            "backlink_post_type": state["selected_backlink"].get("post_type", "html") or "html",
            "backlink_title_max_characters": state["selected_backlink"].get("title_max_characters", 0) or 0,
            "backlink_min_words": state["selected_backlink"].get("min_words", 0) or 0,
            "backlink_max_characters": state["selected_backlink"].get("max_characters", 0) or 0,
            "backlink_tier_level": "Tier 1",
            "backlink_blog_name": state["selected_backlink"].get("blog_name", "") or state["selected_backlink"].get("account_name", ""),
            "backlink_writer_name": state["selected_backlink"].get("writer_name", ""),
            "backlink_content_guidelines": state["selected_backlink"].get("content_guidelines", ""),
            "brand_topic_mode": state["selected_backlink"].get("brand_topic_mode", "example"),
        }
        is_minor_revision = bool(existing_content and state["change_request"])
        if not state["meta_descriptions"]:
            progress("Generating meta descriptions...")
            state["meta_descriptions"] = generate_backlink_meta_descriptions(
                provider,
                title=state["selected_title"],
                keyword=state["keyword"],
                count=5,
                brand=state["brand"],
                brand_context=brand_context,
                **backlink_context,
                language=state["language"],
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
                keyword=state["keyword"],
                brand=state["brand"],
                backlink_website_name=backlink_context.get("backlink_website_name", ""),
                backlink_website_type=backlink_context.get("backlink_website_type", ""),
                backlink_blog_name=backlink_context.get("backlink_blog_name", ""),
                backlink_content_guidelines=backlink_context.get("backlink_content_guidelines", ""),
                language=state["language"],
                progress_callback=progress,
            )
        if is_minor_revision:
            progress("Applying minor medium content changes...")
            state["content"] = revise_existing_content(
                provider,
                title=state["selected_title"],
                existing_content=existing_content,
                change_request=state["change_request"],
                scope=state["regenerate_scope"],
                output_format=backlink_context.get("backlink_post_type", "html"),
                keyword=state["keyword"],
                brand=state["brand"],
                required_url=state["brand_website_url"],
                required_anchor_text=state["keyword"],
                language=state["language"],
                progress_callback=progress,
            )
        else:
            progress("Generating medium content...")
            state["content"] = generate_backlink_content(
                provider,
                title=state["selected_title"],
                keyword=state["keyword"],
                tone=state["tone"],
                money_site_url=state["brand_website_url"],
                brand=state["brand"],
                brand_context=brand_context,
                suggested_content=state["suggested_content"],
                change_request=_scoped_change_request(state["change_request"], state["regenerate_scope"]),
                required_anchor_text=state["keyword"],
                selected_meta_description=state.get("meta_description", ""),
                **backlink_context,
                language=state["language"],
                progress_callback=progress,
            )
        progress("Content passed validation. Generating tags...")
        state["tag_suggestions"] = generate_ai_content_tags(
            provider,
            title=state["selected_title"],
            keyword=state["keyword"],
            brand=state["brand"],
            content=state["content"],
            minimum=10,
            language=state["language"],
            progress_callback=progress,
        )
        max_words = _int_or_zero(backlink_context.get("backlink_max_characters", 0))
        min_words = _int_or_zero(backlink_context.get("backlink_min_words", 0))
        state["quality_report"] = analyze_generated_content(
            state["content"],
            title=state["selected_title"],
            keyword=state["keyword"],
            meta_description=state["meta_description"],
            min_words=min_words,
            max_words=max_words,
            required_url=state["brand_website_url"],
        )
        state["history_id"] = str(record_generation(
            content_type="Medium Blog",
            brand_name=state["brand"],
            title=state["selected_title"],
            primary_keyword=state["keyword"],
            medium_name=_medium_display_name(state["selected_backlink"]),
            word_count=state["quality_report"]["word_count"],
            meta_description=state["meta_description"],
            tags=state["tag_suggestions"],
            prompt_inputs={
                "tone": state["tone"],
                "language": state["language"],
                "suggested_content": state["suggested_content"],
                "regenerate_scope": state["regenerate_scope"],
                "change_request": state["change_request"],
                "medium": backlink_context,
                "medium_id": state["selected_backlink_id"],
                "brand_link_anchor": state["keyword"],
                "visual": state["visual"],
            },
            content=state["content"],
            quality_report=state["quality_report"],
            history_id=state["history_id"],
        ))
        record_blog(
            brand=state["brand"],
            title=state["selected_title"],
            keyword=state["keyword"],
            supporting_keyword="",
        )
        clear_generation_status(request.form.get("generation_status_token", ""))
        state["step"] = "content"
    except Exception as exc:
        logger.exception("backlink generate_content action failed")
        state["error"] = generation_error_message(
            "An error occurred while generating medium content. Check logs/app.log for details.",
            exc,
        )


def _handle_save_generated_blog(state: dict):
    state["custom_title"] = request.form.get("custom_title", "").strip()
    state["selected_title"] = state["custom_title"] or request.form.get("selected_title", "").strip()
    state["keyword"] = request.form.get("keyword", "").strip()
    state["brand"] = request.form.get("brand", "").strip()
    state["language"] = _language_from_request()
    state["tone"] = request.form.get("tone", "natural").strip() or "natural"
    state["suggested_content"] = request.form.get("suggested_content", "").strip()
    state["change_request"] = request.form.get("change_request", "").strip()
    state["regenerate_scope"] = request.form.get("regenerate_scope", "full").strip() or "full"
    state["brand_website_url"] = request.form.get("brand_website_url", "").strip()
    state["visual"] = request.form.get("visual", "").strip()
    state["post_link"] = _normalize_post_link(request.form.get("post_link", ""))
    state["history_id"] = request.form.get("history_id", "").strip()
    state["selected_backlink_id"] = request.form.get("selected_backlink_id", "").strip()
    state["content"] = request.form.get("content_html", "").strip()
    titles_raw = request.form.get("titles_json", "").strip()
    selected_meta_description = request.form.get("meta_description_choice", "").strip()
    state["meta_description"] = selected_meta_description

    try:
        state["titles"] = json.loads(titles_raw) if titles_raw else []
    except json.JSONDecodeError:
        state["titles"] = []

    if state["selected_backlink_id"].isdigit():
        state["selected_backlink"] = get_backlink(int(state["selected_backlink_id"]))

    if not state["selected_title"]:
        state["error"] = "Please select a title before saving."
        return
    if not state["content"]:
        state["error"] = "There is no generated medium blog content to save."
        return
    if not _valid_post_link(state["post_link"]):
        state["error"] = "Please enter a valid post link before saving."
        state["step"] = "content"
        return

    state["tag_suggestions"] = suggest_content_tags(
        title=state["selected_title"],
        keyword=state["keyword"],
        brand=state["brand"],
        content=state["content"],
        minimum=10,
    )
    max_words = _int_or_zero((state["selected_backlink"] or {}).get("max_characters", 0))
    min_words = _int_or_zero((state["selected_backlink"] or {}).get("min_words", 0))
    state["quality_report"] = analyze_generated_content(
        state["content"],
        title=state["selected_title"],
        keyword=state["keyword"],
        meta_description=state["meta_description"],
        min_words=min_words,
        max_words=max_words,
        required_url=state["brand_website_url"],
    )
    state["history_id"] = str(record_generation(
        content_type="Medium Blog",
        brand_name=state["brand"],
        title=state["selected_title"],
        primary_keyword=state["keyword"],
        medium_name=_medium_display_name(state["selected_backlink"] or {}),
        word_count=state["quality_report"].get("word_count", count_html_words(state["content"])),
        meta_description=state["meta_description"],
        post_link=state["post_link"],
        tags=state["tag_suggestions"],
        prompt_inputs={
            "tone": state["tone"],
            "language": state["language"],
            "suggested_content": state["suggested_content"],
            "manual_save": True,
            "medium_id": state["selected_backlink_id"],
            "brand_link_anchor": state["keyword"],
            "visual": state["visual"],
        },
        content=state["content"],
        quality_report=state["quality_report"],
        history_id=state["history_id"],
    ))
    record_blog(
        brand=state["brand"],
        title=state["selected_title"],
        keyword=state["keyword"],
        supporting_keyword="",
    )
    state["success"] = "Generated medium blog saved to history."
    state["step"] = "content"


def _scoped_change_request(change_request: str, scope: str) -> str:
    cleaned = (change_request or "").strip()
    cleaned_scope = (scope or "full").strip().lower()
    scope_labels = {
        "intro": "Regenerate only the first paragraph/introduction and keep the required brand URL exactly once anywhere in the article.",
        "section": "Regenerate the weakest body section while keeping the selected medium format and brand URL rule.",
        "conclusion": "Regenerate only the ending section without adding the brand URL again.",
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


def _language_from_request() -> str:
    return normalize_language(request.form.get("language", get_default_language()))


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
