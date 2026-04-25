from flask import render_template, request

from database import get_brand_context, list_brand_names, record_page, upsert_brand
from generators.page_generator import generate_page
from generators.simple_page_generator import generate_simple_page
from logger import logger

from app.controllers.helpers import base_template_context
from app.services.provider_service import generation_error_message, get_provider


def page_generator():
    state = {
        "keyword": "",
        "brand": "",
        "supporting_keywords": "",
        "page_type": "",
        "expectations": "",
        "page_title": "",
        "meta_description": "",
        "page_content": "",
        "image_count": 0,
        "error": None,
        "brand_names": list_brand_names(),
    }

    if request.method == "POST":
        state["keyword"] = request.form.get("keyword", "").strip()
        state["brand"] = request.form.get("brand", "").strip()
        state["supporting_keywords"] = request.form.get("supporting_keywords", "").strip()
        state["page_type"] = request.form.get("page_type", "").strip()
        state["expectations"] = request.form.get("expectations", "").strip()

        if not state["keyword"]:
            state["error"] = "Please enter a keyword."
        else:
            try:
                provider = get_provider()
                if state["brand"]:
                    upsert_brand(state["brand"])
                brand_context = get_brand_context(state["brand"])
                result = generate_page(
                    provider,
                    keyword=state["keyword"],
                    brand=state["brand"],
                    supporting_keywords=state["supporting_keywords"],
                    page_type=state["page_type"],
                    expectations=state["expectations"],
                    brand_context=brand_context,
                )
                state["page_title"] = result.get("title", "")
                state["meta_description"] = result.get("meta_description", "")
                state["page_content"] = result.get("content", "")
                state["image_count"] = result.get("image_count", 0)
                record_page(
                    brand=state["brand"],
                    keyword=state["keyword"],
                    page_title=state["page_title"],
                    page_type=state["page_type"],
                    supporting_keywords=state["supporting_keywords"],
                    expectations=state["expectations"],
                )
            except Exception as exc:
                logger.exception("page_generator action failed")
                state["error"] = generation_error_message(
                    "An error occurred while generating the page. Check logs/app.log for details.",
                    exc,
                )

    return render_template("page_generator.html", **base_template_context(), **state)


def simple_page_generator():
    state = {
        "brand": "",
        "page_title": "",
        "page_type": "",
        "expectations": "",
        "generated_title": "",
        "generated_content": "",
        "error": None,
        "brand_names": list_brand_names(),
    }

    if request.method == "POST":
        state["brand"] = request.form.get("brand", "").strip()
        state["page_title"] = request.form.get("page_title", "").strip()
        state["page_type"] = request.form.get("page_type", "").strip()
        state["expectations"] = request.form.get("expectations", "").strip()

        if not state["page_title"]:
            state["error"] = "Please enter the page title or page name."
        else:
            try:
                provider = get_provider()
                if state["brand"]:
                    upsert_brand(state["brand"])
                brand_context = get_brand_context(state["brand"])
                result = generate_simple_page(
                    provider,
                    page_title=state["page_title"],
                    page_type=state["page_type"],
                    brand=state["brand"],
                    expectations=state["expectations"],
                    brand_context=brand_context,
                )
                state["generated_title"] = result.get("title", "")
                state["generated_content"] = result.get("content", "")
                record_page(
                    brand=state["brand"],
                    keyword=state["page_title"],
                    page_title=state["generated_title"] or state["page_title"],
                    page_type=state["page_type"] or "simple page",
                    supporting_keywords="",
                    expectations=state["expectations"],
                )
            except Exception as exc:
                logger.exception("simple_page_generator action failed")
                state["error"] = generation_error_message(
                    "An error occurred while generating the simple page. Check logs/app.log for details.",
                    exc,
                )

    return render_template("simple_page_generator.html", **base_template_context(), **state)
