import json
import re

from flask import render_template, request

from app.controllers.helpers import base_template_context
from app.services.content_quality_service import analyze_generated_content
from app.services.generation_status_service import clear_generation_status, publish_generation_prompt, publish_generation_status
from app.services.locale_settings import (
    country_options,
    get_default_country_target,
    get_default_language,
    language_options,
    normalize_country_target,
    normalize_language,
)
from app.services.provider_service import generation_error_message, get_provider
from app.services.reference_link_service import fetch_reference_context
from app.services.word_limit_settings import get_blog_word_limits
from database import get_brand_context, get_generation_history_item, list_brand_names, list_checklist_items, record_generation, upsert_brand
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
    "Afghanistan",
    "Albania",
    "Algeria",
    "Andorra",
    "Angola",
    "Argentina",
    "Armenia",
    "Australia",
    "Austria",
    "Azerbaijan",
    "Bahamas",
    "Bahrain",
    "Bangladesh",
    "Barbados",
    "Belarus",
    "Belgium",
    "Belize",
    "Benin",
    "Bhutan",
    "Bolivia",
    "Bosnia and Herzegovina",
    "Botswana",
    "Brazil",
    "Brunei",
    "Bulgaria",
    "Burkina Faso",
    "Cambodia",
    "Cameroon",
    "Canada",
    "Chile",
    "China",
    "Colombia",
    "Costa Rica",
    "Croatia",
    "Cyprus",
    "Czech Republic",
    "Denmark",
    "Dominican Republic",
    "Ecuador",
    "Egypt",
    "El Salvador",
    "Estonia",
    "Ethiopia",
    "Finland",
    "France",
    "Georgia",
    "Germany",
    "Ghana",
    "Greece",
    "Guatemala",
    "Honduras",
    "Hong Kong",
    "Hungary",
    "Iceland",
    "India",
    "Indonesia",
    "Ireland",
    "Israel",
    "Italy",
    "Jamaica",
    "Japan",
    "Jordan",
    "Kazakhstan",
    "Kenya",
    "Kuwait",
    "Latvia",
    "Lebanon",
    "Lithuania",
    "Luxembourg",
    "Malaysia",
    "Maldives",
    "Malta",
    "Mexico",
    "Morocco",
    "Myanmar",
    "Nepal",
    "Netherlands",
    "New Zealand",
    "Nigeria",
    "Norway",
    "Oman",
    "Pakistan",
    "Panama",
    "Paraguay",
    "Peru",
    "Philippines",
    "Poland",
    "Portugal",
    "Qatar",
    "Romania",
    "Serbia",
    "Singapore",
    "Slovakia",
    "Slovenia",
    "Saudi Arabia",
    "South Africa",
    "South Korea",
    "Spain",
    "Sri Lanka",
    "Sweden",
    "Switzerland",
    "Taiwan",
    "Thailand",
    "Turkey",
    "Ukraine",
    "United Arab Emirates",
    "United Kingdom",
    "United States",
    "Uruguay",
    "Venezuela",
    "Vietnam",
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
        elif action in {"generate_meta_descriptions", "generate_visual", "generate_content", "generate_tags"}:
            _handle_generate_news_piece(state, action)
        elif action == "generate_all":
            _handle_generate_all(state)
        elif action == "save_generated_news":
            _handle_save_generated_news(state)

    state["language_options"] = language_options(state["language"])
    state["target_countries"] = country_options(state["target_country"])
    return render_template("news_generator.html", **base_template_context(), **state)


def _initial_state() -> dict:
    return {
        "keyword": "",
        "focus_keyword": "",
        "supporting_keywords": "",
        "keyword_suggestions": [],
        "brand": "",
        "language": get_default_language(),
        "target_audience": "",
        "target_country": get_default_country_target(),
        "target_countries": country_options(get_default_country_target()),
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
        "content_checklist_items": list_checklist_items("blog", active_only=True),
    }


