import json

from flask import render_template, request

from database import get_brand_context, get_generation_history_item, list_brand_names, list_checklist_items, record_generation, record_page, upsert_brand
from generators.content_generator import count_html_words, revise_existing_content
from generators.page_generator import generate_page_content, generate_page_meta_description, generate_page_title
from generators.simple_page_generator import (
    generate_simple_page_content,
    generate_simple_page_meta_descriptions,
    generate_simple_page_title,
)
from logger import logger

from app.controllers.helpers import base_template_context
from app.services.content_quality_service import analyze_generated_content
from app.services.generation_status_service import clear_generation_status, publish_generation_prompt, publish_generation_status
from app.services.locale_settings import get_default_language, language_options, normalize_language
from app.services.provider_service import generation_error_message, get_provider
from app.services.word_limit_settings import get_page_word_limits


def page_generator():
    state = {
        "keyword": "",
        "brand": "",
        "language": get_default_language(),
        "supporting_keywords": "",
        "page_type": "",
        "expectations": "",
        "page_title": "",
        "change_request": "",
        "meta_description": "",
        "page_content": "",
        "history_id": "",
        "quality_report": None,
        "regenerate_scope": "full",
        "image_count": 0,
        "error": None,
        "success": None,
        "brand_names": list_brand_names(),
        "content_checklist_items": list_checklist_items("page", active_only=True),
        "language_options": language_options(get_default_language()),
    }

    edit_history_id = request.args.get("edit_history_id", "").strip()
    if request.method == "GET" and edit_history_id.isdigit():
        _load_page_history_item(state, int(edit_history_id))

    if request.method == "POST":
        action = request.form.get("action", "generate_page_title").strip()
        state["keyword"] = request.form.get("keyword", "").strip()
        state["brand"] = request.form.get("brand", "").strip()
        state["language"] = _language_from_request()
        state["supporting_keywords"] = request.form.get("supporting_keywords", "").strip()
        state["page_type"] = request.form.get("page_type", "").strip()
        state["expectations"] = request.form.get("expectations", "").strip()
        state["change_request"] = request.form.get("change_request", "").strip()
        state["regenerate_scope"] = request.form.get("regenerate_scope", "full").strip() or "full"
        state["page_title"] = request.form.get("page_title", "").strip()
        state["meta_description"] = request.form.get("meta_description", "").strip()
        state["page_content"] = request.form.get("page_content", "").strip()
        state["history_id"] = request.form.get("history_id", "").strip()
        state["image_count"] = _int_or_zero(request.form.get("image_count", "0"))

        if action == "save_generated_blog":
            _save_page_generation(state)
        elif not state["keyword"]:
            state["error"] = "Please enter a keyword."
        else:
            try:
                provider = get_provider()
                if state["brand"]:
                    upsert_brand(state["brand"])
                brand_context = get_brand_context(state["brand"])
                min_words, max_words = get_page_word_limits()
                progress = _progress_callback("Page", request.form.get("generation_status_token", ""))
                is_minor_revision = bool(state["page_content"] and state["change_request"])
                if is_minor_revision:
                    progress("Applying minor page changes...")
                    state["page_content"] = revise_existing_content(
                        provider,
                        title=state["page_title"] or state["keyword"],
                        existing_content=state["page_content"],
                        change_request=state["change_request"],
                        scope=state["regenerate_scope"],
                        output_format="html",
                        keyword=state["keyword"],
                        brand=state["brand"],
                        language=state["language"],
                        progress_callback=progress,
                    )
                    _record_completed_page(state, min_words, max_words)
                elif action == "generate_page_meta" and not state["page_title"]:
                    state["error"] = "Please generate the page title first."
                elif action == "generate_page_content" and not state["page_title"]:
                    state["error"] = "Please generate the page title first."
                elif action == "generate_page_content" and not state["meta_description"]:
                    state["error"] = "Please generate the meta description first."
                elif action in {"generate_page_title", "generate_page"} or not state["page_title"]:
                    progress("Generating page title...")
                    state["page_title"] = generate_page_title(
                        provider,
                        keyword=state["keyword"],
                        brand=state["brand"],
                        supporting_keywords=state["supporting_keywords"],
                        page_type=state["page_type"],
                        expectations=state["expectations"],
                        brand_context=brand_context,
                        language=state["language"],
                        progress_callback=progress,
                    )
                elif action == "generate_page_meta" or not state["meta_description"]:
                    progress("Generating page meta description...")
                    state["meta_description"] = generate_page_meta_description(
                        provider,
                        keyword=state["keyword"],
                        title=state["page_title"],
                        brand=state["brand"],
                        supporting_keywords=state["supporting_keywords"],
                        page_type=state["page_type"],
                        expectations=state["expectations"],
                        brand_context=brand_context,
                        language=state["language"],
                        progress_callback=progress,
                    )
                else:
                    progress("Generating page content...")
                    result = generate_page_content(
                        provider,
                        keyword=state["keyword"],
                        title=state["page_title"],
                        meta_description=state["meta_description"],
                        brand=state["brand"],
                        supporting_keywords=state["supporting_keywords"],
                        page_type=state["page_type"],
                        expectations=state["expectations"],
                        brand_context=brand_context,
                        change_request=_scoped_change_request(state["change_request"], state["regenerate_scope"]),
                        min_words=min_words,
                        max_words=max_words,
                        language=state["language"],
                        progress_callback=progress,
                    )
                    state["page_content"] = result.get("content", "")
                    state["image_count"] = result.get("image_count", 0)
                    _record_completed_page(state, min_words, max_words)
                clear_generation_status(request.form.get("generation_status_token", ""))
            except Exception as exc:
                logger.exception("page_generator action failed")
                state["error"] = generation_error_message(
                    "An error occurred while generating the page. Check logs/app.log for details.",
                    exc,
                )

    state["language_options"] = language_options(state["language"])
    return render_template("page_generator.html", **base_template_context(), **state)


