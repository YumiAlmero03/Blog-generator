import json

from flask import render_template, request

from database import get_brand_context, get_generation_history_item, get_setting, list_brand_names, record_blog, record_generation, upsert_brand
from generators.content_generator import count_html_words, generate_ai_content_tags, generate_blog_visual_ideas, generate_content, revise_existing_content, suggest_content_tags
from generators.meta_description_generator import generate_meta_descriptions
from generators.title_generator import generate_titles
from logger import logger

from app.controllers.helpers import base_template_context
from app.services.content_quality_service import analyze_generated_content
from app.services.generation_status_service import clear_generation_status, publish_generation_prompt, publish_generation_status
from app.services.provider_service import generation_error_message, get_provider
from app.services.word_limit_settings import get_blog_word_limits


def index():
    state = {
        "keyword": "",
        "brand": "",
        "supporting_keyword": "",
        "tone": "natural",
        "count": 10,
        "titles": [],
        "selected_title": "",
        "meta_descriptions": [],
        "meta_description": "",
        "content": "",
        "visual": "",
        "quality_report": None,
        "tag_suggestions": [],
        "change_request": "",
        "regenerate_scope": "full",
        "error": None,
        "success": None,
        "step": "title",
        "include_money_site": False,
        "money_site_url": "",
        "links": [],
        "history_id": "",
        "brand_names": list_brand_names(),
    }
    selected_brand = request.args.get("brand", "").strip()
    if request.method == "GET" and selected_brand:
        state["brand"] = selected_brand
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

    if not state["money_site_url"]:
        state["money_site_url"] = get_setting("money_site", "")

    return render_template("index.html", **base_template_context(), **state)


def _handle_generate_titles(state: dict):
    state["keyword"] = request.form.get("keyword", "").strip()
    state["brand"] = request.form.get("brand", "").strip()
    state["supporting_keyword"] = request.form.get("supporting_keyword", "").strip()
    state["tone"] = request.form.get("tone", "natural").strip() or "natural"
    count_raw = request.form.get("count", "10").strip()

    if not state["keyword"]:
        state["error"] = "Please enter one or more keywords."
        return

    if state["brand"]:
        upsert_brand(state["brand"])

    try:
        state["count"] = int(count_raw)
    except ValueError:
        state["count"] = 10

    try:
        provider = get_provider()
        brand_context = get_brand_context(state["brand"])
        progress = _progress_callback("Title", request.form.get("generation_status_token", ""))
        progress("Starting title generation...")
        state["titles"] = generate_titles(
            provider,
            keyword=state["keyword"],
            tone=state["tone"],
            count=state["count"],
            brand=state["brand"],
            brand_context=brand_context,
            progress_callback=progress,
        )
        progress("Titles passed validation.")
        state["step"] = "title"
    except Exception as exc:
        logger.exception("generate_titles action failed")
        state["error"] = generation_error_message(
            "An error occurred while generating titles. Check logs/app.log for details.",
            exc,
        )


def _load_history_item(state: dict, history_id: int):
    item = get_generation_history_item(history_id)
    if not item:
        return
    prompt_inputs = _loads(item.get("prompt_inputs", "{}"))
    state["history_id"] = str(item.get("id", ""))
    state["brand"] = item.get("brand_name", "") or ""
    state["keyword"] = item.get("primary_keyword", "") or ""
    state["supporting_keyword"] = prompt_inputs.get("supporting_keyword", "")
    state["tone"] = prompt_inputs.get("tone", state["tone"])
    state["include_money_site"] = bool(prompt_inputs.get("include_money_site", False))
    state["links"] = prompt_inputs.get("links", [])
    state["titles"] = [item.get("title", "")] if item.get("title") else []
    state["selected_title"] = item.get("title", "") or ""
    state["meta_description"] = item.get("meta_description", "") or ""
    state["meta_descriptions"] = [{"text": state["meta_description"], "character_count": len(state["meta_description"])}] if state["meta_description"] else []
    state["content"] = item.get("content", "") or ""
    state["visual"] = prompt_inputs.get("visual", "") or ""
    state["quality_report"] = _loads(item.get("quality_report", "{}"))
    state["tag_suggestions"] = [tag.strip() for tag in (item.get("tags", "") or "").split(",") if tag.strip()]
    state["step"] = "content"


