import csv
import io
import json
import re
import time
from datetime import date, timedelta

from flask import Response, redirect, render_template, request, url_for
from urllib.parse import urlparse

from app.controllers.helpers import base_template_context
from app.services.document_service import build_docx_response, build_gsc_summary_report_response, build_website_planner_report_response, extract_docx_website_reference
from app.services.indexnow_service import (
    DEFAULT_INDEXNOW_ENDPOINT,
    GOOGLE_INDEXING_ENDPOINT,
    build_sitemap_xml,
    extract_urls,
    inspect_google_index_status_by_url_domain,
    submit_google_indexing_urls,
    submit_indexnow_urls,
)
from app.services.gsc_planner_service import answer_gsc_planner_chat, fetch_gsc_performance_data, generate_gsc_seo_report
from app.services.keyword_suggestion_service import generate_keyword_suggestions
from app.services.locale_settings import (
    country_options,
    get_default_country_target,
    get_default_language,
    language_options,
    normalize_country_target,
    normalize_language,
)
from app.services.meta_generator_service import (
    DEFAULT_META_OPTION_COUNT,
    META_DESCRIPTION_MAX_CHARS,
    META_DESCRIPTION_MIN_CHARS,
    generate_meta_titles_and_descriptions,
    keyword_from_page_type,
)
from app.services.provider_service import generation_error_message, get_provider
from app.services.reference_link_service import fetch_url_html, fetch_url_rendered_html
from app.services.seo_checker_service import run_seo_audit
from app.services.generation_status_service import publish_generation_prompt, publish_generation_status
from app.services.generation_log_service import append_generation_log, generation_log_json, parse_generation_log
from app.services.website_page_discovery_service import discover_website_pages
from app.services.website_index_scheduler import submit_website_index_urls_to_indexnow, trigger_website_index_batch
from app.services.website_planner_service import DEFAULT_KEYWORD_CATEGORIES, build_website_plan, get_main_pages_setting, get_trust_pages_setting, parse_keyword_categories
from database import get_brand_context, get_brand_record, get_setting, list_backlinks, list_brand_names, list_brand_records, set_setting
from database import delete_website_index_url, delete_website_index_urls_by_domain, list_due_website_index_submission_urls, list_due_website_index_urls, list_website_index_urls, mark_website_index_urls_checking, update_website_index_bing_yahoo_weekly_result, update_website_index_google_result, upsert_website_index_urls, website_index_stats
from logger import logger


WEBSITE_INDEX_CHECK_LIMIT = 50
WEBSITE_PAGES_PER_PAGE = 50


def text_tools():
    return render_template("text_tools.html", **base_template_context())


def test_page():
    state = {
        "url": "",
        "wait_minutes": "0",
        "fetch_mode": "browser",
        "result": None,
        "error": None,
    }
    if request.method == "POST":
        state["url"] = request.form.get("url", "").strip()
        state["wait_minutes"] = request.form.get("wait_minutes", "0").strip() or "0"
        state["fetch_mode"] = request.form.get("fetch_mode", "browser").strip() or "browser"
        if not state["url"]:
            state["error"] = "Enter a link to test."
        else:
            try:
                wait_seconds = _test_page_wait_seconds(state["wait_minutes"])
                if state["fetch_mode"] == "browser":
                    fetched = fetch_url_rendered_html(state["url"], wait_seconds=wait_seconds)
                else:
                    if wait_seconds:
                        time.sleep(wait_seconds)
                    fetched = fetch_url_html(state["url"])
                state["result"] = {
                    "content_type": fetched.get("content_type", ""),
                    "html": fetched.get("html", ""),
                    "byte_count": fetched.get("byte_count", 0),
                    "character_count": fetched.get("character_count", 0),
                    "final_url": fetched.get("final_url", state["url"]),
                    "wait_seconds": wait_seconds,
                    "fetch_mode": state["fetch_mode"],
                    "rendered": bool(fetched.get("rendered")),
                }
            except Exception as exc:
                logger.exception("test page link fetch failed")
                state["error"] = str(exc) or "Could not fetch that link."
    return render_template("test_page.html", **base_template_context(), **state)


def _test_page_wait_seconds(value: str) -> float:
    try:
        minutes = float(value)
    except (TypeError, ValueError):
        raise ValueError("Wait time must be a number.")
    if minutes < 0:
        raise ValueError("Wait time cannot be negative.")
    if minutes > 5:
        raise ValueError("Wait time can be 5 minutes maximum.")
    return minutes * 60


def context_planner():
    state = _default_context_planner_state()
    if request.method == "POST":
        for key in (
            "content_type",
            "topic",
            "brand",
            "medium",
            "target_country",
            "language",
            "audience",
            "search_intent",
            "primary_keyword",
            "supporting_keywords",
            "entities",
            "must_include",
            "avoid",
            "internal_links",
            "competitor_notes",
            "outline_notes",
            "cta",
        ):
            state[key] = request.form.get(key, "").strip()
        state["target_country"] = normalize_country_target(state["target_country"])
        state["language"] = normalize_language(state["language"])
        state["context_brief"] = _build_context_brief(state)
        state["success"] = "Context brief created."
    state["target_countries"] = country_options(state["target_country"])
    state["languages"] = language_options(state["language"])
    return render_template("context_planner.html", **base_template_context(), **state)