def simple_page_generator():
    state = {
        "brand": "",
        "language": get_default_language(),
        "page_title": "",
        "page_type": "",
        "expectations": "",
        "generated_title": "",
        "meta_descriptions": [],
        "generated_content": "",
        "history_id": "",
        "quality_report": None,
        "change_request": "",
        "regenerate_scope": "full",
        "error": None,
        "success": None,
        "brand_names": list_brand_names(),
        "content_checklist_items": list_checklist_items("page", active_only=True),
        "language_options": language_options(get_default_language()),
    }

    edit_history_id = request.args.get("edit_history_id", "").strip()
    if request.method == "GET" and edit_history_id.isdigit():
        _load_simple_page_history_item(state, int(edit_history_id))

    if request.method == "POST":
        action = request.form.get("action", "generate_simple_page_title").strip()
        state["brand"] = request.form.get("brand", "").strip()
        state["language"] = _language_from_request()
        state["page_title"] = request.form.get("page_title", "").strip()
        state["page_type"] = request.form.get("page_type", "").strip()
        state["expectations"] = request.form.get("expectations", "").strip()
        state["change_request"] = request.form.get("change_request", "").strip()
        state["regenerate_scope"] = request.form.get("regenerate_scope", "full").strip() or "full"
        state["generated_title"] = request.form.get("generated_title", "").strip()
        state["generated_content"] = request.form.get("generated_content", "").strip()
        state["history_id"] = request.form.get("history_id", "").strip()
        state["meta_descriptions"] = _parse_meta_descriptions(request.form.get("meta_descriptions_json", "").strip())

        if action == "save_generated_blog":
            _save_simple_page_generation(state)
        elif not state["page_title"]:
            state["error"] = "Please enter the page title or page name."
        else:
            try:
                provider = get_provider()
                if state["brand"]:
                    upsert_brand(state["brand"])
                brand_context = get_brand_context(state["brand"])
                min_words, max_words = get_page_word_limits()
                progress = _progress_callback("Simple page", request.form.get("generation_status_token", ""))
                is_minor_revision = bool(state["generated_content"] and state["change_request"])
                if is_minor_revision:
                    progress("Applying minor simple page changes...")
                    state["generated_content"] = revise_existing_content(
                        provider,
                        title=state["generated_title"] or state["page_title"],
                        existing_content=state["generated_content"],
                        change_request=state["change_request"],
                        scope=state["regenerate_scope"],
                        output_format="html",
                        keyword=state["page_title"],
                        brand=state["brand"],
                        language=state["language"],
                        progress_callback=progress,
                    )
                    if not state["generated_title"]:
                        state["generated_title"] = state["page_title"]
                    selected_meta = state["meta_descriptions"][0].get("text", "") if state["meta_descriptions"] else ""
                    _record_completed_simple_page(state, selected_meta, min_words, max_words)
                elif action == "generate_simple_page_meta" and not state["generated_title"]:
                    state["error"] = "Please generate the simple page title first."
                elif action == "generate_simple_page_content" and not state["generated_title"]:
                    state["error"] = "Please generate the simple page title first."
                elif action == "generate_simple_page_content" and not state["meta_descriptions"]:
                    state["error"] = "Please generate the meta descriptions first."
                elif action in {"generate_simple_page_title", "generate_simple_page"} or not state["generated_title"]:
                    progress("Generating simple page title...")
                    state["generated_title"] = generate_simple_page_title(
                        provider,
                        page_title=state["page_title"],
                        page_type=state["page_type"],
                        brand=state["brand"],
                        expectations=state["expectations"],
                        brand_context=brand_context,
                        language=state["language"],
                        progress_callback=progress,
                    )
                elif action == "generate_simple_page_meta" or not state["meta_descriptions"]:
                    progress("Generating simple page meta descriptions...")
                    state["meta_descriptions"] = generate_simple_page_meta_descriptions(
                        provider,
                        page_title=state["page_title"],
                        generated_title=state["generated_title"],
                        page_type=state["page_type"],
                        brand=state["brand"],
                        expectations=state["expectations"],
                        brand_context=brand_context,
                        language=state["language"],
                        progress_callback=progress,
                    )
                else:
                    selected_meta = state["meta_descriptions"][0].get("text", "") if state["meta_descriptions"] else ""
                    progress("Generating simple page content...")
                    state["generated_content"] = generate_simple_page_content(
                        provider,
                        page_title=state["page_title"],
                        generated_title=state["generated_title"],
                        selected_meta_description=selected_meta,
                        page_type=state["page_type"],
                        brand=state["brand"],
                        expectations=state["expectations"],
                        brand_context=brand_context,
                        change_request=_scoped_change_request(state["change_request"], state["regenerate_scope"]),
                        min_words=min_words,
                        max_words=max_words,
                        language=state["language"],
                        progress_callback=progress,
                    )
                    _record_completed_simple_page(state, selected_meta, min_words, max_words)
                clear_generation_status(request.form.get("generation_status_token", ""))
            except Exception as exc:
                logger.exception("simple_page_generator action failed")
                state["error"] = generation_error_message(
                    "An error occurred while generating the simple page. Check logs/app.log for details.",
                    exc,
                )

    state["language_options"] = language_options(state["language"])
    return render_template("simple_page_generator.html", **base_template_context(), **state)


