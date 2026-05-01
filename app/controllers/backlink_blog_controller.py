import json

from flask import render_template, request

from database import get_backlink, get_brand_context, get_brand_record, list_backlinks, list_brand_names, record_blog, upsert_brand
from generators.content_generator import generate_backlink_content, suggest_content_tags
from generators.meta_description_generator import generate_backlink_meta_descriptions
from generators.title_generator import generate_backlink_titles
from logger import logger

from app.controllers.helpers import base_template_context
from app.services.provider_service import generation_error_message, get_provider


def backlink_blog_generator():
    state = {
        "keyword": "",
        "brand": "",
        "tone": "natural",
        "count": 10,
        "titles": [],
        "selected_title": "",
        "meta_descriptions": [],
        "meta_description": "",
        "content": "",
        "tag_suggestions": [],
        "change_request": "",
        "error": None,
        "step": "title",
        "brand_website_url": "",
        "selected_backlink_id": "",
        "selected_backlink": None,
        "brand_names": list_brand_names(),
        "backlinks": list_backlinks(),
    }

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        if action == "generate_titles":
            _handle_generate_titles(state)
        elif action == "generate_content":
            _handle_generate_content(state)

    return render_template("backlink_blog_generator.html", **base_template_context(), **state)


def _handle_generate_titles(state: dict):
    state["brand"] = request.form.get("brand", "").strip()
    state["keyword"] = request.form.get("keyword", "").strip()
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
            backlink_title_max_characters=state["selected_backlink"].get("title_max_characters", 0) or 0,
            backlink_max_characters=state["selected_backlink"].get("max_characters", 0) or 0,
            backlink_tier_level=state["selected_backlink"].get("tier_level", ""),
            backlink_blog_name=state["selected_backlink"].get("blog_name", "") or state["selected_backlink"].get("account_name", ""),
            backlink_writer_name=state["selected_backlink"].get("writer_name", ""),
            backlink_content_guidelines=state["selected_backlink"].get("content_guidelines", ""),
        )
        state["step"] = "title"
    except Exception as exc:
        logger.exception("backlink generate_titles action failed")
        state["error"] = generation_error_message(
            "An error occurred while generating medium titles. Check logs/app.log for details.",
            exc,
        )


def _handle_generate_content(state: dict):
    state["selected_title"] = request.form.get("selected_title", "").strip()
    state["keyword"] = request.form.get("keyword", "").strip()
    state["brand"] = request.form.get("brand", "").strip()
    state["tone"] = request.form.get("tone", "natural").strip() or "natural"
    state["change_request"] = request.form.get("change_request", "").strip()
    state["brand_website_url"] = request.form.get("brand_website_url", "").strip()
    state["selected_backlink_id"] = request.form.get("selected_backlink_id", "").strip()
    titles_raw = request.form.get("titles_json", "").strip()
    selected_meta_description = request.form.get("meta_description_choice", "").strip()

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
        state["titles"] = json.loads(titles_raw) if titles_raw else []
        provider = get_provider()
        if state["brand"]:
            upsert_brand(state["brand"])
        brand_context = get_brand_context(state["brand"])
        backlink_context = {
            "backlink_website_name": state["selected_backlink"].get("website_name", ""),
            "backlink_blog_url": "",
            "backlink_website_type": state["selected_backlink"].get("website_type", "blog"),
            "backlink_title_max_characters": state["selected_backlink"].get("title_max_characters", 0) or 0,
            "backlink_max_characters": state["selected_backlink"].get("max_characters", 0) or 0,
            "backlink_tier_level": state["selected_backlink"].get("tier_level", ""),
            "backlink_blog_name": state["selected_backlink"].get("blog_name", "") or state["selected_backlink"].get("account_name", ""),
            "backlink_writer_name": state["selected_backlink"].get("writer_name", ""),
            "backlink_content_guidelines": state["selected_backlink"].get("content_guidelines", ""),
        }
        state["meta_descriptions"] = generate_backlink_meta_descriptions(
            provider,
            title=state["selected_title"],
            keyword=state["keyword"],
            count=5,
            brand=state["brand"],
            brand_context=brand_context,
            **backlink_context,
        )
        if state["meta_descriptions"]:
            selected_match = next(
                (item for item in state["meta_descriptions"] if item.get("text", "").strip() == selected_meta_description),
                None,
            )
            state["meta_description"] = (selected_match or state["meta_descriptions"][0]).get("text", "")
        state["content"] = generate_backlink_content(
            provider,
            title=state["selected_title"],
            keyword=state["keyword"],
            tone=state["tone"],
            money_site_url=state["brand_website_url"],
            brand=state["brand"],
            brand_context=brand_context,
            change_request=state["change_request"],
            **backlink_context,
        )
        state["tag_suggestions"] = suggest_content_tags(
            title=state["selected_title"],
            keyword=state["keyword"],
            brand=state["brand"],
            content=state["content"],
            minimum=10,
        )
        record_blog(
            brand=state["brand"],
            title=state["selected_title"],
            keyword=state["keyword"],
            supporting_keyword="",
        )
        state["step"] = "content"
    except Exception as exc:
        logger.exception("backlink generate_content action failed")
        state["error"] = generation_error_message(
            "An error occurred while generating medium content. Check logs/app.log for details.",
            exc,
        )