def _handle_generate_titles(state: dict) -> None:
    state["keyword"] = request.form.get("keyword", "").strip()
    state["brand"] = request.form.get("brand", "").strip()
    state["language"] = _language_from_request()
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
            language=state["language"],
            progress_callback=progress,
        )
        state["focus_keyword"] = _default_focus_keyword(state["keyword"])
        state["supporting_keywords"] = _default_supporting_keywords(state["keyword"], state["titles"], state["target_country"])
        state["keyword_suggestions"] = _keyword_suggestions(
            state["keyword"],
            state["titles"],
            state["target_country"],
            state["focus_keyword"],
            state["supporting_keywords"],
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

        progress("Generating current news article content first...")
        state["content"] = generate_news_content(
            provider,
            title=state["selected_title"],
            keyword=_news_keyword_context(state),
            target_audience=state["target_audience"],
            target_country=state["target_country"],
            reference_context=reference_context,
            tone=state["tone"],
            brand=state["brand"],
            brand_context=brand_context,
            min_words=min_words,
            max_words=max_words,
            current_date=state["current_date"],
            language=state["language"],
            progress_callback=progress,
        )

        if state["meta_descriptions"]:
            progress("Reusing existing meta descriptions.")
            state["meta_description"] = state["meta_description"] or state["meta_descriptions"][0].get("text", "")
        else:
            try:
                progress("Generating 3 meta descriptions...")
                state["meta_descriptions"] = generate_news_meta_descriptions(
                    provider,
                    title=state["selected_title"],
                    keyword=_news_keyword_context(state),
                    target_audience=state["target_audience"],
                    target_country=state["target_country"],
                    reference_context=reference_context,
                    count=3,
                    brand=state["brand"],
                    brand_context=brand_context,
                    current_date=state["current_date"],
                    language=state["language"],
                    progress_callback=progress,
                )
                state["meta_description"] = state["meta_descriptions"][0].get("text", "") if state["meta_descriptions"] else ""
            except Exception as exc:
                logger.warning("news meta generation skipped after content success: %s", exc)
                progress("Meta descriptions could not be generated, continuing with the article.")

        if state["visual"]:
            progress("Reusing existing visual descriptions.")
        else:
            try:
                progress("Generating 2 visual image descriptions...")
                state["visual"] = _visual_text(generate_news_visual_ideas(
                    provider,
                    title=state["selected_title"],
                    keyword=_news_keyword_context(state),
                    target_audience=state["target_audience"],
                    target_country=state["target_country"],
                    reference_context=reference_context,
                    count=2,
                    brand=state["brand"],
                    brand_context=brand_context,
                    current_date=state["current_date"],
                    language=state["language"],
                    progress_callback=progress,
                ))
            except Exception as exc:
                logger.warning("news visual generation skipped after content success: %s", exc)
                progress("Visual descriptions could not be generated, continuing with the article.")

        try:
            progress("Generating news tags...")
            state["tag_suggestions"] = generate_news_tags(
                provider,
                title=state["selected_title"],
                keyword=_news_keyword_context(state),
                target_audience=state["target_audience"],
                target_country=state["target_country"],
                reference_context=reference_context,
                brand=state["brand"],
                content=state["content"],
                minimum=10,
                current_date=state["current_date"],
                language=state["language"],
                progress_callback=progress,
            )
        except Exception as exc:
            logger.warning("news tags generation skipped after content success: %s", exc)
            progress("Tags could not be generated, continuing with the article.")

        _record_completed_news(state, min_words, max_words)
        clear_generation_status(request.form.get("generation_status_token", ""))
        state["step"] = "content"
    except Exception as exc:
        logger.exception("generate_all_news action failed")
        state["error"] = generation_error_message(
            "An error occurred while generating the news article. Check logs/app.log for details.",
            exc,
        )


def _handle_generate_news_piece(state: dict, action: str) -> None:
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

        if action == "generate_meta_descriptions":
            progress("Generating 3 meta descriptions...")
            state["meta_descriptions"] = generate_news_meta_descriptions(
                provider,
                title=state["selected_title"],
                keyword=_news_keyword_context(state),
                target_audience=state["target_audience"],
                target_country=state["target_country"],
                reference_context=reference_context,
                count=3,
                brand=state["brand"],
                brand_context=brand_context,
                current_date=state["current_date"],
                language=state["language"],
                progress_callback=progress,
            )
            state["meta_description"] = state["meta_descriptions"][0].get("text", "") if state["meta_descriptions"] else ""
            state["step"] = "content"
            clear_generation_status(request.form.get("generation_status_token", ""))
            return

        if action == "generate_visual":
            progress("Generating 2 visual image descriptions...")
            state["visual"] = _visual_text(generate_news_visual_ideas(
                provider,
                title=state["selected_title"],
                keyword=_news_keyword_context(state),
                target_audience=state["target_audience"],
                target_country=state["target_country"],
                reference_context=reference_context,
                count=2,
                brand=state["brand"],
                brand_context=brand_context,
                current_date=state["current_date"],
                language=state["language"],
                progress_callback=progress,
            ))
            state["step"] = "content"
            clear_generation_status(request.form.get("generation_status_token", ""))
            return

        if action == "generate_tags":
            if not state["content"]:
                state["error"] = "Please generate news content before generating tags."
                return
            progress("Generating news tags...")
            state["tag_suggestions"] = generate_news_tags(
                provider,
                title=state["selected_title"],
                keyword=_news_keyword_context(state),
                target_audience=state["target_audience"],
                target_country=state["target_country"],
                reference_context=reference_context,
                brand=state["brand"],
                content=state["content"],
                minimum=10,
                current_date=state["current_date"],
                language=state["language"],
                progress_callback=progress,
            )
            _record_completed_news(state, min_words, max_words)
            clear_generation_status(request.form.get("generation_status_token", ""))
            state["step"] = "content"
            return

        progress("Generating current news article content...")
        state["content"] = generate_news_content(
            provider,
            title=state["selected_title"],
            keyword=_news_keyword_context(state),
            target_audience=state["target_audience"],
            target_country=state["target_country"],
            reference_context=reference_context,
            tone=state["tone"],
            brand=state["brand"],
            brand_context=brand_context,
            min_words=min_words,
            max_words=max_words,
            current_date=state["current_date"],
            language=state["language"],
            progress_callback=progress,
        )
        _record_completed_news(state, min_words, max_words)
        clear_generation_status(request.form.get("generation_status_token", ""))
        state["step"] = "content"
    except Exception as exc:
        logger.exception("generate_news_piece action failed")
        state["error"] = generation_error_message(
            "An error occurred while generating the news piece. Check logs/app.log for details.",
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
    state["focus_keyword"] = prompt_inputs.get("focus_keyword", _default_focus_keyword(state["keyword"]))
    state["language"] = prompt_inputs.get("language", state["language"]) or "English"
    state["supporting_keywords"] = prompt_inputs.get("supporting_keywords", "")
    state["target_audience"] = prompt_inputs.get("target_audience", "")
    state["target_country"] = normalize_country_target(prompt_inputs.get("target_country", get_default_country_target()))
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
    state["keyword_suggestions"] = _keyword_suggestions(
        state["keyword"],
        state["titles"],
        state["target_country"],
        state["focus_keyword"],
        state["supporting_keywords"],
    )


def _hydrate_news_state(state: dict) -> None:
    state["selected_title"] = request.form.get("selected_title", "").strip()
    state["keyword"] = request.form.get("keyword", "").strip()
    state["focus_keyword"] = request.form.get("focus_keyword", "").strip() or _default_focus_keyword(state["keyword"])
    state["supporting_keywords"] = request.form.get("supporting_keywords", "").strip()
    state["brand"] = request.form.get("brand", "").strip()
    state["language"] = _language_from_request()
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

    state["keyword_suggestions"] = _keyword_suggestions(
        state["keyword"],
        state["titles"],
        state["target_country"],
        state["focus_keyword"],
        state["supporting_keywords"],
    )


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
            "language": state["language"],
            "focus_keyword": state["focus_keyword"],
            "supporting_keywords": state["supporting_keywords"],
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
    cached_context = _reference_context_from_cached_fetches(state["links"], state["reference_fetches"])
    if cached_context:
        fetched_count = len([item for item in state["reference_fetches"] if item.get("status") == "fetched"])
        progress(f"Reusing {fetched_count} cached reference link(s).")
        return cached_context
    progress(f"Fetching {len(state['links'])} reference link(s)...")
    reference_context, fetched = fetch_reference_context(state["links"])
    state["reference_fetches"] = fetched
    fetched_count = len([item for item in fetched if item.get("status") == "fetched"])
    if fetched_count == 0:
        progress("Reference links were not readable, continuing without source context.")
        return ""
    progress(f"Using {fetched_count} fetched reference link(s) as the only source context.")
    return reference_context


def _reference_context_from_cached_fetches(links: list[dict], fetched: list[dict]) -> str:
    if not links or not fetched:
        return ""
    requested_urls = [_normalize_reference_url(item.get("url", "")).lower() for item in links]
    fetched_by_url = {
        _normalize_reference_url(item.get("url", "")).lower(): item
        for item in fetched
        if item.get("status") == "fetched" and item.get("excerpt")
    }
    if not requested_urls or not all(url in fetched_by_url for url in requested_urls):
        return ""

    context_parts = []
    for index, url in enumerate(requested_urls, start=1):
        item = fetched_by_url[url]
        source_label = item.get("source_label") or item.get("text") or item.get("title") or item.get("url")
        context_parts.append(
            f"Reference {index}: {source_label}\nURL: {item.get('url')}\nExtracted content:\n{item.get('excerpt')}"
        )
    return "\n\n---\n\n".join(context_parts).strip()


def _loads(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _language_from_request() -> str:
    return normalize_language(request.form.get("language", get_default_language()))


def _visual_text(visuals: list[str]) -> str:
    return "\n\n".join(item for item in visuals if item).strip()


def _target_country_from_request() -> str:
    return normalize_country_target(request.form.get("target_country", get_default_country_target()))


def _news_keyword_context(state: dict) -> str:
    focus = (state.get("focus_keyword") or _default_focus_keyword(state.get("keyword", ""))).strip()
    supporting = (state.get("supporting_keywords") or "").strip()
    original = (state.get("keyword") or "").strip()
    parts = []
    if focus:
        parts.append(f"Focus keyphrase: {focus}")
    if supporting:
        parts.append(f"Supporting keyphrases: {supporting}")
    if original and original.lower() != focus.lower():
        parts.append(f"Original news topic: {original}")
    return "\n".join(parts) if parts else original


def _default_focus_keyword(keyword: str) -> str:
    chunks = [item.strip() for item in re.split(r"[,;\n]+", keyword or "") if item.strip()]
    return chunks[0] if chunks else (keyword or "").strip()


def _default_supporting_keywords(keyword: str, titles: list[str], target_country: str) -> str:
    focus = _default_focus_keyword(keyword).lower()
    suggestions = _keyword_suggestions(keyword, titles, target_country, focus, "")
    filtered = [item for item in suggestions if item.lower() != focus]
    return ", ".join(filtered[:5])


def _keyword_suggestions(
    keyword: str,
    titles: list[str],
    target_country: str,
    focus_keyword: str = "",
    supporting_keywords: str = "",
) -> list[str]:
    candidates = []
    for value in re.split(r"[,;\n]+", keyword or ""):
        _append_keyword_candidate(candidates, value)

    selected_focus = (focus_keyword or _default_focus_keyword(keyword)).strip()
    _append_keyword_candidate(candidates, selected_focus)
    for value in re.split(r"[,;\n]+", supporting_keywords or ""):
        _append_keyword_candidate(candidates, value)

    title_text = " ".join(title for title in titles if isinstance(title, str))
    words = [
        word.lower()
        for word in re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]{2,}", title_text)
        if word.lower() not in _KEYWORD_STOP_WORDS
    ]
    for size in (3, 2):
        for index in range(0, max(0, len(words) - size + 1)):
            phrase = " ".join(words[index : index + size])
            _append_keyword_candidate(candidates, phrase)
            if len(candidates) >= 10:
                break
        if len(candidates) >= 10:
            break

    if target_country and target_country != "Worldwide" and selected_focus:
        _append_keyword_candidate(candidates, f"{selected_focus} {target_country}")

    return candidates[:10]


def _append_keyword_candidate(candidates: list[str], value: str) -> None:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip(" -_.,:;")).strip()
    if not cleaned:
        return
    normalized = cleaned.lower()
    if normalized in _KEYWORD_STOP_WORDS or len(normalized) < 3:
        return
    if normalized not in [item.lower() for item in candidates]:
        candidates.append(cleaned)


_KEYWORD_STOP_WORDS = {
    "about",
    "after",
    "and",
    "are",
    "breaking",
    "current",
    "daily",
    "from",
    "for",
    "have",
    "latest",
    "news",
    "that",
    "the",
    "this",
    "today",
    "update",
    "what",
    "when",
    "where",
    "with",
}


def _progress_callback(label: str, token: str):
    cleaned_label = (label or "Generation").strip()

    def publish(message: str, kind: str = "status"):
        if kind == "prompt":
            publish_generation_prompt(token, message)
            return
        publish_generation_status(token, f"{cleaned_label}: {message}")

    return publish