def website_planner():
    default_keyword_categories = list(DEFAULT_KEYWORD_CATEGORIES)
    state = {
        "planner_client": "",
        "planner_domain": "",
        "planner_target_market": "",
        "planner_language": "English",
        "planner_site_type": "",
        "planner_reference_content": "",
        "planner_reference_filename": "",
        "planner_reference_pages": [],
        "page_count": 5,
        "trust_page_count": 3,
        "blog_count": 10,
        "keyword_categories": default_keyword_categories,
        "selected_keyword_categories": default_keyword_categories[:3],
        "custom_keyword_categories": "",
        "main_pages_text": get_main_pages_setting(),
        "trust_pages_text": get_trust_pages_setting(),
        "plan": None,
        "plan_json": "",
        "generation_log": [],
        "generation_log_json": "[]",
        "error": None,
    }
    if request.method == "POST":
        for key in ("planner_client", "planner_domain", "planner_target_market", "planner_language", "planner_site_type", "planner_reference_content", "planner_reference_filename"):
            state[key] = request.form.get(key, "").strip()
        state["generation_log"] = parse_generation_log(request.form.get("generation_log_json", ""))
        state["generation_log_json"] = generation_log_json(state["generation_log"])
        append_generation_log(state["generation_log"], "status", "Website Planner: Starting plan build.")
        state["page_count"] = _planner_count(request.form.get("page_count", "5"), 5)
        state["trust_page_count"] = _planner_count(request.form.get("trust_page_count", "3"), 3)
        state["blog_count"] = _planner_count(request.form.get("blog_count", "10"), 10)
        state["custom_keyword_categories"] = request.form.get("custom_keyword_categories", "").strip()
        selected_categories = parse_keyword_categories(request.form.getlist("keyword_categories"))
        custom_categories = parse_keyword_categories(state["custom_keyword_categories"])
        state["selected_keyword_categories"] = _merge_planner_categories(selected_categories, custom_categories)
        state["keyword_categories"] = _merge_planner_categories(default_keyword_categories, custom_categories)
        try:
            reference_upload = request.files.get("planner_reference_file")
            if reference_upload and reference_upload.filename:
                reference = extract_docx_website_reference(reference_upload)
                state["planner_reference_content"] = reference["text"]
                state["planner_reference_filename"] = reference_upload.filename
                state["planner_reference_pages"] = reference["pages"]
                append_generation_log(state["generation_log"], "status", f"Read reference file: {reference_upload.filename}.")
                if state["planner_reference_pages"]:
                    append_generation_log(state["generation_log"], "status", f"Extracted {len(state['planner_reference_pages'])} page(s) from DOCX Heading 1/Page sections.")
                else:
                    append_generation_log(state["generation_log"], "status", "No DOCX Heading 1/Page sections found. Using Settings main pages.")
            state["plan"] = build_website_plan(
                state["main_pages_text"],
                state["trust_pages_text"],
                page_count=len(state["planner_reference_pages"]) if state["planner_reference_pages"] else state["page_count"],
                trust_page_count=state["trust_page_count"],
                blog_count=state["blog_count"],
                keyword_categories_text=state["selected_keyword_categories"],
                brand_names=list_brand_names(),
            )
            if state["planner_reference_pages"]:
                state["plan"]["main_pages"] = _planner_reference_page_items(state["planner_reference_pages"])
                state["plan"]["summary"]["main_pages"] = len(state["plan"]["main_pages"])
                state["plan"]["summary"]["total"] = state["plan"]["summary"]["main_pages"] + state["plan"]["summary"]["trust_pages"] + state["plan"]["summary"]["blogs"]
                state["page_count"] = len(state["plan"]["main_pages"])
                append_generation_log(state["generation_log"], "status", "Using uploaded DOCX pages as the core page list.")
            append_generation_log(state["generation_log"], "status", f"Plan created: {state['plan']['summary']['main_pages']} core page(s), {state['plan']['summary']['trust_pages']} trust page(s), {state['plan']['summary']['blogs']} blog topic(s).")
            state["plan_json"] = json.dumps(state["plan"], ensure_ascii=True)
        except Exception as exc:
            logger.exception("website planner failed")
            append_generation_log(state["generation_log"], "error", str(exc) or "Could not create the website plan.")
            state["error"] = str(exc) or "Could not create the website plan."
    state["generation_log_json"] = generation_log_json(state.get("generation_log", []))
    return render_template("website_planner.html", **base_template_context(), **state)


def download_website_planner_report():
    plan = _json_dict(request.form.get("plan_json", ""))
    if not plan:
        return redirect(url_for("web.website_planner"))
    metadata = {
        "client": request.form.get("planner_client", "").strip(),
        "domain": request.form.get("planner_domain", "").strip(),
        "target_market": request.form.get("planner_target_market", "").strip(),
        "language": request.form.get("planner_language", "").strip(),
        "site_type": request.form.get("planner_site_type", "").strip(),
        "reference_content": request.form.get("planner_reference_content", "").strip(),
        "reference_filename": request.form.get("planner_reference_filename", "").strip(),
        "date": "",
    }
    return build_website_planner_report_response(metadata, plan)


def keyword_suggestions():
    state = {
        "topic": "",
        "target_country": get_default_country_target(),
        "target_countries": country_options(get_default_country_target()),
        "count": 30,
        "result": None,
        "error": None,
        "generation_log": [],
        "generation_log_json": "[]",
    }
    if request.method == "POST":
        state["topic"] = request.form.get("topic", "").strip()
        state["target_country"] = normalize_country_target(request.form.get("target_country", get_default_country_target()))
        state["target_countries"] = country_options(state["target_country"])
        state["generation_log"] = parse_generation_log(request.form.get("generation_log_json", ""))
        state["generation_log_json"] = generation_log_json(state["generation_log"])
        try:
            state["count"] = max(10, min(60, int(request.form.get("count", "30"))))
        except ValueError:
            state["count"] = 30
        try:
            provider = get_provider()
            progress = _keyword_suggestions_progress_callback(request.form.get("generation_status_token", ""), state["generation_log"])
            state["result"] = generate_keyword_suggestions(
                provider,
                topic=state["topic"],
                target_country=state["target_country"],
                count=state["count"],
                progress_callback=progress,
            )
            publish_generation_status(request.form.get("generation_status_token", ""), "Keyword Suggestions: Generation complete.")
            append_generation_log(state["generation_log"], "status", "Generation complete.")
        except Exception as exc:
            logger.exception("keyword suggestions action failed")
            append_generation_log(state["generation_log"], "error", str(exc) or "Generation failed.")
            state["error"] = generation_error_message(
                "Could not generate keyword suggestions. Check logs/app.log for details.",
                exc,
            )
    state["target_countries"] = country_options(state["target_country"])
    state["generation_log_json"] = generation_log_json(state.get("generation_log", []))
    return render_template("keyword_suggestions.html", **base_template_context(), **state)


def meta_generator():
    state = _default_meta_generator_state()
    if request.method == "POST":
        state["brand"] = request.form.get("brand", "").strip()
        state["page_type"] = request.form.get("page_type", "Blog").strip() or "Blog"
        state["keyword"] = keyword_from_page_type(state["page_type"])
        state["language"] = normalize_language(request.form.get("language", get_default_language()))
        state["generation_log"] = parse_generation_log(request.form.get("generation_log_json", ""))
        state["generation_log_json"] = generation_log_json(state["generation_log"])
        try:
            state["count"] = max(1, min(10, int(request.form.get("count", str(DEFAULT_META_OPTION_COUNT)))))
        except ValueError:
            state["count"] = DEFAULT_META_OPTION_COUNT

        try:
            provider = get_provider()
            progress = _meta_generator_progress_callback(request.form.get("generation_status_token", ""), state["generation_log"])
            state["result"] = generate_meta_titles_and_descriptions(
                provider,
                keyword=state["keyword"],
                page_type=state["page_type"],
                brand=state["brand"],
                brand_context=get_brand_context(state["brand"]),
                count=state["count"],
                language=state["language"],
                progress_callback=progress,
            )
            publish_generation_status(request.form.get("generation_status_token", ""), "Meta Generator: Generation complete.")
            append_generation_log(state["generation_log"], "status", "Generation complete.")
        except Exception as exc:
            logger.exception("meta generator action failed")
            append_generation_log(state["generation_log"], "error", str(exc) or "Generation failed.")
            state["error"] = generation_error_message(
                "Could not generate meta titles and descriptions. Check logs/app.log for details.",
                exc,
            )

    state["languages"] = language_options(state["language"])
    state["brand_names"] = list_brand_names()
    state["generation_log_json"] = generation_log_json(state.get("generation_log", []))
    return render_template("meta_generator.html", **base_template_context(), **state)


def gsc_planner():
    state = _default_gsc_planner_state()
    if request.method == "POST":
        action = request.form.get("action", "generate_report").strip()
        _apply_gsc_planner_form(state)
        if action == "chat":
            _handle_gsc_planner_chat(state)
        else:
            _handle_gsc_planner_report(state)

    state["languages"] = language_options(state["language"])
    state["brand_names"] = list_brand_names()
    state["brand_websites"] = _brand_website_map()
    state["generation_log_json"] = generation_log_json(state.get("generation_log", []))
    return render_template("gsc_planner.html", **base_template_context(), **state)


