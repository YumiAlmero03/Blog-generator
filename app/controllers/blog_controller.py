import json

from flask import render_template, request

from database import get_brand_context, get_setting, list_brand_names, record_blog, upsert_brand
from generators.content_generator import generate_content
from generators.meta_description_generator import generate_meta_descriptions
from generators.title_generator import generate_titles
from logger import logger

from app.controllers.helpers import base_template_context
from app.services.provider_service import generation_error_message, get_provider


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
        "error": None,
        "step": "title",
        "include_money_site": False,
        "money_site_url": "",
        "links": [],
        "brand_names": list_brand_names(),
    }

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        if action == "generate_titles":
            _handle_generate_titles(state)
        elif action == "generate_content":
            _handle_generate_content(state)

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
        state["titles"] = generate_titles(
            provider,
            keyword=state["keyword"],
            tone=state["tone"],
            count=state["count"],
            brand=state["brand"],
            brand_context=brand_context,
        )
        state["step"] = "title"
    except Exception as exc:
        logger.exception("generate_titles action failed")
        state["error"] = generation_error_message(
            "An error occurred while generating titles. Check logs/app.log for details.",
            exc,
        )


def _handle_generate_content(state: dict):
    state["selected_title"] = request.form.get("selected_title", "").strip()
    state["keyword"] = request.form.get("keyword", "").strip()
    state["brand"] = request.form.get("brand", "").strip()
    state["supporting_keyword"] = request.form.get("supporting_keyword", "").strip()
    state["tone"] = request.form.get("tone", "natural").strip() or "natural"
    state["include_money_site"] = request.form.get("include_money_site") == "1"
    titles_raw = request.form.get("titles_json", "").strip()
    selected_meta_description = request.form.get("meta_description_choice", "").strip()

    state["links"] = _extract_links_from_request()

    if not state["selected_title"]:
        state["error"] = "Please select a title first."
        return

    try:
        state["titles"] = json.loads(titles_raw) if titles_raw else []
        provider = get_provider()
        if state["brand"]:
            upsert_brand(state["brand"])
        state["money_site_url"] = get_setting("money_site", "")
        brand_context = get_brand_context(state["brand"])
        state["meta_descriptions"] = generate_meta_descriptions(
            provider,
            title=state["selected_title"],
            keyword=state["keyword"],
            count=5,
            brand=state["brand"],
            brand_context=brand_context,
        )
        if state["meta_descriptions"]:
            selected_match = next(
                (item for item in state["meta_descriptions"] if item.get("text", "").strip() == selected_meta_description),
                None,
            )
            state["meta_description"] = (selected_match or state["meta_descriptions"][0]).get("text", "")
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
        )
        record_blog(
            brand=state["brand"],
            title=state["selected_title"],
            keyword=state["keyword"],
            supporting_keyword=state["supporting_keyword"],
        )
        state["step"] = "content"
    except Exception as exc:
        logger.exception("generate_content action failed")
        state["error"] = generation_error_message(
            "An error occurred while generating article content. Check logs/app.log for details.",
            exc,
        )


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
