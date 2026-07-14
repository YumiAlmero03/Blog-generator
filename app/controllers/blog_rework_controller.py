import json
import re

from flask import render_template, request

from app.controllers.helpers import base_template_context
from app.services.content_quality_service import analyze_generated_content
from app.services.generation_log_service import append_generation_log, generation_log_json, parse_generation_log
from app.services.generation_status_service import clear_generation_status, publish_generation_draft, publish_generation_prompt, publish_generation_status
from app.services.locale_settings import get_default_language, language_options, normalize_language
from app.services.provider_service import generation_error_message, get_provider
from app.services.word_limit_settings import get_blog_word_limits, get_page_word_limits
from database import get_brand_context, list_brand_names, record_blog, record_generation, upsert_brand
from generators.blog_rework_generator import generate_blog_rework
from generators.content_generator import count_html_words, suggest_content_tags
from logger import logger


def blog_rework_generator():
    state = _default_state()
    if request.method == "POST":
        action = request.form.get("action", "generate_rework").strip()
        if action == "save_blog_rework":
            _handle_save_blog_rework(state)
        else:
            _handle_generate_blog_rework(state)

    state["language_options"] = language_options(state["language"])
    state["generation_log_json"] = generation_log_json(state.get("generation_log", []))
    return render_template("blog_rework_generator.html", **base_template_context(), **state)


def _default_state() -> dict:
    return {
        "source_url": "",
        "source_content": "",
        "rework_content_type": "blog",
        "source_title": "",
        "old_brand": "",
        "brand": "",
        "language": get_default_language(),
        "tone": "natural",
        "selected_title": "",
        "keyword": "",
        "supporting_keyword": "",
        "manual_supporting_keywords": "",
        "meta_descriptions": [],
        "meta_description": "",
        "visual": "",
        "content": "",
        "quality_report": None,
        "tag_suggestions": [],
        "history_id": "",
        "generation_log": [],
        "generation_log_json": "[]",
        "error": None,
        "success": None,
        "brand_names": list_brand_names(),
        "language_options": language_options(get_default_language()),
    }


def _handle_generate_blog_rework(state: dict) -> None:
    state["source_url"] = request.form.get("source_url", "").strip()
    state["source_content"] = request.form.get("source_content_html", "").strip()
    state["rework_content_type"] = _rework_content_type_from_request()
    state["manual_supporting_keywords"] = request.form.get("manual_supporting_keywords", "").strip()
    state["old_brand"] = request.form.get("old_brand", "").strip()
    state["brand"] = request.form.get("brand", "").strip()
    state["language"] = _language_from_request()
    state["tone"] = request.form.get("tone", "natural").strip() or "natural"
    state["generation_log"] = parse_generation_log(request.form.get("generation_log_json", ""))
    state["generation_log_json"] = generation_log_json(state["generation_log"])
    if not state["source_url"] and not _has_readable_source_content(state["source_content"]):
        state["error"] = "Please enter a blog link or paste the source content to rework."
        return

    if state["brand"]:
        upsert_brand(state["brand"])

    try:
        provider = get_provider()
        min_words, max_words = _rework_word_limits(state["rework_content_type"])
        progress = _progress_callback("Blog Rework", request.form.get("generation_status_token", ""), state["generation_log"])
        progress("Starting blog rework...")
        result = generate_blog_rework(
            provider,
            source_url=state["source_url"],
            source_content=state["source_content"],
            content_type=state["rework_content_type"],
            manual_supporting_keywords=state["manual_supporting_keywords"],
            old_brand=state["old_brand"],
            brand=state["brand"],
            tone=state["tone"],
            language=state["language"],
            min_words=min_words,
            max_words=max_words,
            brand_context=get_brand_context(state["brand"]),
            progress_callback=progress,
        )
        _apply_result(state, result)
        state["quality_report"] = analyze_generated_content(
            state["content"],
            title=state["selected_title"],
            keyword=state["keyword"],
            meta_description=state["meta_description"],
            min_words=min_words,
            max_words=max_words,
        )
        _record_blog_rework(state, min_words, max_words)
        progress("Generation complete.")
        clear_generation_status(request.form.get("generation_status_token", ""))
    except Exception as exc:
        logger.exception("blog rework generation failed")
        append_generation_log(state["generation_log"], "error", str(exc) or "Generation failed.")
        state["error"] = generation_error_message(
            "Could not generate the blog rework. Check logs/app.log for details.",
            exc,
        )


