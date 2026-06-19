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
from app.services.locale_settings import country_options, get_default_country_target, normalize_country_target
from app.services.provider_service import generation_error_message, get_provider
from app.services.seo_checker_service import run_seo_audit
from database import get_setting, set_setting
from database import list_due_website_index_urls, list_website_index_urls, mark_website_index_urls_checking, update_website_index_bing_yahoo_weekly_result, update_website_index_google_result, upsert_website_index_urls, website_index_stats
from logger import logger


WEBSITE_INDEX_CHECK_LIMIT = 10


def text_tools():
    return render_template("text_tools.html", **base_template_context())


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
            state["result"] = generate_keyword_suggestions(
                provider,
                topic=state["topic"],
                target_country=state["target_country"],
                count=state["count"],
            )
        except Exception as exc:
            logger.exception("keyword suggestions action failed")
            state["error"] = generation_error_message(
                "Could not generate keyword suggestions. Check logs/app.log for details.",
                exc,
            )
    state["target_countries"] = country_options(state["target_country"])
    return render_template("keyword_suggestions.html", **base_template_context(), **state)


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


def _url_domain(url: str) -> str:
    parsed = urlparse(url or "")
    return parsed.netloc.lower()


def _website_index_domain_stats(urls: list[dict]) -> list[dict]:
    stats_by_domain = {}
    for item in urls:
        domain = item.get("domain") or _url_domain(item.get("url", ""))
        if not domain:
            continue
        stats = stats_by_domain.setdefault(domain, {"domain": domain, "total": 0, "indexed": 0})
        stats["total"] += 1
        if item.get("google_status") == "indexed":
            stats["indexed"] += 1
    domain_stats = []
    for stats in stats_by_domain.values():
        total = stats["total"]
        indexed = stats["indexed"]
        domain_stats.append({
            **stats,
            "percent": round((indexed / total) * 100, 1) if total else 0,
        })
    return sorted(domain_stats, key=lambda item: item["domain"])


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
                    state["success"] = "No saved URLs are due for a weekly Google index check."
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
                        state["success"] = f"Weekly check ran for {len(due_urls)} URL(s). Bing/Yahoo were marked for manual webmaster review."
                    else:
                        state["success"] = f"Weekly check marked Bing/Yahoo for {len(due_urls)} URL(s). Add Google settings to include Google URL Inspection."
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
