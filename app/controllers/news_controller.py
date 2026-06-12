import json

from flask import render_template, request

from app.controllers.helpers import base_template_context
from app.services.content_quality_service import analyze_generated_content
from app.services.generation_status_service import clear_generation_status, publish_generation_prompt, publish_generation_status
from app.services.provider_service import generation_error_message, get_provider
from app.services.reference_link_service import fetch_reference_context
from app.services.word_limit_settings import get_blog_word_limits
from database import get_brand_context, get_generation_history_item, list_brand_names, record_generation, upsert_brand
from generators.content_generator import count_html_words
from generators.news_generator import (
    generate_news_content,
    generate_news_meta_descriptions,
    generate_news_tags,
    generate_news_titles,
    generate_news_visual_ideas,
)
from logger import logger
from prompts.news import current_news_date


TARGET_COUNTRIES = [
    "Worldwide",
    "United States",
    "Philippines",
    "United Kingdom",
    "Canada",
    "Australia",
    "India",
    "Singapore",
    "Malaysia",
    "Indonesia",
    "Japan",
    "South Korea",
    "China",
    "Germany",
    "France",
    "Spain",
    "Italy",
    "Brazil",
    "Mexico",
    "United Arab Emirates",
    "Saudi Arabia",
    "South Africa",
]


def news_generator():
    state = _initial_state()
    edit_history_id = request.args.get("edit_history_id", "").strip()
    if request.method == "GET" and edit_history_id.isdigit():
        _load_history_item(state, int(edit_history_id))

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        if action == "generate_titles":
            _handle_generate_titles(state)
        elif action == "generate_all":
            _handle_generate_all(state)
        elif action == "save_generated_news":
            _handle_save_generated_news(state)

    return render_template("news_generator.html", **base_template_context(), **state)


def _initial_state() -> dict:
    return {
        "keyword": "",
        "brand": "",
        "target_audience": "",
        "target_country": "Worldwide",
        "target_countries": TARGET_COUNTRIES,
        "tone": "news",
        "count": 10,
        "titles": [],
        "selected_title": "",
        "meta_descriptions": [],
        "meta_description": "",
        "content": "",
        "visual": "",
        "links": [],
        "reference_fetches": [],
        "quality_report": None,
        "tag_suggestions": [],
        "error": None,
        "success": None,
        "step": "title",
        "history_id": "",
        "brand_names": list_brand_names(),
        "current_date": current_news_date(),
    }


def _handle_generate_titles(state: dict) -> None:
    state["keyword"] = request.form.get("keyword", "").strip()
    state["brand"] = request.form.get("brand", "").strip()
    state["target_audience"] = request.form.get("target_audience", "").strip()
    state["target_country"] = _target_country_from_request()
    state["links"] = _extract_reference_links_from_request()
    state["tone"] = request.form.get("tone", "news").strip() or "news"
    count_raw = request.form.get("count", "10").strip()

    if not state["keyword"]:
        state["error"] = "Please enter a current news keyword or event."
        return

    if state["brand"]:
        upsert_brand(state["brand"])

    try:
        state["count"] = int(count_raw)
    except ValueError:
        state["count"] = 10
    state["count"] = 20 if state["count"] > 10 else 10

    try:
        provider = get_provider()
        brand_context = get_brand_context(state["brand"])
        progress = _progress_callback("News Title", request.form.get("generation_status_token", ""))
        reference_context = _reference_context_for_state(state, progress)
        if state["error"]:
            return
        progress("Starting current news title generation...")
        state["titles"] = generate_news_titles(
            provider,
            keyword=state["keyword"],
            target_audience=state["target_audience"],
            target_country=state["target_country"],
            reference_context=reference_context,
            tone=state["tone"],
            count=state["count"],
            brand=state["brand"],
            brand_context=brand_context,
            current_date=state["current_date"],
            progress_callback=progress,
        )
        state["step"] = "title"
        progress("News titles passed validation.")
    except Exception as exc:
        logger.exception("generate_news_titles action failed")
        state["error"] = generation_error_message(
            "An error occurred while generating news titles. Check logs/app.log for details.",
            exc,
        )


