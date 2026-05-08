from flask import render_template, request

from database import get_brand_context, list_brand_names, record_generation, record_page, upsert_brand
from generators.page_generator import generate_page
from generators.simple_page_generator import generate_simple_page
from logger import logger

from app.controllers.helpers import base_template_context
from app.services.content_quality_service import analyze_generated_content
from app.services.provider_service import generation_error_message, get_provider
from app.services.word_limit_settings import get_page_word_limits


def page_generator():
    state = {
        "keyword": "",
        "brand": "",
        "supporting_keywords": "",
        "page_type": "",
        "expectations": "",
        "page_title": "",
        "change_request": "",
        "meta_description": "",
        "page_content": "",
        "quality_report": None,
        "regenerate_scope": "full",
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
        state["change_request"] = request.form.get("change_request", "").strip()
        state["regenerate_scope"] = request.form.get("regenerate_scope", "full").strip() or "full"

        if not state["keyword"]:
            state["error"] = "Please enter a keyword."
        else:
            try:
                provider = get_provider()
                if state["brand"]:
                    upsert_brand(state["brand"])
                brand_context = get_brand_context(state["brand"])
                min_words, max_words = get_page_word_limits()
                result = generate_page(
                    provider,
                    keyword=state["keyword"],
                    brand=state["brand"],
                    supporting_keywords=state["supporting_keywords"],
                    page_type=state["page_type"],
                    expectations=state["expectations"],
                    brand_context=brand_context,
                    change_request=_scoped_change_request(state["change_request"], state["regenerate_scope"]),
                    min_words=min_words,
                    max_words=max_words,
                )
                state["page_title"] = result.get("title", "")
                state["meta_description"] = result.get("meta_description", "")
                state["page_content"] = result.get("content", "")
                state["image_count"] = result.get("image_count", 0)
                state["quality_report"] = analyze_generated_content(
                    state["page_content"],
                    title=state["page_title"],
                    keyword=state["keyword"],
                    meta_description=state["meta_description"],
                    min_words=min_words,
                    max_words=max_words,
                )
                record_generation(
                    content_type="Page",
                    brand_name=state["brand"],
                    title=state["page_title"],
                    primary_keyword=state["keyword"],
                    word_count=state["quality_report"]["word_count"],
                    meta_description=state["meta_description"],
                    prompt_inputs={
                        "page_type": state["page_type"],
                        "supporting_keywords": state["supporting_keywords"],
                        "expectations": state["expectations"],
                        "regenerate_scope": state["regenerate_scope"],
                        "change_request": state["change_request"],
                    },
                    content=state["page_content"],
                    quality_report=state["quality_report"],
                )
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
        "meta_descriptions": [],
        "generated_content": "",
        "quality_report": None,
        "change_request": "",
        "regenerate_scope": "full",
        "error": None,
        "brand_names": list_brand_names(),
    }

    if request.method == "POST":
        state["brand"] = request.form.get("brand", "").strip()
        state["page_title"] = request.form.get("page_title", "").strip()
        state["page_type"] = request.form.get("page_type", "").strip()
        state["expectations"] = request.form.get("expectations", "").strip()
        state["change_request"] = request.form.get("change_request", "").strip()
        state["regenerate_scope"] = request.form.get("regenerate_scope", "full").strip() or "full"

        if not state["page_title"]:
            state["error"] = "Please enter the page title or page name."
        else:
            try:
                provider = get_provider()
                if state["brand"]:
                    upsert_brand(state["brand"])
                brand_context = get_brand_context(state["brand"])
                min_words, max_words = get_page_word_limits()
                result = generate_simple_page(
                    provider,
                    page_title=state["page_title"],
                    page_type=state["page_type"],
                    brand=state["brand"],
                    expectations=state["expectations"],
                    brand_context=brand_context,
                    change_request=_scoped_change_request(state["change_request"], state["regenerate_scope"]),
                    min_words=min_words,
                    max_words=max_words,
                )
                state["generated_title"] = result.get("title", "")
                state["meta_descriptions"] = result.get("meta_descriptions", [])
                state["generated_content"] = result.get("content", "")
                selected_meta = state["meta_descriptions"][0].get("text", "") if state["meta_descriptions"] else ""
                state["quality_report"] = analyze_generated_content(
                    state["generated_content"],
                    title=state["generated_title"] or state["page_title"],
                    keyword=state["page_title"],
                    meta_description=selected_meta,
                    min_words=min_words,
                    max_words=max_words,
                )
                record_generation(
                    content_type="Simple Page",
                    brand_name=state["brand"],
                    title=state["generated_title"] or state["page_title"],
                    primary_keyword=state["page_title"],
                    word_count=state["quality_report"]["word_count"],
                    meta_description=selected_meta,
                    prompt_inputs={
                        "page_type": state["page_type"],
                        "expectations": state["expectations"],
                        "regenerate_scope": state["regenerate_scope"],
                        "change_request": state["change_request"],
                    },
                    content=state["generated_content"],
                    quality_report=state["quality_report"],
                )
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