def download_gsc_summary_report():
    state = _default_gsc_planner_state()
    _apply_gsc_planner_form(state)
    if not state["report"]:
        return redirect(url_for("web.gsc_planner"))
    return build_gsc_summary_report_response(
        brand=state["brand"],
        target_url=state["target_url"],
        gsc_property=state["gsc_property"],
        start_date=state["gsc_start_date"],
        end_date=state["gsc_end_date"],
        report=state["report"],
        query_rows=state["gsc_api_rows"],
        daily_rows=state["gsc_api_daily_rows"],
        backlink_snapshot=state["backlink_snapshot"],
    )


def _default_meta_generator_state() -> dict:
    return {
        "keyword": "",
        "brand": "",
        "brand_names": list_brand_names(),
        "page_type": "Blog",
        "page_types": _meta_page_types(),
        "count": DEFAULT_META_OPTION_COUNT,
        "language": get_default_language(),
        "languages": language_options(get_default_language()),
        "meta_description_min_chars": META_DESCRIPTION_MIN_CHARS,
        "meta_description_max_chars": META_DESCRIPTION_MAX_CHARS,
        "result": None,
        "error": None,
    }


def _default_gsc_planner_state() -> dict:
    today = date.today()
    default_end = today - timedelta(days=2)
    default_start = default_end - timedelta(days=27)
    backlink_snapshot = _gsc_backlink_snapshot()
    return {
        "brand": "",
        "target_url": "",
        "gsc_property": "",
        "gsc_notes": "",
        "gsc_start_date": default_start.isoformat(),
        "gsc_end_date": default_end.isoformat(),
        "gsc_row_limit": 25,
        "gsc_api_summary": "",
        "gsc_api_notice": "",
        "gsc_api_rows": [],
        "gsc_api_rows_json": "[]",
        "gsc_api_daily_rows": [],
        "gsc_api_daily_rows_json": "[]",
        "backlink_snapshot": backlink_snapshot,
        "backlink_snapshot_json": json.dumps(backlink_snapshot, ensure_ascii=True),
        "backlink_summary": backlink_snapshot.get("summary", ""),
        "language": get_default_language(),
        "languages": language_options(get_default_language()),
        "brand_names": list_brand_names(),
        "brand_websites": _brand_website_map(),
        "report": None,
        "report_json": "",
        "chat_history": [],
        "chat_history_json": "[]",
        "chat_question": "",
        "generation_log": [],
        "generation_log_json": "[]",
        "error": None,
        "chat_error": None,
    }


def _gsc_backlink_snapshot() -> dict:
    backlinks = list_backlinks()
    items = [_gsc_backlink_item(item) for item in backlinks]
    scored_items = [item for item in items if item["authority_score"] is not None]
    top_high = sorted(scored_items, key=lambda item: (-item["authority_score"], item["name"].casefold()))[:5]
    lowest = sorted(scored_items, key=lambda item: (item["authority_score"], item["name"].casefold()))[:5]
    unscored_count = len(items) - len(scored_items)
    summary = _gsc_backlink_summary(
        total_count=len(items),
        scored_count=len(scored_items),
        unscored_count=unscored_count,
        top_high=top_high,
        lowest=lowest,
    )
    return {
        "total_count": len(items),
        "scored_count": len(scored_items),
        "unscored_count": unscored_count,
        "top_high": top_high,
        "lowest": lowest,
        "summary": summary,
    }


def _gsc_backlink_item(item: dict) -> dict:
    name = _clean_compact_text(item.get("website_name", "")) or "Unnamed medium"
    url = _clean_compact_text(item.get("blog_url", ""))
    authority_score = _extract_backlink_authority_score(item)
    authority_label = str(authority_score) if authority_score is not None else "Not saved"
    return {
        "id": item.get("id"),
        "name": name,
        "url": url,
        "type": _clean_compact_text(item.get("website_type", "")),
        "publication": _clean_compact_text(item.get("blog_name", "") or item.get("account_name", "")),
        "authority_score": authority_score,
        "authority_label": authority_label,
        "posts_per_day": item.get("posts_per_day", 0) or 0,
        "notes": _clean_compact_text(item.get("notes", "")),
    }


