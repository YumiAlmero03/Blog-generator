from flask import render_template, request

from database import check_keyword_usage, get_brand_record, list_brand_records, upsert_brand
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
        "logo_path": "",
        "brand_color": "#b07042",
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
        elif action == "check_keyword":
            _handle_check_keyword(state)

    return render_template(
        "brands.html",
        **base_template_context(),
        **state,
        logo_url=image_url(state["logo_path"]),
        brands=_build_brand_view_models(),
        brand_color_palette=brand_color_palette,
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
    state["logo_path"] = brand_record.get("logo_path", "")
    state["brand_color"] = brand_record.get("brand_color", "") or _fallback_brand_color(state["brand_name"])


def _handle_save_brand(state: dict):
    state["brand_name"] = request.form.get("brand_name", "").strip()
    state["website"] = request.form.get("website", "").strip()
    state["niche"] = request.form.get("niche", "").strip()
    state["main_keywords"] = request.form.get("main_keywords", "").strip()
    state["tone"] = request.form.get("tone", "").strip()
    state["notes"] = request.form.get("notes", "").strip()
    state["brand_color"] = _normalize_color_input(request.form.get("brand_color", ""))
    logo_upload = request.files.get("logo_file")

    if not state["brand_name"]:
        state["error"] = "Please enter a brand name."
        return

    try:
        if logo_upload and logo_upload.filename:
            state["logo_path"] = f"brand_logos/{save_uploaded_image(logo_upload, BRAND_LOGO_DIR, 'logo')}"

        upsert_brand(
            state["brand_name"],
            website=state["website"],
            tone=state["tone"],
            notes=state["notes"],
            niche=state["niche"],
            main_keywords=state["main_keywords"],
            logo_path=state["logo_path"],
            brand_color=state["brand_color"],
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
                "logo_path": "",
                "brand_color": "#b07042",
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


def _build_brand_view_models() -> list[dict]:
    brands = []
    for brand in list_brand_records():
        item = dict(brand)
        item["logo_url"] = image_url(item.get("logo_path", ""))
        item["brand_color"] = _normalize_color_input(item.get("brand_color", "")) or _fallback_brand_color(item.get("name", ""))
        brands.append(item)
    return brands


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