def _handle_save_blog_rework(state: dict) -> None:
    state["source_url"] = request.form.get("source_url", "").strip()
    state["source_content"] = request.form.get("source_content_html", "").strip()
    state["source_title"] = request.form.get("source_title", "").strip()
    state["rework_content_type"] = _rework_content_type_from_request()
    state["manual_supporting_keywords"] = request.form.get("manual_supporting_keywords", "").strip()
    state["old_brand"] = request.form.get("old_brand", "").strip()
    state["brand"] = request.form.get("brand", "").strip()
    state["language"] = _language_from_request()
    state["tone"] = request.form.get("tone", "natural").strip() or "natural"
    state["selected_title"] = request.form.get("selected_title", "").strip()
    state["keyword"] = request.form.get("keyword", "").strip()
    state["supporting_keyword"] = request.form.get("supporting_keyword", "").strip()
    state["meta_description"] = request.form.get("meta_description_choice", "").strip()
    state["visual"] = request.form.get("visual", "").strip()
    state["content"] = request.form.get("content_html", "").strip()
    state["history_id"] = request.form.get("history_id", "").strip()
    state["meta_descriptions"] = _json_list(request.form.get("meta_descriptions_json", ""))
    state["tag_suggestions"] = _tags_from_raw(request.form.get("tags_json", ""))
    state["generation_log"] = parse_generation_log(request.form.get("generation_log_json", ""))
    state["generation_log_json"] = generation_log_json(state["generation_log"])

    if not state["selected_title"] or not state["content"]:
        state["error"] = "There is no generated rework to save."
        return

    min_words, max_words = _rework_word_limits(state["rework_content_type"])
    if not state["tag_suggestions"]:
        state["tag_suggestions"] = suggest_content_tags(
            title=state["selected_title"],
            keyword=state["keyword"],
            supporting_keyword=state["supporting_keyword"],
            brand=state["brand"],
            content=state["content"],
            minimum=10,
        )
    state["quality_report"] = analyze_generated_content(
        state["content"],
        title=state["selected_title"],
        keyword=state["keyword"],
        meta_description=state["meta_description"],
        min_words=min_words,
        max_words=max_words,
    )
    _record_blog_rework(state, min_words, max_words)
    state["success"] = "Blog rework saved to history."


def _apply_result(state: dict, result: dict) -> None:
    state["source_url"] = result.get("source_url", state["source_url"])
    state["source_content"] = result.get("source_content", state.get("source_content", ""))
    state["rework_content_type"] = result.get("content_type", state.get("rework_content_type", "blog"))
    state["source_title"] = result.get("source_title", "")
    state["selected_title"] = result.get("title", "")
    state["keyword"] = result.get("keyword", "")
    state["supporting_keyword"] = result.get("supporting_keyword", "")
    state["manual_supporting_keywords"] = result.get("manual_supporting_keywords", state.get("manual_supporting_keywords", ""))
    state["meta_descriptions"] = result.get("meta_descriptions", [])
    state["meta_description"] = result.get("meta_description", "")
    state["visual"] = result.get("visual", "")
    state["content"] = result.get("content", "")
    state["tag_suggestions"] = result.get("tag_suggestions", [])


def _record_blog_rework(state: dict, min_words: int, max_words: int) -> None:
    state["history_id"] = str(record_generation(
        content_type="Blog Rework",
        brand_name=state["brand"],
        title=state["selected_title"],
        primary_keyword=state["keyword"],
        word_count=state["quality_report"].get("word_count", count_html_words(state["content"])) if state["quality_report"] else count_html_words(state["content"]),
        meta_description=state["meta_description"],
        tags=state["tag_suggestions"],
        prompt_inputs={
            "source_url": state["source_url"],
            "source_type": "url" if state["source_url"] else "pasted_content",
            "rework_content_type": state.get("rework_content_type", "blog"),
            "source_content_character_count": len(_readable_source_content(state.get("source_content", ""))),
            "source_title": state["source_title"],
            "old_brand": state["old_brand"],
            "supporting_keyword": state["supporting_keyword"],
            "manual_supporting_keywords": state.get("manual_supporting_keywords", ""),
            "language": state["language"],
            "tone": state["tone"],
            "visual": state["visual"],
            "min_words": min_words,
            "max_words": max_words,
            "generation_log": state.get("generation_log", []),
        },
        content=state["content"],
        quality_report=state["quality_report"] or {},
        history_id=state["history_id"],
    ))
    record_blog(
        brand=state["brand"],
        title=state["selected_title"],
        keyword=state["keyword"],
        supporting_keyword=state["supporting_keyword"],
    )


def _language_from_request() -> str:
    return normalize_language(request.form.get("language", get_default_language()))


def _rework_content_type_from_request() -> str:
    value = request.form.get("rework_content_type", "blog").strip().lower()
    return value if value in {"blog", "page"} else "blog"


def _rework_word_limits(content_type: str) -> tuple[int, int]:
    if content_type == "page":
        return get_page_word_limits()
    return get_blog_word_limits()


def _json_list(raw: str) -> list:
    try:
        parsed = json.loads(raw) if raw else []
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _tags_from_raw(raw: str) -> list[str]:
    tags = []
    for item in _json_list(raw):
        cleaned = str(item or "").strip()
        if cleaned:
            tags.append(cleaned)
    return tags


def _progress_callback(label: str, token: str, log_entries: list[dict] | None = None):
    cleaned_label = (label or "Generation").strip()

    def publish(message: str, kind: str = "status"):
        if log_entries is not None:
            append_generation_log(log_entries, kind, message)
        if kind == "prompt":
            publish_generation_prompt(token, message)
            return
        if kind == "draft":
            publish_generation_draft(token, message, f"{cleaned_label}: Draft available while retrying...")
            return
        publish_generation_status(token, f"{cleaned_label}: {message}")

    publish.generation_token = token
    return publish


def _readable_source_content(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", str(value or ""))
    return " ".join(without_tags.split()).strip()


def _has_readable_source_content(value: str) -> bool:
    return bool(_readable_source_content(value))
