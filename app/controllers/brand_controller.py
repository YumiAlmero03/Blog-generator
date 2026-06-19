import csv
from io import StringIO

from flask import Response, render_template, request

from database import check_keyword_usage, delete_brand, delete_brand_page, get_brand_pages, get_brand_record, list_brand_records, record_page, update_brand_page, upsert_brand
from database.common import normalize_brand_name
from logger import logger

from app.controllers.helpers import base_template_context, image_url
from app.services.image_service import BRAND_LOGO_DIR, save_uploaded_image


def brands():
    brand_color_palette = _brand_color_palette()
    state = {
        "brand_name": "",
        "website": "",
        "niche": "",
        "main_keywords": "",
        "tone": "",
        "notes": "",
        "planner_notes": "",
        "logo_path": "",
        "brand_color": "#b07042",
        "include_in_posting_planner": False,
        "include_in_backlink_follow_up": False,
        "include_in_website_checklist": False,
        "brand_preset": "",
        "check_brand": "",
        "check_keyword": "",
        "keyword_check_result": None,
        "error": None,
        "success": None,
    }

    edit_brand = request.args.get("edit", "").strip()
    if request.method == "GET" and edit_brand:
        _populate_brand_for_edit(state, edit_brand)

    if request.method == "POST":
        action = request.form.get("action", "save_brand").strip()
        if action == "save_brand":
            _handle_save_brand(state)
        elif action == "save_brand_color":
            _handle_save_brand_color(state)
        elif action == "delete_brand":
            _handle_delete_brand(state)
        elif action == "check_keyword":
            _handle_check_keyword(state)
        elif action == "import_brand_pages":
            _handle_import_brand_pages(state)
        elif action == "update_brand_page":
            _handle_update_brand_page(state)
        elif action == "delete_brand_page":
            _handle_delete_brand_page(state)
        elif action == "export_brand_pages":
            return _export_brand_pages_csv()
        elif action == "download_brand_pages_template":
            return _download_brand_pages_template_csv()

    brand_models = _build_brand_view_models()
    return render_template(
        "brands.html",
        **base_template_context(),
        **state,
        logo_url=image_url(state["logo_path"]),
        brands=brand_models,
        brand_color_filters=_build_brand_color_filters(brand_models),
        brand_color_palette=brand_color_palette,
        brand_presets=_brand_presets(),
    )


def _populate_brand_for_edit(state: dict, brand_name: str):
    brand_record = get_brand_record(brand_name)
    if not brand_record:
        return

    state["brand_name"] = brand_record.get("name", "")
    state["website"] = brand_record.get("website", "")
    state["niche"] = brand_record.get("niche", "")
    state["main_keywords"] = brand_record.get("main_keywords", "")
    state["tone"] = brand_record.get("tone", "")
    state["notes"] = brand_record.get("notes", "")
    state["planner_notes"] = brand_record.get("planner_notes", "")
    state["logo_path"] = brand_record.get("logo_path", "")
    state["brand_color"] = brand_record.get("brand_color", "") or _fallback_brand_color(state["brand_name"])
    state["include_in_posting_planner"] = bool(brand_record.get("include_in_posting_planner", 0))
    state["include_in_backlink_follow_up"] = bool(brand_record.get("include_in_backlink_follow_up", 0))
    state["include_in_website_checklist"] = bool(brand_record.get("include_in_website_checklist", 0))


def _handle_save_brand(state: dict):
    state["brand_name"] = request.form.get("brand_name", "").strip()
    state["website"] = request.form.get("website", "").strip()
    state["niche"] = request.form.get("niche", "").strip()
    state["main_keywords"] = request.form.get("main_keywords", "").strip()
    state["tone"] = request.form.get("tone", "").strip()
    state["notes"] = request.form.get("notes", "").strip()
    state["planner_notes"] = request.form.get("planner_notes", "").strip()
    state["brand_color"] = _normalize_color_input(request.form.get("brand_color", ""))
    state["include_in_posting_planner"] = request.form.get("include_in_posting_planner") == "1"
    state["include_in_backlink_follow_up"] = request.form.get("include_in_backlink_follow_up") == "1"
    state["include_in_website_checklist"] = request.form.get("include_in_website_checklist") == "1"
    state["brand_preset"] = request.form.get("brand_preset", "").strip()
    logo_upload = request.files.get("logo_file")

    if not state["brand_name"]:
        state["error"] = "Please enter a brand name."
        return

    try:
        _apply_brand_preset(state)
        if logo_upload and logo_upload.filename:
            state["logo_path"] = f"brand_logos/{save_uploaded_image(logo_upload, BRAND_LOGO_DIR, 'logo')}"

        upsert_brand(
            state["brand_name"],
            website=state["website"],
            tone=state["tone"],
            notes=state["notes"],
            planner_notes=state["planner_notes"],
            niche=state["niche"],
            main_keywords=state["main_keywords"],
            logo_path=state["logo_path"],
            brand_color=state["brand_color"],
            include_in_posting_planner=state["include_in_posting_planner"],
            include_in_backlink_follow_up=state["include_in_backlink_follow_up"],
            include_in_website_checklist=state["include_in_website_checklist"],
        )
        saved_name = state["brand_name"]
        state.update(
            {
                "brand_name": "",
                "website": "",
                "niche": "",
                "main_keywords": "",
                "tone": "",
                "notes": "",
                "planner_notes": "",
                "logo_path": "",
                "brand_color": "#b07042",
                "include_in_posting_planner": False,
                "include_in_backlink_follow_up": False,
                "include_in_website_checklist": False,
                "success": f"Saved brand: {saved_name}",
            }
        )
    except ValueError as exc:
        state["error"] = str(exc)
    except Exception:
        logger.exception("brands save action failed")
        state["error"] = "An error occurred while saving the brand. Check logs/app.log for details."