def _handle_generate_content(state: dict):
    state["selected_title"] = request.form.get("selected_title", "").strip()
    state["keyword"] = request.form.get("keyword", "").strip()
    state["brand"] = request.form.get("brand", "").strip()
    state["supporting_keyword"] = request.form.get("supporting_keyword", "").strip()
    state["tone"] = request.form.get("tone", "natural").strip() or "natural"
    state["change_request"] = request.form.get("change_request", "").strip()
    state["regenerate_scope"] = request.form.get("regenerate_scope", "full").strip() or "full"
    state["include_money_site"] = request.form.get("include_money_site") == "1"
    state["history_id"] = request.form.get("history_id", "").strip()
    titles_raw = request.form.get("titles_json", "").strip()
    meta_descriptions_raw = request.form.get("meta_descriptions_json", "").strip()
    selected_meta_description = request.form.get("meta_description_choice", "").strip()
    existing_content = request.form.get("content_html", "").strip()
    state["visual"] = request.form.get("visual", "").strip()

    state["links"] = _extract_links_from_request()

    if not state["selected_title"]:
        state["error"] = "Please select a title first."
        return

    try:
        state["titles"] = _json_list(titles_raw)
        state["meta_descriptions"] = _json_list(meta_descriptions_raw)
        provider = get_provider()
        progress = _progress_callback("Blog", request.form.get("generation_status_token", ""))
        if state["brand"]:
            upsert_brand(state["brand"])
        state["money_site_url"] = get_setting("money_site", "")
        min_words, max_words = get_blog_word_limits()
        brand_context = get_brand_context(state["brand"])
        is_minor_revision = bool(existing_content and state["change_request"])
        if not is_minor_revision:
            progress("Generating meta descriptions...")
            state["meta_descriptions"] = generate_meta_descriptions(
                provider,
                title=state["selected_title"],
                keyword=state["keyword"],
                count=5,
                brand=state["brand"],
                brand_context=brand_context,
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
            state["visual"] = _visual_text(generate_blog_visual_ideas(
                provider,
                title=state["selected_title"],
                keyword=state["keyword"],
                brand=state["brand"],
                context=brand_context,
                count=2,
                progress_callback=progress,
            ))
        if is_minor_revision:
            progress("Applying minor article changes...")
            state["content"] = revise_existing_content(
                provider,
                title=state["selected_title"],
                existing_content=existing_content,
                change_request=state["change_request"],
                scope=state["regenerate_scope"],
                output_format="html",
                keyword=state["keyword"],
                brand=state["brand"],
                required_url=state["money_site_url"] if state["include_money_site"] else "",
                progress_callback=progress,
            )
        else:
            scoped_change_request = _scoped_change_request(state["change_request"], state["regenerate_scope"])
            progress("Generating article content...")
            state["content"] = generate_content(
                provider,
                title=state["selected_title"],
                keyword=state["keyword"],
                supporting_keyword=state["supporting_keyword"],
                tone=state["tone"],
                links=state["links"],
                money_site_url=state["money_site_url"] if state["include_money_site"] else "",
                brand=state["brand"],
                brand_context=brand_context,
                change_request=scoped_change_request,
                min_words=min_words,
                max_words=max_words,
                progress_callback=progress,
            )
        progress("Content passed validation. Generating tags...")
        state["tag_suggestions"] = generate_ai_content_tags(
            provider,
            title=state["selected_title"],
            keyword=state["keyword"],
            supporting_keyword=state["supporting_keyword"],
            brand=state["brand"],
            content=state["content"],
            minimum=10,
            progress_callback=progress,
        )
        state["quality_report"] = analyze_generated_content(
            state["content"],
            title=state["selected_title"],
            keyword=state["keyword"],
            meta_description=state["meta_description"],
            min_words=min_words,
            max_words=max_words,
        )
        state["history_id"] = str(record_generation(
            content_type="Blog",
            brand_name=state["brand"],
            title=state["selected_title"],
            primary_keyword=state["keyword"],
            word_count=state["quality_report"]["word_count"],
            meta_description=state["meta_description"],
            tags=state["tag_suggestions"],
            prompt_inputs={
                "supporting_keyword": state["supporting_keyword"],
                "tone": state["tone"],
                "include_money_site": state["include_money_site"],
                "regenerate_scope": state["regenerate_scope"],
                "change_request": state["change_request"],
                "links": state["links"],
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
            supporting_keyword=state["supporting_keyword"],
        )
        clear_generation_status(request.form.get("generation_status_token", ""))
        state["step"] = "content"
    except Exception as exc:
        logger.exception("generate_content action failed")
        state["error"] = generation_error_message(
            "An error occurred while generating article content. Check logs/app.log for details.",
            exc,
        )


def _handle_save_generated_blog(state: dict):
    state["selected_title"] = request.form.get("selected_title", "").strip()
    state["keyword"] = request.form.get("keyword", "").strip()
    state["brand"] = request.form.get("brand", "").strip()
    state["supporting_keyword"] = request.form.get("supporting_keyword", "").strip()
    state["tone"] = request.form.get("tone", "natural").strip() or "natural"
    state["change_request"] = request.form.get("change_request", "").strip()
    state["regenerate_scope"] = request.form.get("regenerate_scope", "full").strip() or "full"
    state["include_money_site"] = request.form.get("include_money_site") == "1"
    state["history_id"] = request.form.get("history_id", "").strip()
    state["content"] = request.form.get("content_html", "").strip()
    state["visual"] = request.form.get("visual", "").strip()
    titles_raw = request.form.get("titles_json", "").strip()
    selected_meta_description = request.form.get("meta_description_choice", "").strip()
    state["meta_description"] = selected_meta_description
    state["links"] = _extract_links_from_request()

    try:
        state["titles"] = json.loads(titles_raw) if titles_raw else []
    except json.JSONDecodeError:
        state["titles"] = []

    if not state["selected_title"]:
        state["error"] = "Please select a title before saving."
        return
    if not state["content"]:
        state["error"] = "There is no generated blog content to save."
        return

    min_words, max_words = get_blog_word_limits()
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
    state["history_id"] = str(record_generation(
        content_type="Blog",
        brand_name=state["brand"],
        title=state["selected_title"],
        primary_keyword=state["keyword"],
        word_count=state["quality_report"].get("word_count", count_html_words(state["content"])),
        meta_description=state["meta_description"],
        tags=state["tag_suggestions"],
        prompt_inputs={
            "supporting_keyword": state["supporting_keyword"],
            "tone": state["tone"],
            "include_money_site": state["include_money_site"],
            "manual_save": True,
            "links": state["links"],
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
        supporting_keyword=state["supporting_keyword"],
    )
    state["success"] = "Generated blog saved to history."
    state["step"] = "content"


def _extract_links_from_request() -> list[dict]:
    links = []
    link_texts = request.form.getlist("link_text[]")
    link_urls = request.form.getlist("link_url[]")
    link_types = request.form.getlist("link_type[]")

    for text, url, link_type in zip(link_texts, link_urls, link_types):
        cleaned_text = text.strip()
        cleaned_url = url.strip()
        cleaned_type = link_type.strip().lower() or "internal"
        if cleaned_text and cleaned_url:
            links.append({"text": cleaned_text, "url": cleaned_url, "type": cleaned_type})
    return links


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


def _visual_text(visuals: list[str]) -> str:
    return "\n\n".join(item for item in visuals if item).strip()


def _scoped_change_request(change_request: str, scope: str) -> str:
    cleaned = (change_request or "").strip()
    cleaned_scope = (scope or "full").strip().lower()
    scope_labels = {
        "intro": "Regenerate only the introduction while keeping the rest of the article structure and intent consistent.",
        "meta": "Regenerate the meta description options and keep the article aligned with the selected title.",
        "tags": "Refresh the tag angle and make the article naturally support better tags.",
        "conclusion": "Regenerate only the ending section while keeping the article body consistent.",
        "section": "Regenerate the weakest body section while keeping the title, intro, and ending consistent.",
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
