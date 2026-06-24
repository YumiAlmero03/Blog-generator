import csv
import io
import re

from flask import Response, render_template, request
from urllib.parse import urlparse

from app.controllers.helpers import base_template_context
from app.services.document_service import build_docx_response
from app.services.indexnow_service import (
    DEFAULT_INDEXNOW_ENDPOINT,
    GOOGLE_INDEXING_ENDPOINT,
    build_sitemap_xml,
    extract_urls,
    inspect_google_index_status,
    submit_google_indexing_urls,
    submit_indexnow_urls,
)
from app.services.keyword_suggestion_service import generate_keyword_suggestions
from app.services.locale_settings import (
    country_options,
    get_default_country_target,
    get_default_language,
    language_options,
    normalize_country_target,
    normalize_language,
)
from app.services.provider_service import generation_error_message, get_provider
from app.services.seo_checker_service import run_seo_audit
from app.services.generation_status_service import publish_generation_prompt, publish_generation_status
from app.services.website_page_discovery_service import discover_website_pages
from database import get_setting, list_backlinks, list_brand_names, set_setting
from database import list_due_website_index_urls, list_website_index_urls, mark_website_index_urls_checking, update_website_index_bing_yahoo_weekly_result, update_website_index_google_result, upsert_website_index_urls, website_index_stats
from logger import logger


WEBSITE_INDEX_CHECK_LIMIT = 10
WEBSITE_PAGES_PER_PAGE = 50


def text_tools():
    return render_template("text_tools.html", **base_template_context())


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


def keyword_suggestions():
    state = {
        "topic": "",
        "target_country": get_default_country_target(),
        "target_countries": country_options(get_default_country_target()),
        "count": 30,
        "result": None,
        "error": None,
    }
    if request.method == "POST":
        state["topic"] = request.form.get("topic", "").strip()
        state["target_country"] = normalize_country_target(request.form.get("target_country", get_default_country_target()))
        state["target_countries"] = country_options(state["target_country"])
        try:
            state["count"] = max(10, min(60, int(request.form.get("count", "30"))))
        except ValueError:
            state["count"] = 30
        try:
            provider = get_provider()
            progress = _keyword_suggestions_progress_callback(request.form.get("generation_status_token", ""))
            state["result"] = generate_keyword_suggestions(
                provider,
                topic=state["topic"],
                target_country=state["target_country"],
                count=state["count"],
                progress_callback=progress,
            )
            publish_generation_status(request.form.get("generation_status_token", ""), "Keyword Suggestions: Generation complete.")
        except Exception as exc:
            logger.exception("keyword suggestions action failed")
            state["error"] = generation_error_message(
                "Could not generate keyword suggestions. Check logs/app.log for details.",
                exc,
            )
    state["target_countries"] = country_options(state["target_country"])
    return render_template("keyword_suggestions.html", **base_template_context(), **state)


def _keyword_suggestions_progress_callback(token: str):
    cleaned_token = (token or "").strip()

    def progress(message: str, kind: str = "status") -> None:
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
        "result": None,
        "error": None,
    }

    if request.method == "POST":
        state["url"] = request.form.get("url", "").strip()
        state["ignore_ssl_errors"] = request.form.get("ignore_ssl_errors") == "1"
        try:
            state["result"] = run_seo_audit(state["url"], verify_ssl=not state["ignore_ssl_errors"])
        except Exception as exc:
            logger.exception("seo_checker action failed")
            state["error"] = str(exc) or "Could not complete the SEO check."

    return render_template("seo_checker.html", **base_template_context(), **state)


def website_index_dashboard():
    urls = list_website_index_urls()
    due_urls = list_due_website_index_urls()
    due_lookup = {item["url"] for item in due_urls}
    for item in urls:
        item["is_due"] = item["url"] in due_lookup
        item["domain"] = _url_domain(item["url"])
    domain_stats = _website_index_domain_stats(urls)
    return render_template(
        "website_index_dashboard.html",
        **base_template_context(),
        urls=urls,
        domains=[item["domain"] for item in domain_stats],
        domain_stats=domain_stats,
        due_count=len(due_urls),
        stats=website_index_stats(),
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
        "limit": 500,
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
            state["limit"] = max(1, min(1000, int(request.form.get("limit", "500"))))
        except ValueError:
            state["limit"] = 500

        try:
            if action == "save":
                urls = request.form.getlist("selected_urls")
                if not urls:
                    urls = extract_urls(request.form.get("discovered_urls", ""))
                state["saved_count"] = upsert_website_index_urls(urls)
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
        "key_location": "",
        "endpoint": DEFAULT_INDEXNOW_ENDPOINT,
        "google_access_token": get_setting("google_oauth_access_token", ""),
        "google_service_account_json": get_setting("google_service_account_json", ""),
        "google_site_url": get_setting("google_search_console_property", ""),
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
        state["google_site_url"] = request.form.get("google_site_url", "").strip()
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
        if state["google_site_url"]:
            set_setting("google_search_console_property", state["google_site_url"])
        try:
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
            elif action == "google_inspect":
                urls_to_check = urls[:WEBSITE_INDEX_CHECK_LIMIT]
                mark_website_index_urls_checking(urls_to_check)
                state["google_inspection_result"] = inspect_google_index_status(
                    urls=urls_to_check,
                    site_url=state["google_site_url"],
                    access_token=state["google_access_token"],
                    service_account_json=state["google_service_account_json"],
                )
                for item in state["google_inspection_result"].items:
                    update_website_index_google_result(item)
                if len(urls) > WEBSITE_INDEX_CHECK_LIMIT:
                    state["success"] = f"Checked the first {WEBSITE_INDEX_CHECK_LIMIT} URL(s). Run again for the next batch."
            elif action == "weekly_check":
                due_rows = list_due_website_index_urls()
                due_urls = [item["url"] for item in due_rows[:WEBSITE_INDEX_CHECK_LIMIT]]
                if not due_urls:
                    state["success"] = "No saved URLs are due for a Google index check."
                else:
                    mark_website_index_urls_checking(due_urls)
                    update_website_index_bing_yahoo_weekly_result(due_urls)
                    if state["google_site_url"] and (state["google_access_token"] or state["google_service_account_json"]):
                        state["google_inspection_result"] = inspect_google_index_status(
                            urls=due_urls,
                            site_url=state["google_site_url"],
                            access_token=state["google_access_token"],
                            service_account_json=state["google_service_account_json"],
                        )
                        for item in state["google_inspection_result"].items:
                            update_website_index_google_result(item)
                        state["success"] = f"Due check ran for {len(due_urls)} URL(s). Bing/Yahoo were marked for manual webmaster review."
                    else:
                        state["success"] = f"Due check marked Bing/Yahoo for {len(due_urls)} URL(s). Add Google settings to include Google URL Inspection."
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
        except Exception as exc:
            logger.exception("indexing action failed")
            state["error"] = str(exc) or "Could not complete the indexing action."

    state["website_index_urls"] = list_website_index_urls()
    state["due_count"] = len(list_due_website_index_urls())
    return render_template("indexnow.html", **base_template_context(), **state)


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