def _handle_check_keyword(state: dict):
    state["check_brand"] = request.form.get("check_brand", "").strip()
    state["check_keyword"] = request.form.get("check_keyword", "").strip()

    if not state["check_brand"] or not state["check_keyword"]:
        state["error"] = "Please enter both a brand and a keyword to check."
        return

    try:
        state["keyword_check_result"] = check_keyword_usage(state["check_brand"], state["check_keyword"])
    except Exception:
        logger.exception("brands check_keyword action failed")
        state["error"] = "An error occurred while checking the keyword. Check logs/app.log for details."


def _handle_save_brand_color(state: dict):
    brand_name = request.form.get("brand_name", "").strip()
    brand_color = _normalize_color_input(request.form.get("brand_color", ""))

    if not brand_name:
        state["error"] = "Please select a brand before saving a color."
        return
    if not brand_color:
        state["error"] = "Please choose a valid brand color."
        return

    try:
        upsert_brand(brand_name, brand_color=brand_color)
        state["success"] = f"Updated color for {brand_name}"
    except Exception:
        logger.exception("brands save_brand_color action failed")
        state["error"] = "An error occurred while saving the brand color. Check logs/app.log for details."


def _handle_delete_brand(state: dict):
    brand_name = request.form.get("brand_name", "").strip()
    if not brand_name:
        state["error"] = "Please select a brand to delete."
        return

    try:
        if delete_brand(brand_name):
            state["success"] = f"Deleted brand: {brand_name}"
        else:
            state["error"] = "Brand not found."
    except Exception:
        logger.exception("brands delete_brand action failed")
        state["error"] = "An error occurred while deleting the brand. Check logs/app.log for details."


def _handle_import_brand_pages(state: dict):
    brand_name = request.form.get("brand_name", "").strip()
    upload = request.files.get("pages_file")
    if not brand_name:
        state["error"] = "Please select a brand before importing pages."
        return
    if not upload or not upload.filename:
        state["error"] = "Please choose a CSV file to import."
        return

    try:
        text = upload.read().decode("utf-8-sig")
        reader = csv.DictReader(StringIO(text))
        imported = 0
        skipped = 0
        for row in reader:
            page_title = (row.get("page_title") or row.get("title") or row.get("Page title") or "").strip()
            primary_keyword = (row.get("primary_keyword") or row.get("keyword") or row.get("Primary keyword") or "").strip()
            if not page_title and not primary_keyword:
                skipped += 1
                continue
            record_page(
                brand=brand_name,
                keyword=primary_keyword,
                page_title=page_title,
                page_type=row.get("page_type", ""),
                supporting_keywords=row.get("supporting_keywords", ""),
                expectations=row.get("expectations", ""),
            )
            imported += 1
        state["success"] = f"Imported {imported} page{'s' if imported != 1 else ''} for {brand_name}."
        if skipped:
            state["success"] += f" Skipped {skipped} row{'s' if skipped != 1 else ''} without a page title or primary keyword."
    except UnicodeDecodeError:
        state["error"] = "Could not read the CSV file. Please upload a UTF-8 CSV."
    except Exception:
        logger.exception("brand pages import action failed")
        state["error"] = "An error occurred while importing brand pages. Check logs/app.log for details."


def _handle_update_brand_page(state: dict):
    page_id = request.form.get("page_id", "").strip()
    if not page_id.isdigit():
        state["error"] = "Please select a page to update."
        return

    try:
        if update_brand_page(
            int(page_id),
            page_title=request.form.get("page_title", ""),
            page_type=request.form.get("page_type", ""),
            primary_keyword=request.form.get("primary_keyword", ""),
            supporting_keywords=request.form.get("supporting_keywords", ""),
            expectations=request.form.get("expectations", ""),
        ):
            state["success"] = "Updated brand page."
        else:
            state["error"] = "Brand page not found."
    except Exception:
        logger.exception("brand page update action failed")
        state["error"] = "An error occurred while updating the page. Check logs/app.log for details."


def _handle_delete_brand_page(state: dict):
    page_id = request.form.get("page_id", "").strip()
    if not page_id.isdigit():
        state["error"] = "Please select a page to delete."
        return

    try:
        if delete_brand_page(int(page_id)):
            state["success"] = "Deleted brand page."
        else:
            state["error"] = "Brand page not found."
    except Exception:
        logger.exception("brand page delete action failed")
        state["error"] = "An error occurred while deleting the page. Check logs/app.log for details."