def _extract_backlink_authority_score(item: dict) -> int | None:
    explicit_score = _int_between(item.get("domain_power", 0), 0, 100, 0)
    if explicit_score:
        return explicit_score
    searchable_text = " ".join(
        _clean_compact_text(item.get(key, ""))
        for key in ("website_name", "blog_name", "blog_url", "content_guidelines", "notes")
    )
    patterns = [
        r"\b(?:dp|da|dr|domain\s+power|domain\s+authority|domain\s+rating)\s*[:=#-]?\s*(\d{1,3})\b",
        r"\b(\d{1,3})\s*(?:dp|da|dr)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, searchable_text, flags=re.IGNORECASE)
        if not match:
            continue
        value = _int_between(match.group(1), 0, 100, 0)
        return value
    return None


def _gsc_backlink_summary(total_count: int, scored_count: int, unscored_count: int, top_high: list[dict], lowest: list[dict]) -> str:
    lines = [
        f"Saved backlinks / publishing mediums: total={total_count}, with_saved_dp_da_dr={scored_count}, without_saved_dp_da_dr={unscored_count}.",
    ]
    if top_high:
        lines.append("Top high-DP/DA/DR saved links:")
        lines.extend(_gsc_backlink_summary_lines(top_high))
    if lowest:
        lines.append("Lowest-DP/DA/DR saved links:")
        lines.extend(_gsc_backlink_summary_lines(lowest))
    if total_count and not scored_count:
        lines.append("No DP/DA/DR values were found in saved backlink notes, names, URLs, or rules. Add values like DP 45, DA 32, or DR 50 to rank backlink strength.")
    elif not total_count:
        lines.append("No saved backlinks or publishing mediums were found.")
    lines.append("Backlinks can affect SEO through authority, trust, relevance, anchor context, and discovery. Treat this as supporting evidence unless backlink acquisition/loss timing is known.")
    return "\n".join(lines)


def _gsc_backlink_summary_lines(items: list[dict]) -> list[str]:
    lines = []
    for item in items:
        url = item.get("url") or "No URL saved"
        publication = f" / {item['publication']}" if item.get("publication") else ""
        lines.append(f"- {item['name']}{publication}: DP/DA/DR={item['authority_label']}; type={item.get('type') or 'unknown'}; url={url}")
    return lines


def _clean_compact_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _brand_website_map() -> dict:
    websites = {}
    for brand in list_brand_records():
        name = (brand.get("name") or "").strip()
        website = (brand.get("website") or "").strip()
        if name and website:
            websites[name] = website
    return websites


def _apply_gsc_planner_form(state: dict) -> None:
    state["brand"] = request.form.get("brand", "").strip()
    state["target_url"] = request.form.get("target_url", "").strip()
    state["gsc_property"] = request.form.get("gsc_property", "").strip()
    state["gsc_notes"] = request.form.get("gsc_notes", "").strip()
    state["gsc_start_date"] = request.form.get("gsc_start_date", state["gsc_start_date"]).strip()
    state["gsc_end_date"] = request.form.get("gsc_end_date", state["gsc_end_date"]).strip()
    state["gsc_row_limit"] = _int_between(request.form.get("gsc_row_limit", state["gsc_row_limit"]), 5, 100, 25)
    state["gsc_api_summary"] = request.form.get("gsc_api_summary", "").strip()
    state["gsc_api_notice"] = request.form.get("gsc_api_notice", "").strip()
    state["gsc_api_rows"] = _json_list_of_dicts(request.form.get("gsc_api_rows_json", ""))
    state["gsc_api_rows_json"] = json.dumps(state["gsc_api_rows"], ensure_ascii=True)
    state["gsc_api_daily_rows"] = _json_list_of_dicts(request.form.get("gsc_api_daily_rows_json", ""))
    state["gsc_api_daily_rows_json"] = json.dumps(state["gsc_api_daily_rows"], ensure_ascii=True)
    state["backlink_snapshot"] = _json_dict(request.form.get("backlink_snapshot_json", "")) or _gsc_backlink_snapshot()
    state["backlink_snapshot_json"] = json.dumps(state["backlink_snapshot"], ensure_ascii=True)
    state["backlink_summary"] = state["backlink_snapshot"].get("summary", "")
    state["language"] = normalize_language(request.form.get("language", get_default_language()))
    state["report"] = _json_dict(request.form.get("report_json", ""))
    state["report_json"] = json.dumps(state["report"], ensure_ascii=True) if state["report"] else ""
    state["chat_history"] = _json_list_of_dicts(request.form.get("chat_history_json", ""))
    state["chat_history_json"] = json.dumps(state["chat_history"], ensure_ascii=True)
    state["generation_log"] = parse_generation_log(request.form.get("generation_log_json", ""))
    state["generation_log_json"] = generation_log_json(state["generation_log"])


def _handle_gsc_planner_report(state: dict) -> None:
    if not state["target_url"] and state["brand"]:
        brand_record = get_brand_record(state["brand"]) or {}
        state["target_url"] = (brand_record.get("website") or "").strip()

    try:
        gsc_performance = fetch_gsc_performance_data(
            target_url=state["target_url"],
            start_date=state["gsc_start_date"],
            end_date=state["gsc_end_date"],
            site_url=state["gsc_property"],
            row_limit=state["gsc_row_limit"],
            access_token=get_setting("google_oauth_access_token", ""),
            service_account_json=get_setting("google_service_account_json", ""),
        )
        state["gsc_api_summary"] = gsc_performance.summary
        state["gsc_api_rows"] = gsc_performance.rows
        state["gsc_api_rows_json"] = json.dumps(state["gsc_api_rows"], ensure_ascii=True)
        state["gsc_api_daily_rows"] = gsc_performance.daily_rows
        state["gsc_api_daily_rows_json"] = json.dumps(state["gsc_api_daily_rows"], ensure_ascii=True)
        state["gsc_api_notice"] = (
            f"Fetched {len(gsc_performance.rows)} query row(s) and {len(gsc_performance.daily_rows)} daily row(s) from "
            f"{gsc_performance.start_date} to {gsc_performance.end_date} using {gsc_performance.site_url}."
        )
        provider = get_provider()
        progress = _gsc_planner_progress_callback(request.form.get("generation_status_token", ""), state["generation_log"])
        state["report"] = generate_gsc_seo_report(
            provider,
            brand=state["brand"],
            target_url=state["target_url"],
            gsc_notes=state["gsc_notes"],
            brand_context=get_brand_context(state["brand"]),
            gsc_api_summary=state["gsc_api_summary"],
            backlink_summary=state["backlink_summary"],
            language=state["language"],
            progress_callback=progress,
        )
        state["report_json"] = json.dumps(state["report"], ensure_ascii=True)
        state["chat_history"] = [
            {
                "role": "assistant",
                "content": "I have the GSC SEO report ready. Ask me what to do first, how to rewrite metadata, what content to add, or how to prioritize the fixes.",
            }
        ]
        state["chat_history_json"] = json.dumps(state["chat_history"], ensure_ascii=True)
        publish_generation_status(request.form.get("generation_status_token", ""), "GSC Planner: Report complete.")
        append_generation_log(state["generation_log"], "status", "Report complete.")
    except Exception as exc:
        logger.exception("gsc planner report action failed")
        append_generation_log(state["generation_log"], "error", str(exc) or "Generation failed.")
        state["error"] = generation_error_message(
            "Could not generate the GSC SEO report. Check logs/app.log for details.",
            exc,
        )


def _handle_gsc_planner_chat(state: dict) -> None:
    state["chat_question"] = request.form.get("chat_question", "").strip()
    if not state["report"]:
        state["chat_error"] = "Generate a GSC SEO report before using the chat assistant."
        return
    try:
        provider = get_provider()
        answer = answer_gsc_planner_chat(
            provider,
            question=state["chat_question"],
            report=state["report"],
            brand=state["brand"],
            target_url=state["target_url"],
            gsc_notes=state["gsc_notes"],
            brand_context=get_brand_context(state["brand"]),
            language=state["language"],
            chat_history=state["chat_history"],
            progress_callback=_gsc_planner_progress_callback(request.form.get("generation_status_token", ""), state["generation_log"]),
        )
        state["chat_history"].append({"role": "user", "content": state["chat_question"]})
        state["chat_history"].append({"role": "assistant", "content": answer})
        state["chat_history_json"] = json.dumps(state["chat_history"], ensure_ascii=True)
        state["chat_question"] = ""
    except Exception as exc:
        logger.exception("gsc planner chat action failed")
        append_generation_log(state["generation_log"], "error", str(exc) or "Generation failed.")
        state["chat_error"] = generation_error_message(
            "Could not answer the GSC planner chat question. Check logs/app.log for details.",
            exc,
        )


def _gsc_planner_progress_callback(token: str, log_entries: list[dict] | None = None):
    cleaned_token = (token or "").strip()

    def progress(message: str, kind: str = "status") -> None:
        if log_entries is not None:
            append_generation_log(log_entries, kind, message)
        if not cleaned_token:
            return
        if kind == "prompt":
            publish_generation_prompt(cleaned_token, message)
            publish_generation_status(cleaned_token, "GSC Planner: Analyzing Search Console evidence...")
            return
        publish_generation_status(cleaned_token, f"GSC Planner: {message}")

    return progress


def _meta_page_types() -> list[str]:
    return [
        "Blog",
        "Homepage",
        "Blog Page",
        "Service Page",
        "Product Page",
        "Category Page",
        "Author Page",
        "Landing Page",
        "About Page",
        "Contact Page",
    ]


def _meta_generator_progress_callback(token: str, log_entries: list[dict] | None = None):
    cleaned_token = (token or "").strip()

    def progress(message: str, kind: str = "status") -> None:
        if log_entries is not None:
            append_generation_log(log_entries, kind, message)
        if not cleaned_token:
            return
        if kind == "prompt":
            publish_generation_prompt(cleaned_token, message)
            publish_generation_status(cleaned_token, "Meta Generator: Creating metadata options...")
            return
        publish_generation_status(cleaned_token, f"Meta Generator: {message}")

    return progress


def _json_dict(raw: str) -> dict:
    try:
        parsed = json.loads(raw) if raw else {}
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _json_list_of_dicts(raw: str) -> list[dict]:
    try:
        parsed = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _keyword_suggestions_progress_callback(token: str, log_entries: list[dict] | None = None):
    cleaned_token = (token or "").strip()

    def progress(message: str, kind: str = "status") -> None:
        if log_entries is not None:
            append_generation_log(log_entries, kind, message)
        if not cleaned_token:
            return
        if kind == "prompt":
            publish_generation_prompt(cleaned_token, message)
            publish_generation_status(cleaned_token, "Keyword Suggestions: Generating keyword estimates...")
            return
        publish_generation_status(cleaned_token, f"Keyword Suggestions: {message}")

    return progress


def _default_context_planner_state() -> dict:
    return {
        "content_type": "Blog",
        "topic": "",
        "brand": "",
        "medium": "",
        "target_country": get_default_country_target(),
        "language": get_default_language(),
        "audience": "",
        "search_intent": "Informational",
        "primary_keyword": "",
        "supporting_keywords": "",
        "entities": "",
        "must_include": "",
        "avoid": "",
        "internal_links": "",
        "competitor_notes": "",
        "outline_notes": "",
        "cta": "",
        "context_brief": "",
        "success": None,
        "brand_names": list_brand_names(),
        "mediums": list_backlinks(),
        "target_countries": country_options(get_default_country_target()),
        "languages": language_options(get_default_language()),
    }


def _planner_count(value: str, default: int) -> int:
    try:
        return max(0, min(500, int(value or default)))
    except (TypeError, ValueError):
        return default


def _planner_reference_page_items(pages: list[dict]) -> list[dict]:
    items = []
    for index, page in enumerate(pages, start=1):
        keyword = " ".join(str(page.get("keyword") or page.get("name") or page.get("h1") or "").split()).strip()
        if not keyword:
            continue
        h1 = " ".join(str(page.get("h1") or keyword).split()).strip()
        headings = []
        seen = set()
        for heading in page.get("headings", []):
            cleaned = " ".join(str(heading or "").split()).strip()
            key = cleaned.casefold()
            if cleaned and key not in seen:
                seen.add(key)
                headings.append(cleaned)
        items.append(
            {
                "type": "page",
                "index": len(items) + 1,
                "name": keyword,
                "keyword": keyword,
                "h1": h1,
                "headings": headings,
                "source": "DOCX reference",
            }
        )
    return items


def _int_between(value, minimum: int, maximum: int, default: int) -> int:
    try:
        return max(minimum, min(maximum, int(value or default)))
    except (TypeError, ValueError):
        return default


def _merge_planner_categories(*groups) -> list[str]:
    categories = []
    seen = set()
    for group in groups:
        for item in group or []:
            cleaned = " ".join(str(item or "").split()).strip()
            normalized = cleaned.casefold()
            if cleaned and normalized not in seen:
                seen.add(normalized)
                categories.append(cleaned)
    return categories


def _build_context_brief(state: dict) -> str:
    lines = ["CONTEXT BRIEF", ""]
    _append_context_lines(
        lines,
        [
            ("Content type", state.get("content_type")),
            ("Topic", state.get("topic")),
            ("Brand", state.get("brand")),
            ("Medium / Website", state.get("medium")),
            ("Target country / region", state.get("target_country")),
            ("Language", state.get("language")),
            ("Audience", state.get("audience")),
            ("Search intent", state.get("search_intent")),
        ],
    )
    _append_context_section(
        lines,
        "SEO TARGETS",
        [
            ("Primary keyword", state.get("primary_keyword")),
            ("Supporting keywords", state.get("supporting_keywords")),
            ("Entities / topics to mention", state.get("entities")),
        ],
    )
    _append_context_section(
        lines,
        "CONTENT RULES",
        [
            ("Must include", state.get("must_include")),
            ("Avoid", state.get("avoid")),
            ("Internal links to use", state.get("internal_links")),
            ("Competitor / SERP notes", state.get("competitor_notes")),
            ("Outline notes", state.get("outline_notes")),
            ("CTA", state.get("cta")),
        ],
    )
    lines.extend([
        "",
        "Use this brief as the source of truth. Keep the generated content aligned with the target audience, intent, region, language, keywords, required points, and exclusions above.",
    ])
    return "\n".join(lines)


def _append_context_section(lines: list[str], title: str, fields: list[tuple[str, str]]) -> None:
    section_lines: list[str] = []
    _append_context_lines(section_lines, fields)
    if not section_lines:
        return
    lines.extend(["", title, *section_lines])


def _append_context_lines(lines: list[str], fields: list[tuple[str, str]]) -> None:
    for label, value in fields:
        cleaned_value = " ".join(str(value or "").split()).strip()
        if cleaned_value:
            lines.append(f"{label}: {cleaned_value}")


def seo_checker():
    state = {
        "url": "",
        "ignore_ssl_errors": False,
        "limit": 10,
        "result": None,
        "error": None,
        "generation_log": [],
        "generation_log_json": "[]",
    }

    if request.method == "POST":
        state["url"] = request.form.get("url", "").strip()
        state["ignore_ssl_errors"] = request.form.get("ignore_ssl_errors") == "1"
        state["generation_log"] = parse_generation_log(request.form.get("generation_log_json", ""))
        state["generation_log_json"] = generation_log_json(state["generation_log"])
        try:
            state["limit"] = max(1, min(100, int(request.form.get("limit", "10"))))
        except ValueError:
            state["limit"] = 10
        try:
            progress = _seo_checker_progress_callback(request.form.get("generation_status_token", ""), state["generation_log"])
            state["result"] = _run_site_seo_checks(
                state["url"],
                limit=state["limit"],
                verify_ssl=not state["ignore_ssl_errors"],
                progress_callback=progress,
            )
            publish_generation_status(request.form.get("generation_status_token", ""), "Website SEO Checker: Check complete.")
            append_generation_log(state["generation_log"], "status", "Check complete.")
        except Exception as exc:
            logger.exception("seo_checker action failed")
            append_generation_log(state["generation_log"], "error", str(exc) or "SEO check failed.")
            state["error"] = str(exc) or "Could not complete the SEO check."

    state["generation_log_json"] = generation_log_json(state.get("generation_log", []))
    return render_template("seo_checker.html", **base_template_context(), **state)


def _run_site_seo_checks(raw_url: str, limit: int = 10, verify_ssl: bool = True, progress_callback=None) -> dict:
    _publish_seo_progress(progress_callback, "Listing pages...")
    discovery = discover_website_pages(raw_url, limit=limit)
    page_urls = discovery.pages[:limit] or [discovery.base_url]
    page_results = []
    checked_pages = []
    total_pages = len(page_urls)

    _publish_seo_progress(progress_callback, f"Found {total_pages} page(s). Starting page checks...")

    for index, page_url in enumerate(page_urls, start=1):
        _publish_seo_progress(progress_callback, f"Checking page {index}/{total_pages}: {page_url}")
        try:
            audit = run_seo_audit(page_url, verify_ssl=verify_ssl)
            page_results.append(
                {
                    "index": index,
                    "url": page_url,
                    "status": "checked",
                    "result": audit,
                    "error": "",
                }
            )
            checked_pages.append(
                {
                    "index": index,
                    "url": page_url,
                    "status": "checked",
                    "score": audit.get("score", 0),
                    "grade": audit.get("grade", ""),
                    "error": "",
                }
            )
            _publish_seo_progress(progress_callback, f"Checked page {index}/{total_pages}: {page_url}")
        except Exception as exc:
            logger.exception("seo_checker page audit failed: url=%s", page_url)
            page_results.append(
                {
                    "index": index,
                    "url": page_url,
                    "status": "error",
                    "result": None,
                    "error": str(exc) or "Could not complete this page check.",
                }
            )
            checked_pages.append(
                {
                    "index": index,
                    "url": page_url,
                    "status": "error",
                    "score": None,
                    "grade": "",
                    "error": str(exc) or "Could not complete this page check.",
                }
            )
            _publish_seo_progress(progress_callback, f"Page {index}/{total_pages} failed: {page_url}")

    checked_results = [item["result"] for item in page_results if item.get("result")]
    average_score = round(sum(item["score"] for item in checked_results) / len(checked_results)) if checked_results else 0
    issue_count = sum(
        1
        for item in checked_results
        for check in item.get("checks", [])
        if check.get("status") in {"fail", "warn"}
    )
    not_found_link_count = sum(
        int(item.get("stats", {}).get("links", {}).get("not_found_count", 0) or 0)
        for item in checked_results
    )
    checked_link_count = sum(
        int(item.get("stats", {}).get("links", {}).get("checked_count", 0) or 0)
        for item in checked_results
    )
    return {
        "mode": "site",
        "source_url": raw_url,
        "base_url": discovery.base_url,
        "limit": limit,
        "discovered_pages": page_urls,
        "discovery_errors": discovery.errors,
        "sitemaps": discovery.sitemaps,
        "pages": page_results,
        "checked_pages": checked_pages,
        "summary": {
            "discovered_count": len(page_urls),
            "checked_count": len(checked_results),
            "error_count": len(page_results) - len(checked_results),
            "average_score": average_score,
            "average_grade": _seo_grade(average_score),
            "issue_count": issue_count,
            "not_found_link_count": not_found_link_count,
            "checked_link_count": checked_link_count,
        },
    }


def _seo_grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _seo_checker_progress_callback(token: str, log_entries: list[dict] | None = None):
    cleaned_token = (token or "").strip()

    def progress(message: str) -> None:
        if log_entries is not None:
            append_generation_log(log_entries, "status", message)
        if not cleaned_token:
            return
        publish_generation_status(cleaned_token, f"Website SEO Checker: {message}")

    return progress


def _publish_seo_progress(progress_callback, message: str) -> None:
    if not progress_callback:
        return
    try:
        progress_callback(message)
    except Exception:
        logger.exception("SEO checker progress callback failed")


def website_index_dashboard():
    success = request.args.get("success", "").strip()
    error = request.args.get("error", "").strip()

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        if action == "delete_domain":
            domain = request.form.get("domain", "").strip().lower()
            try:
                deleted_count = delete_website_index_urls_by_domain(domain)
                logger.info("Website Index dashboard deleted domain group: domain=%s deleted=%d", domain, deleted_count)
                if deleted_count:
                    return redirect(url_for("web.website_index_dashboard", success=f"Deleted {deleted_count} URL(s) for {domain}."))
                return redirect(url_for("web.website_index_dashboard", error=f"No saved URLs found for {domain or 'that domain'}."))
            except Exception as exc:
                logger.exception("Website Index dashboard domain delete failed: domain=%s", domain)
                return redirect(url_for("web.website_index_dashboard", error=str(exc) or "Could not delete that domain group."))
        if action == "delete_url":
            url = request.form.get("url", "").strip()
            try:
                deleted_count = delete_website_index_url(url)
                logger.info("Website Index dashboard deleted URL: url=%s deleted=%d", url, deleted_count)
                if deleted_count:
                    return redirect(url_for("web.website_index_dashboard", success="Removed that URL from Website Index."))
                return redirect(url_for("web.website_index_dashboard", error="That URL was not found in Website Index."))
            except Exception as exc:
                logger.exception("Website Index dashboard URL delete failed: url=%s", url)
                return redirect(url_for("web.website_index_dashboard", error=str(exc) or "Could not delete that URL."))
        if action == "trigger_due_job":
            try:
                trigger_website_index_batch()
                return redirect(url_for("web.website_index_dashboard", success="Website Index job triggered. Watch Background Jobs or app logs for progress."))
            except Exception as exc:
                logger.exception("Website Index dashboard manual trigger failed")
                return redirect(url_for("web.website_index_dashboard", error=str(exc) or "Could not trigger the Website Index job."))

    urls = list_website_index_urls()
    due_urls = list_due_website_index_urls()
    due_lookup = {item["url"] for item in due_urls}
    for item in urls:
        item["is_due"] = item["url"] in due_lookup
        item["domain"] = _url_domain(item["url"])
    urls = sorted(urls, key=_website_index_dashboard_sort_key)
    domain_stats = _website_index_domain_stats(urls)
    return render_template(
        "website_index_dashboard.html",
        **base_template_context(),
        urls=urls,
        domains=[item["domain"] for item in domain_stats],
        domain_stats=domain_stats,
        due_count=len(due_urls),
        stats=website_index_stats(),
        success=success,
        error=error,
    )


def website_pages():
    saved_urls = list_website_index_urls()
    for item in saved_urls:
        item["domain"] = _url_domain(item.get("url", ""))
    saved_domains = _website_index_domain_stats(saved_urls)
    selected_domain = request.args.get("domain", "").strip().lower()
    selected_domain_urls = _website_pages_for_domain(saved_urls, selected_domain)
    selected_domain_pagination = _paginate_items(
        selected_domain_urls,
        request.args.get("page", "1"),
        per_page=WEBSITE_PAGES_PER_PAGE,
    )
    state = {
        "site_url": "",
        "limit": 50,
        "result": None,
        "saved_domains": saved_domains,
        "selected_domain": selected_domain,
        "selected_domain_urls": selected_domain_urls,
        "selected_domain_page_urls": selected_domain_pagination["items"],
        "selected_domain_pagination": selected_domain_pagination,
        "saved_count": 0,
        "error": None,
        "success": None,
    }
    if request.method == "POST":
        action = request.form.get("action", "discover")
        state["site_url"] = request.form.get("site_url", "").strip()
        try:
            state["limit"] = max(1, min(1000, int(request.form.get("limit", "50"))))
        except ValueError:
            state["limit"] = 50

        try:
            if action == "save":
                page_records = _website_page_records_from_form()
                urls = [item["url"] for item in page_records]
                state["saved_count"] = upsert_website_index_urls(page_records)
                state["success"] = f"Saved {state['saved_count']} page URL(s)."
                saved_urls = list_website_index_urls()
                for item in saved_urls:
                    item["domain"] = _url_domain(item.get("url", ""))
                state["saved_domains"] = _website_index_domain_stats(saved_urls)
                state["selected_domain"] = _url_domain(urls[0]) if urls else selected_domain
                state["selected_domain_urls"] = _website_pages_for_domain(saved_urls, state["selected_domain"])
                state["selected_domain_pagination"] = _paginate_items(
                    state["selected_domain_urls"],
                    1,
                    per_page=WEBSITE_PAGES_PER_PAGE,
                )
                state["selected_domain_page_urls"] = state["selected_domain_pagination"]["items"]
                if state["site_url"]:
                    state["result"] = discover_website_pages(state["site_url"], limit=state["limit"])
            else:
                state["result"] = discover_website_pages(state["site_url"], limit=state["limit"])
                page_count = len(state["result"].pages)
                state["success"] = f"Found {page_count} page URL(s)." if page_count else "No page URLs were discovered."
        except Exception as exc:
            logger.exception("website pages action failed")
            state["error"] = str(exc) or "Could not list website pages."

    return render_template("website_pages.html", **base_template_context(), **state)


def download_website_pages_csv():
    selected_domain = request.args.get("domain", "").strip().lower()
    saved_urls = list_website_index_urls()
    for item in saved_urls:
        item["domain"] = _url_domain(item.get("url", ""))
    rows = _website_pages_for_domain(saved_urls, selected_domain)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "url",
        "domain",
        "check_status",
        "google_status",
        "page_keywords",
        "google_coverage_state",
        "google_indexing_state",
        "google_last_crawl_time",
        "bing_status",
        "bing_last_checked_at",
        "yahoo_status",
        "yahoo_last_checked_at",
        "last_checked_at",
        "last_error",
    ])
    for item in rows:
        writer.writerow([
            item.get("url", ""),
            item.get("domain", ""),
            item.get("check_status", ""),
            item.get("google_status", ""),
            item.get("page_keywords", ""),
            item.get("google_coverage_state", ""),
            item.get("google_indexing_state", ""),
            item.get("google_last_crawl_time", ""),
            item.get("bing_status", ""),
            item.get("bing_last_checked_at", ""),
            item.get("yahoo_status", ""),
            item.get("yahoo_last_checked_at", ""),
            item.get("last_checked_at", ""),
            item.get("last_error", ""),
        ])

    filename_domain = _safe_csv_filename_part(selected_domain or "all-websites")
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=website-pages-{filename_domain}.csv"},
    )