def _handle_generate_all(state: dict) -> None:
    _hydrate_news_state(state)

    if not state["selected_title"]:
        state["error"] = "Please select a title first."
        return

    try:
        provider = get_provider()
        if state["brand"]:
            upsert_brand(state["brand"])
        brand_context = get_brand_context(state["brand"])
        min_words, max_words = get_blog_word_limits()
        progress = _progress_callback("News", request.form.get("generation_status_token", ""))
        reference_context = _reference_context_for_state(state, progress)
        if state["error"]:
            return

        progress("Generating 5 meta descriptions...")
        state["meta_descriptions"] = generate_news_meta_descriptions(
            provider,
            title=state["selected_title"],
            keyword=state["keyword"],
            target_audience=state["target_audience"],
            target_country=state["target_country"],
            reference_context=reference_context,
            count=5,
            brand=state["brand"],
            brand_context=brand_context,
            current_date=state["current_date"],
            progress_callback=progress,
        )
        state["meta_description"] = state["meta_descriptions"][0].get("text", "") if state["meta_descriptions"] else ""

        progress("Generating 3 visual image descriptions...")
        state["visual"] = _visual_text(generate_news_visual_ideas(
            provider,
            title=state["selected_title"],
            keyword=state["keyword"],
            target_audience=state["target_audience"],
            target_country=state["target_country"],
            reference_context=reference_context,
            count=3,
            brand=state["brand"],
            brand_context=brand_context,
            current_date=state["current_date"],
            progress_callback=progress,
        ))

        progress("Generating current news article content...")
        state["content"] = generate_news_content(
            provider,
            title=state["selected_title"],
            keyword=state["keyword"],
            target_audience=state["target_audience"],
            target_country=state["target_country"],
            reference_context=reference_context,
            tone=state["tone"],
            brand=state["brand"],
            brand_context=brand_context,
            min_words=min_words,
            max_words=max_words,
            current_date=state["current_date"],
            progress_callback=progress,
        )

        progress("Generating news tags...")
        state["tag_suggestions"] = generate_news_tags(
            provider,
            title=state["selected_title"],
            keyword=state["keyword"],
            target_audience=state["target_audience"],
            target_country=state["target_country"],
            reference_context=reference_context,
            brand=state["brand"],
            content=state["content"],
            minimum=10,
            current_date=state["current_date"],
            progress_callback=progress,
        )
        _record_completed_news(state, min_words, max_words)
        clear_generation_status(request.form.get("generation_status_token", ""))
        state["step"] = "content"
    except Exception as exc:
        logger.exception("generate_all_news action failed")
        state["error"] = generation_error_message(
            "An error occurred while generating the news article. Check logs/app.log for details.",
            exc,
        )


def _handle_save_generated_news(state: dict) -> None:
    _hydrate_news_state(state)
    state["content"] = request.form.get("content_html", "").strip()
    selected_meta_description = request.form.get("meta_description_choice", "").strip()
    if selected_meta_description:
        state["meta_description"] = selected_meta_description

    if not state["selected_title"]:
        state["error"] = "Please select a title before saving."
        return
    if not state["content"]:
        state["error"] = "There is no generated news content to save."
        return

    min_words, max_words = get_blog_word_limits()
    _record_completed_news(state, min_words, max_words)
    state["success"] = "Generated news article saved to history."
    state["step"] = "content"


def _load_history_item(state: dict, history_id: int) -> None:
    item = get_generation_history_item(history_id)
    if not item:
        return
    prompt_inputs = _loads(item.get("prompt_inputs", "{}"))
    if not prompt_inputs.get("news_generator"):
        return
    state["history_id"] = str(item.get("id", ""))
    state["brand"] = item.get("brand_name", "") or ""
    state["keyword"] = item.get("primary_keyword", "") or ""
    state["target_audience"] = prompt_inputs.get("target_audience", "")
    state["target_country"] = prompt_inputs.get("target_country", "Worldwide")
    if state["target_country"] not in TARGET_COUNTRIES:
        state["target_country"] = "Worldwide"
    state["tone"] = prompt_inputs.get("tone", state["tone"])
    state["titles"] = [item.get("title", "")] if item.get("title") else []
    state["selected_title"] = item.get("title", "") or ""
    state["meta_description"] = item.get("meta_description", "") or ""
    state["meta_descriptions"] = [{"text": state["meta_description"], "character_count": len(state["meta_description"])}] if state["meta_description"] else []
    state["content"] = item.get("content", "") or ""
    state["visual"] = prompt_inputs.get("visual", "") or ""
    state["links"] = prompt_inputs.get("links", [])
    state["reference_fetches"] = prompt_inputs.get("reference_fetches", [])
    state["quality_report"] = _loads(item.get("quality_report", "{}"))
    state["tag_suggestions"] = [tag.strip() for tag in (item.get("tags", "") or "").split(",") if tag.strip()]
    state["step"] = "content"