def _record_completed_page(state: dict, min_words: int, max_words: int):
    if not state["page_content"]:
        return
    state["quality_report"] = analyze_generated_content(
        state["page_content"],
        title=state["page_title"],
        keyword=state["keyword"],
        meta_description=state["meta_description"],
        min_words=min_words,
        max_words=max_words,
    )
    state["history_id"] = str(record_generation(
        content_type="Page",
        brand_name=state["brand"],
        title=state["page_title"],
        primary_keyword=state["keyword"],
        word_count=state["quality_report"]["word_count"],
        meta_description=state["meta_description"],
        prompt_inputs={
            "page_type": state["page_type"],
            "language": state["language"],
            "supporting_keywords": state["supporting_keywords"],
            "expectations": state["expectations"],
            "image_count": state["image_count"],
            "regenerate_scope": state["regenerate_scope"],
            "change_request": state["change_request"],
        },
        content=state["page_content"],
        quality_report=state["quality_report"],
        history_id=state["history_id"],
    ))
    record_page(
        brand=state["brand"],
        keyword=state["keyword"],
        page_title=state["page_title"],
        page_type=state["page_type"],
        supporting_keywords=state["supporting_keywords"],
        expectations=state["expectations"],
    )


def _record_completed_simple_page(state: dict, selected_meta: str, min_words: int, max_words: int):
    if not state["generated_content"]:
        return
    title = state["generated_title"] or state["page_title"]
    state["quality_report"] = analyze_generated_content(
        state["generated_content"],
        title=title,
        keyword=state["page_title"],
        meta_description=selected_meta,
        min_words=min_words,
        max_words=max_words,
    )
    state["history_id"] = str(record_generation(
        content_type="Simple Page",
        brand_name=state["brand"],
        title=title,
        primary_keyword=state["page_title"],
        word_count=state["quality_report"]["word_count"],
        meta_description=selected_meta,
        prompt_inputs={
            "page_type": state["page_type"],
            "language": state["language"],
            "expectations": state["expectations"],
            "regenerate_scope": state["regenerate_scope"],
            "change_request": state["change_request"],
        },
        content=state["generated_content"],
        quality_report=state["quality_report"],
        history_id=state["history_id"],
    ))
    record_page(
        brand=state["brand"],
        keyword=state["page_title"],
        page_title=title,
        page_type=state["page_type"] or "simple page",
        supporting_keywords="",
        expectations=state["expectations"],
    )