def _url_domain(url: str) -> str:
    parsed = urlparse(url or "")
    return parsed.netloc.lower()


def _website_page_records_from_form() -> list[dict]:
    selected_urls = request.form.getlist("selected_urls")
    if not selected_urls:
        selected_urls = extract_urls(request.form.get("discovered_urls", ""))
    selected_lookup = set(selected_urls)
    keyword_map = {}
    for value in request.form.getlist("page_keyword_records"):
        url, separator, keywords = (value or "").partition("|||")
        cleaned_url = url.strip()
        if separator and cleaned_url:
            keyword_map[cleaned_url] = keywords.strip()
    return [
        {
            "url": url,
            "page_keywords": keyword_map.get(url, ""),
        }
        for url in selected_urls
        if url in selected_lookup
    ]


def _website_index_dashboard_sort_key(item: dict) -> tuple:
    last_checked_at = (item.get("last_checked_at") or "").strip()
    return (
        0 if item.get("is_due") else 1,
        0 if not last_checked_at else 1,
        last_checked_at,
        item.get("id") or 0,
    )


def _website_index_domain_stats(urls: list[dict]) -> list[dict]:
    stats_by_domain = {}
    for item in urls:
        domain = item.get("domain") or _url_domain(item.get("url", ""))
        if not domain:
            continue
        stats = stats_by_domain.setdefault(
            domain,
            {"domain": domain, "total": 0, "indexed": 0, "not_indexed": 0, "errors": 0, "unchecked": 0},
        )
        stats["total"] += 1
        if item.get("google_status") == "indexed":
            stats["indexed"] += 1
        elif item.get("google_status") == "not-indexed":
            stats["not_indexed"] += 1
        elif item.get("google_status") == "error":
            stats["errors"] += 1
        else:
            stats["unchecked"] += 1
    domain_stats = []
    for stats in stats_by_domain.values():
        total = stats["total"]
        indexed = stats["indexed"]
        domain_stats.append({
            **stats,
            "percent": round((indexed / total) * 100, 1) if total else 0,
        })
    return sorted(domain_stats, key=lambda item: item["domain"])