def _hydrate_news_state(state: dict) -> None:
    state["selected_title"] = request.form.get("selected_title", "").strip()
    state["keyword"] = request.form.get("keyword", "").strip()
    state["brand"] = request.form.get("brand", "").strip()
    state["target_audience"] = request.form.get("target_audience", "").strip()
    state["target_country"] = _target_country_from_request()
    state["tone"] = request.form.get("tone", "news").strip() or "news"
    state["history_id"] = request.form.get("history_id", "").strip()
    state["visual"] = request.form.get("visual", "").strip()
    state["content"] = request.form.get("content_html", "").strip()
    state["links"] = _extract_reference_links_from_request()
    state["reference_fetches"] = _json_list(request.form.get("reference_fetches_json", "").strip())
    state["titles"] = _json_list(request.form.get("titles_json", "").strip())
    state["meta_descriptions"] = _json_list(request.form.get("meta_descriptions_json", "").strip())
    state["tag_suggestions"] = _tags_from_raw(request.form.get("tags_json", "").strip())

    selected_meta_description = request.form.get("meta_description_choice", "").strip()
    if state["meta_descriptions"]:
        selected_match = next(
            (item for item in state["meta_descriptions"] if item.get("text", "").strip() == selected_meta_description),
            None,
        )
        state["meta_description"] = (selected_match or state["meta_descriptions"][0]).get("text", "")
    else:
        state["meta_description"] = selected_meta_description


def _record_completed_news(state: dict, min_words: int, max_words: int) -> None:
    if not state["content"]:
        return
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
            "tone": state["tone"],
            "target_audience": state["target_audience"],
            "target_country": state["target_country"],
            "visual": state["visual"],
            "links": state["links"],
            "reference_fetches": state["reference_fetches"],
            "current_date": state["current_date"],
            "news_generator": True,
        },
        content=state["content"],
        quality_report=state["quality_report"],
        history_id=state["history_id"],
    ))


def _json_list(raw: str) -> list:
    try:
        parsed = json.loads(raw) if raw else []
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _tags_from_raw(raw: str) -> list[str]:
    parsed = _json_list(raw)
    tags = []
    for item in parsed:
        cleaned = str(item or "").strip()
        if cleaned:
            tags.append(cleaned)
    return tags


def _extract_reference_links_from_request() -> list[dict]:
    links_from_json = _json_list(request.form.get("links_json", "").strip())
    if links_from_json:
        return _clean_reference_links(links_from_json)

    link_urls = request.form.getlist("link_url[]")
    links = []
    for url in link_urls:
        cleaned_url = _normalize_reference_url(url)
        if cleaned_url:
            links.append({"text": "", "url": cleaned_url, "type": "reference"})
    return _clean_reference_links(links)


def _clean_reference_links(raw_links: list) -> list[dict]:
    links = []
    seen_urls = set()
    for item in raw_links:
        if not isinstance(item, dict):
            continue
        url = _normalize_reference_url(item.get("url", ""))
        if not url or url.lower() in seen_urls:
            continue
        seen_urls.add(url.lower())
        links.append({
            "text": " ".join(str(item.get("text", "") or "").split()).strip(),
            "url": url,
            "type": "reference",
        })
    return links[:6]


def _normalize_reference_url(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    if cleaned.startswith("www."):
        cleaned = "https://" + cleaned
    if not cleaned.lower().startswith(("http://", "https://")):
        return ""
    return cleaned


def _reference_context_for_state(state: dict, progress) -> str:
    if not state["links"]:
        state["reference_fetches"] = []
        return ""
    progress(f"Fetching {len(state['links'])} reference link(s)...")
    reference_context, fetched = fetch_reference_context(state["links"])
    state["reference_fetches"] = fetched
    fetched_count = len([item for item in fetched if item.get("status") == "fetched"])
    if fetched_count == 0:
        state["error"] = "Could not fetch readable content from the reference links. Please check the URLs or try different news links."
        return ""
    progress(f"Using {fetched_count} fetched reference link(s) as the only source context.")
    return reference_context


def _loads(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _visual_text(visuals: list[str]) -> str:
    return "\n\n".join(item for item in visuals if item).strip()


def _target_country_from_request() -> str:
    value = request.form.get("target_country", "Worldwide").strip() or "Worldwide"
    return value if value in TARGET_COUNTRIES else "Worldwide"


def _progress_callback(label: str, token: str):
    cleaned_label = (label or "Generation").strip()

    def publish(message: str, kind: str = "status"):
        if kind == "prompt":
            publish_generation_prompt(token, message)
            return
        publish_generation_status(token, f"{cleaned_label}: {message}")

    return publish