def _save_page_generation(state: dict):
    if not state["page_title"]:
        state["error"] = "There is no generated page title to save."
        return
    if not state["page_content"]:
        state["error"] = "There is no generated page content to save."
        return

    min_words, max_words = get_page_word_limits()
    state["quality_report"] = analyze_generated_content(
        state["page_content"],
        title=state["page_title"],
        keyword=state["keyword"],
        meta_description=state["meta_description"],
        min_words=min_words,
        max_words=max_words,
    )
    state["history_id"] = str(record_generation(
        content_type="Page",
        brand_name=state["brand"],
        title=state["page_title"],
        primary_keyword=state["keyword"],
        word_count=state["quality_report"].get("word_count", count_html_words(state["page_content"])),
        meta_description=state["meta_description"],
        prompt_inputs={
            "page_type": state["page_type"],
            "language": state["language"],
            "supporting_keywords": state["supporting_keywords"],
            "expectations": state["expectations"],
            "image_count": state["image_count"],
            "manual_save": True,
        },
        content=state["page_content"],
        quality_report=state["quality_report"],
        history_id=state.get("history_id", ""),
    ))
    record_page(
        brand=state["brand"],
        keyword=state["keyword"],
        page_title=state["page_title"],
        page_type=state["page_type"],
        supporting_keywords=state["supporting_keywords"],
        expectations=state["expectations"],
    )
    state["success"] = "Generated page saved to history."


def _save_simple_page_generation(state: dict):
    title = state["generated_title"] or state["page_title"]
    selected_meta = state["meta_descriptions"][0].get("text", "") if state["meta_descriptions"] else ""
    if not title:
        state["error"] = "There is no generated simple page title to save."
        return
    if not state["generated_content"]:
        state["error"] = "There is no generated simple page content to save."
        return

    min_words, max_words = get_page_word_limits()
    state["quality_report"] = analyze_generated_content(
        state["generated_content"],
        title=title,
        keyword=state["page_title"],
        meta_description=selected_meta,
        min_words=min_words,
        max_words=max_words,
    )
    state["history_id"] = str(record_generation(
        content_type="Simple Page",
        brand_name=state["brand"],
        title=title,
        primary_keyword=state["page_title"],
        word_count=state["quality_report"].get("word_count", count_html_words(state["generated_content"])),
        meta_description=selected_meta,
        prompt_inputs={
            "page_type": state["page_type"],
            "language": state["language"],
            "expectations": state["expectations"],
            "manual_save": True,
        },
        content=state["generated_content"],
        quality_report=state["quality_report"],
        history_id=state.get("history_id", ""),
    ))
    record_page(
        brand=state["brand"],
        keyword=state["page_title"],
        page_title=title,
        page_type=state["page_type"] or "simple page",
        supporting_keywords="",
        expectations=state["expectations"],
    )
    state["success"] = "Generated simple page saved to history."