def _website_pages_for_domain(urls: list[dict], domain: str) -> list[dict]:
    cleaned_domain = (domain or "").strip().lower()
    if not cleaned_domain:
        return []
    return [item for item in urls if item.get("domain") == cleaned_domain]


def _safe_csv_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value or "").strip("-")
    return cleaned or "website"


def _paginate_items(items: list, page_value, per_page: int = 50) -> dict:
    total = len(items)
    per_page = max(1, int(per_page or 50))
    total_pages = max(1, (total + per_page - 1) // per_page)
    try:
        current_page = int(page_value)
    except (TypeError, ValueError):
        current_page = 1
    current_page = max(1, min(total_pages, current_page))
    start = (current_page - 1) * per_page
    end = start + per_page
    page_numbers = [
        page_number
        for page_number in range(max(1, current_page - 2), min(total_pages, current_page + 2) + 1)
    ]
    return {
        "items": items[start:end],
        "page": current_page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "start": start + 1 if total else 0,
        "end": min(end, total),
        "has_previous": current_page > 1,
        "has_next": current_page < total_pages,
        "previous_page": current_page - 1,
        "next_page": current_page + 1,
        "page_numbers": page_numbers,
    }


def indexnow():
    saved_index_urls = list_website_index_urls()
    state = {
        "host": "",
        "key": get_setting("indexnow_key", ""),
        "key_location": get_setting("indexnow_key_location", ""),
        "endpoint": get_setting("indexnow_endpoint", DEFAULT_INDEXNOW_ENDPOINT),
        "google_access_token": get_setting("google_oauth_access_token", ""),
        "google_service_account_json": get_setting("google_service_account_json", ""),
        "google_notification_type": "URL_UPDATED",
        "url_list": "",
        "website_index_urls": saved_index_urls,
        "due_count": len(list_due_website_index_urls()),
        "indexnow_result": None,
        "google_result": None,
        "google_inspection_result": None,
        "error": None,
        "success": None,
        "parsed_count": 0,
    }

    if request.method == "POST":
        action = request.form.get("action", "indexnow")
        state["host"] = request.form.get("host", "").strip()
        state["key"] = request.form.get("key", "").strip()
        state["key_location"] = request.form.get("key_location", "").strip()
        state["endpoint"] = request.form.get("endpoint", DEFAULT_INDEXNOW_ENDPOINT).strip() or DEFAULT_INDEXNOW_ENDPOINT
        state["google_access_token"] = request.form.get("google_access_token", "").strip()
        state["google_service_account_json"] = request.form.get("google_service_account_json", "").strip()
        state["google_notification_type"] = request.form.get("google_notification_type", "URL_UPDATED").strip()
        state["url_list"] = request.form.get("url_list", "")

        file_text = ""
        upload = request.files.get("url_file")
        if upload and upload.filename:
            file_text = upload.read().decode("utf-8-sig", errors="replace")

        service_account_upload = request.files.get("google_service_account_file")
        if service_account_upload and service_account_upload.filename:
            state["google_service_account_json"] = service_account_upload.read().decode("utf-8-sig", errors="replace")

        urls = extract_urls(state["url_list"], file_text)
        state["parsed_count"] = len(urls)
        if urls:
            saved_url_list = "\n".join(dict.fromkeys(urls))
            set_setting("indexnow_url_list", saved_url_list)
            upsert_website_index_urls(urls)
            state["url_list"] = ""
        try:
            action_started_at = time.perf_counter()
            logger.info("Website Index action started: action=%s parsed_urls=%d", action, len(urls))
            if action == "save_urls":
                state["success"] = "URL list saved."
            elif action == "google":
                state["google_result"] = submit_google_indexing_urls(
                    urls=urls,
                    access_token=state["google_access_token"],
                    service_account_json=state["google_service_account_json"],
                    notification_type=state["google_notification_type"],
                    endpoint=GOOGLE_INDEXING_ENDPOINT,
                )
                _log_google_indexing_result(state["google_result"], time.perf_counter() - action_started_at)
            elif action == "google_inspect":
                urls_to_check = urls[:WEBSITE_INDEX_CHECK_LIMIT]
                logger.info("Website Index Google inspection started: urls=%d limit=%d", len(urls_to_check), WEBSITE_INDEX_CHECK_LIMIT)
                mark_website_index_urls_checking(urls_to_check)
                state["google_inspection_result"] = inspect_google_index_status_by_url_domain(
                    urls=urls_to_check,
                    access_token=state["google_access_token"],
                    service_account_json=state["google_service_account_json"],
                )
                for item in state["google_inspection_result"].items:
                    update_website_index_google_result(item)
                _log_google_inspection_result(state["google_inspection_result"], time.perf_counter() - action_started_at)
                if len(urls) > WEBSITE_INDEX_CHECK_LIMIT:
                    state["success"] = f"Checked the first {WEBSITE_INDEX_CHECK_LIMIT} URL(s). Run again for the next batch."
            elif action == "weekly_check":
                logger.info("Website Index due check selecting due URLs.")
                due_rows = list_due_website_index_urls()
                due_urls = [item["url"] for item in due_rows[:WEBSITE_INDEX_CHECK_LIMIT]]
                submit_due_lookup = {item["url"] for item in list_due_website_index_submission_urls()}
                submit_urls = [url for url in due_urls if url in submit_due_lookup]
                logger.info(
                    "Website Index due check selected: due_total=%d batch_urls=%d submit_urls=%d limit=%d",
                    len(due_rows),
                    len(due_urls),
                    len(submit_urls),
                    WEBSITE_INDEX_CHECK_LIMIT,
                )
                if not due_urls:
                    state["success"] = "No saved URLs are due for a Google index check."
                else:
                    phase_started_at = time.perf_counter()
                    mark_website_index_urls_checking(due_urls)
                    logger.info("Website Index marked %d URL(s) checking in %.2fs.", len(due_urls), time.perf_counter() - phase_started_at)
                    phase_started_at = time.perf_counter()
                    indexnow_due_result = submit_website_index_urls_to_indexnow(
                        submit_urls,
                        key=state["key"],
                        key_location=state["key_location"],
                        endpoint=state["endpoint"],
                    )
                    logger.info(
                        "Website Index due IndexNow submit finished in %.2fs: hosts=%d submitted=%d skipped=%d errors=%d",
                        time.perf_counter() - phase_started_at,
                        indexnow_due_result["hosts"],
                        indexnow_due_result["submitted"],
                        indexnow_due_result["skipped"],
                        len(indexnow_due_result["errors"]),
                    )
                    phase_started_at = time.perf_counter()
                    update_website_index_bing_yahoo_weekly_result(due_urls)
                    logger.info("Website Index marked Bing/Yahoo manual for %d URL(s) in %.2fs.", len(due_urls), time.perf_counter() - phase_started_at)
                    if state["google_access_token"] or state["google_service_account_json"]:
                        logger.info("Website Index due Google inspection started: urls=%d", len(due_urls))
                        state["google_inspection_result"] = inspect_google_index_status_by_url_domain(
                            urls=due_urls,
                            access_token=state["google_access_token"],
                            service_account_json=state["google_service_account_json"],
                        )
                        for item in state["google_inspection_result"].items:
                            update_website_index_google_result(item)
                        _log_google_inspection_result(state["google_inspection_result"], time.perf_counter() - action_started_at)
                        state["success"] = f"Due check submitted {indexnow_due_result['submitted']} URL(s) to IndexNow and ran Google inspection for {len(due_urls)} URL(s). Bing/Yahoo were marked for manual webmaster review."
                    else:
                        logger.warning("Website Index due check skipped Google inspection because Google settings are incomplete.")
                        state["success"] = f"Due check submitted {indexnow_due_result['submitted']} URL(s) to IndexNow and marked Bing/Yahoo for {len(due_urls)} URL(s). Add Google credentials to include Google URL Inspection."
                    if indexnow_due_result["errors"]:
                        state["success"] += f" IndexNow reported {len(indexnow_due_result['errors'])} issue(s); check logs for details."
                    if len(due_rows) > WEBSITE_INDEX_CHECK_LIMIT:
                        state["success"] += f" {len(due_rows) - WEBSITE_INDEX_CHECK_LIMIT} URL(s) remain queued for the next run."
            elif action == "sitemap":
                sitemap_xml = build_sitemap_xml(urls)
                return Response(
                    sitemap_xml,
                    mimetype="application/xml",
                    headers={"Content-Disposition": "attachment; filename=sitemap.xml"},
                )
            else:
                state["indexnow_result"] = submit_indexnow_urls(
                    urls=urls,
                    key=state["key"],
                    host=state["host"],
                    key_location=state["key_location"],
                    endpoint=state["endpoint"],
                )
                logger.info(
                    "Website Index IndexNow action finished in %.2fs: submitted=%d skipped=%d batches=%d",
                    time.perf_counter() - action_started_at,
                    state["indexnow_result"].submitted_count,
                    len(state["indexnow_result"].skipped),
                    len(state["indexnow_result"].batches),
                )
            logger.info("Website Index action finished: action=%s elapsed=%.2fs", action, time.perf_counter() - action_started_at)
        except Exception as exc:
            logger.exception("Website Index action failed: action=%s parsed_urls=%d elapsed=%.2fs", action, len(urls), time.perf_counter() - action_started_at)
            state["error"] = str(exc) or "Could not complete the indexing action."

    state["website_index_urls"] = list_website_index_urls()
    state["due_count"] = len(list_due_website_index_urls())
    return render_template("indexnow.html", **base_template_context(), **state)


def _log_google_inspection_result(result, elapsed_seconds: float) -> None:
    error_items = [item for item in result.items if item.status == "error"]
    logger.info(
        "Website Index Google inspection finished in %.2fs: inspected=%d skipped=%d errors=%d",
        elapsed_seconds,
        result.inspected_count,
        len(result.skipped),
        len(error_items),
    )
    for item in error_items[:20]:
        logger.error(
            "Website Index Google inspection URL error: url=%s status_code=%s detail=%s",
            item.url,
            item.status_code,
            item.detail,
        )
    if len(error_items) > 20:
        logger.error("Website Index Google inspection had %d additional URL error(s).", len(error_items) - 20)


def _log_google_indexing_result(result, elapsed_seconds: float) -> None:
    error_items = [item for item in result.items if item.status == "error"]
    logger.info(
        "Website Index Google publish finished in %.2fs: submitted=%d skipped=%d errors=%d",
        elapsed_seconds,
        result.submitted_count,
        len(result.skipped),
        len(error_items),
    )
    for item in error_items[:20]:
        logger.error(
            "Website Index Google publish URL error: url=%s status_code=%s detail=%s",
            item.url,
            item.status_code,
            item.detail,
        )
    if len(error_items) > 20:
        logger.error("Website Index Google publish had %d additional URL error(s).", len(error_items) - 20)


def preview():
    return render_template(
        "preview.html",
        title=request.form.get("selected_title", ""),
        keyword=request.form.get("keyword", ""),
        supporting_keyword=request.form.get("supporting_keyword", ""),
        meta_description=request.form.get("meta_description", ""),
        medium_name=request.form.get("medium_name", ""),
        tags=request.form.get("tags", ""),
        content_html=request.form.get("content_html", ""),
    )


def download_doc():
    return build_docx_response(
        title=request.form.get("selected_title", ""),
        keyword=request.form.get("keyword", ""),
        supporting_keyword=request.form.get("supporting_keyword", ""),
        meta_description=request.form.get("meta_description", ""),
        medium_name=request.form.get("medium_name", ""),
        tags=request.form.get("tags", ""),
        content_html=request.form.get("content_html", ""),
    )