def _export_brand_pages_csv():
    brand_name = request.form.get("brand_name", "").strip()
    brand_record = get_brand_record(brand_name)
    if not brand_record:
        return Response("Brand not found.\n", status=404, mimetype="text/plain")

    output = StringIO()
    fieldnames = ["page_title", "page_type", "primary_keyword", "supporting_keywords", "expectations"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for page in get_brand_pages(brand_record["id"]):
        writer.writerow({field: page.get(field, "") for field in fieldnames})

    filename_brand = "".join(char if char.isalnum() else "-" for char in brand_record.get("name", "brand").lower()).strip("-") or "brand"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename_brand}-pages.csv"},
    )


def _download_brand_pages_template_csv():
    output = StringIO()
    fieldnames = ["page_title", "page_type", "primary_keyword", "supporting_keywords", "expectations"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerow(
        {
            "page_title": "Example Service Page",
            "page_type": "Service",
            "primary_keyword": "example primary keyword",
            "supporting_keywords": "supporting keyword one, supporting keyword two",
            "expectations": "Short notes about what this page should cover.",
        }
    )

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=brand-pages-template.csv"},
    )


def _build_brand_view_models() -> list[dict]:
    brands = []
    for brand in list_brand_records():
        item = dict(brand)
        item["logo_url"] = image_url(item.get("logo_path", ""))
        item["brand_color"] = _normalize_color_input(item.get("brand_color", "")) or _fallback_brand_color(item.get("name", ""))
        item["pages"] = get_brand_pages(item.get("id"))
        brands.append(item)
    return brands


def _build_brand_color_filters(brands: list[dict]) -> list[dict]:
    palette_names = {item["value"]: item["name"] for item in _brand_color_palette()}
    filters = []
    seen = set()
    for brand in brands:
        color = _normalize_color_input(brand.get("brand_color", ""))
        if not color or color in seen:
            continue
        seen.add(color)
        filters.append({"name": palette_names.get(color, color), "value": color})
    return filters


def _normalize_color_input(color: str) -> str:
    cleaned = (color or "").strip().lower()
    if len(cleaned) == 7 and cleaned.startswith("#") and all(char in "0123456789abcdef" for char in cleaned[1:]):
        return cleaned
    return ""


def _fallback_brand_color(brand_name: str) -> str:
    palette = [item["value"] for item in _brand_color_palette()]
    seed = sum(ord(char) for char in (brand_name or "").lower())
    return palette[seed % len(palette)]


def _brand_color_palette() -> list[dict]:
    return [
        {"name": "Green", "value": "#15803d"},
        {"name": "Red", "value": "#be123c"},
        {"name": "Blue", "value": "#2563eb"},
        {"name": "Purple", "value": "#7c3aed"},
        {"name": "Teal", "value": "#0f766e"},
        {"name": "Orange", "value": "#c2410c"},
        {"name": "Moss", "value": "#486034"},
        {"name": "Sand", "value": "#b07042"},
    ]


def _apply_brand_preset(state: dict):
    preset = _brand_presets().get(state.get("brand_preset", ""))
    if not preset:
        return
    for key in ("niche", "tone", "notes", "main_keywords"):
        if not state.get(key, "").strip():
            state[key] = preset.get(key, "")


def _brand_presets() -> dict:
    return {
        "casino_safe": {
            "label": "Casino Safe",
            "niche": "online entertainment and responsible gaming",
            "tone": "calm, factual, compliant, adult-only",
            "main_keywords": "responsible gaming, safer play, online entertainment",
            "notes": "Avoid promotional gambling language. Emphasize age restrictions, user control, risk awareness, support resources, and safer play.",
        },
        "ecommerce": {
            "label": "Ecommerce",
            "niche": "online retail",
            "tone": "helpful, clear, product-focused",
            "main_keywords": "online shopping, product guide, customer support",
            "notes": "Focus on product benefits, buying confidence, practical comparisons, shipping, returns, and customer questions.",
        },
        "local_service": {
            "label": "Local Service",
            "niche": "local services",
            "tone": "friendly, trustworthy, practical",
            "main_keywords": "local service, service area, customer support",
            "notes": "Mention service areas, response time, trust signals, FAQs, and clear calls to action where natural.",
        },
        "saas": {
            "label": "SaaS",
            "niche": "software and workflow tools",
            "tone": "professional, useful, concise",
            "main_keywords": "software platform, workflow automation, business tools",
            "notes": "Focus on use cases, features, integrations, productivity, onboarding, and measurable business value.",
        },
        "affiliate": {
            "label": "Affiliate",
            "niche": "affiliate content and reviews",
            "tone": "balanced, editorial, helpful",
            "main_keywords": "review, comparison, buying guide",
            "notes": "Keep claims balanced. Include pros, cons, suitability, alternatives, and user-focused recommendations.",
        },
        "news": {
            "label": "News",
            "niche": "news and editorial publishing",
            "tone": "neutral, concise, informative",
            "main_keywords": "latest updates, industry news, analysis",
            "notes": "Use neutral wording, clear context, timely framing, and avoid unsupported claims.",
        },
    }