def _load_page_history_item(state: dict, history_id: int):
    item = get_generation_history_item(history_id)
    if not item:
        return
    prompt_inputs = _loads(item.get("prompt_inputs", "{}"))
    state["history_id"] = str(item.get("id", ""))
    state["brand"] = item.get("brand_name", "") or ""
    state["keyword"] = item.get("primary_keyword", "") or ""
    state["language"] = prompt_inputs.get("language", state["language"]) or "English"
    state["supporting_keywords"] = prompt_inputs.get("supporting_keywords", "")
    state["page_type"] = prompt_inputs.get("page_type", "")
    state["expectations"] = prompt_inputs.get("expectations", "")
    state["change_request"] = prompt_inputs.get("change_request", "")
    state["regenerate_scope"] = prompt_inputs.get("regenerate_scope", "full") or "full"
    state["page_title"] = item.get("title", "") or ""
    state["meta_description"] = item.get("meta_description", "") or ""
    state["page_content"] = item.get("content", "") or ""
    state["image_count"] = _int_or_zero(prompt_inputs.get("image_count", 0))
    state["quality_report"] = _loads(item.get("quality_report", "{}"))


def _load_simple_page_history_item(state: dict, history_id: int):
    item = get_generation_history_item(history_id)
    if not item:
        return
    prompt_inputs = _loads(item.get("prompt_inputs", "{}"))
    meta_description = item.get("meta_description", "") or ""
    state["history_id"] = str(item.get("id", ""))
    state["brand"] = item.get("brand_name", "") or ""
    state["language"] = prompt_inputs.get("language", state["language"]) or "English"
    state["page_title"] = item.get("primary_keyword", "") or item.get("title", "") or ""
    state["page_type"] = prompt_inputs.get("page_type", "")
    state["expectations"] = prompt_inputs.get("expectations", "")
    state["change_request"] = prompt_inputs.get("change_request", "")
    state["regenerate_scope"] = prompt_inputs.get("regenerate_scope", "full") or "full"
    state["generated_title"] = item.get("title", "") or ""
    state["meta_descriptions"] = [{"text": meta_description, "character_count": len(meta_description)}] if meta_description else []
    state["generated_content"] = item.get("content", "") or ""
    state["quality_report"] = _loads(item.get("quality_report", "{}"))


def _parse_meta_descriptions(raw: str) -> list[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


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


def _scoped_change_request(change_request: str, scope: str) -> str:
    cleaned = (change_request or "").strip()
    cleaned_scope = (scope or "full").strip().lower()
    scope_labels = {
        "intro": "Regenerate only the introduction while keeping the rest of the page consistent.",
        "meta": "Regenerate the meta description options while keeping the page content aligned.",
        "section": "Regenerate the weakest body section and keep the surrounding sections consistent.",
        "conclusion": "Regenerate only the final section while keeping the page body consistent.",
    }
    prefix = scope_labels.get(cleaned_scope, "")
    if not prefix:
        return cleaned
    return f"{prefix}\n{cleaned}".strip()


def _progress_callback(label: str, token: str):
    cleaned_label = (label or "Generation").strip()

    def publish(message: str, kind: str = "status"):
        if kind == "prompt":
            publish_generation_prompt(token, message)
            return
        publish_generation_status(token, f"{cleaned_label}: {message}")

    return publish
