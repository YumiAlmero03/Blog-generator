from flask import render_template, request

from app.controllers.helpers import base_template_context, image_url
from database import (
    checklist_items_by_type,
    delete_checklist_item,
    list_brand_records,
    list_checklist_items,
    list_checklist_states,
    list_backlinks,
    reorder_checklist_items,
    save_checklist_item,
    save_checklist_subject_state,
)
from logger import logger


CHECKLIST_TYPE_LABELS = {
    "website": "Whole Website",
    "blog": "Blog Content",
    "page": "Page Content",
}


def checklist_manager():
    state = {"error": None, "success": None}
    if request.method == "POST":
        action = request.form.get("action", "save_item").strip()
        try:
            if action == "delete_item":
                item_id = request.form.get("item_id", "").strip()
                if not item_id.isdigit() or not delete_checklist_item(int(item_id)):
                    state["error"] = "Checklist item not found."
                else:
                    state["success"] = "Checklist item deleted."
            elif action == "reorder_items":
                reorder_checklist_items(
                    request.form.get("checklist_type", "website"),
                    request.form.getlist("item_ids"),
                )
                state["success"] = "Checklist order saved."
            else:
                item_id = request.form.get("item_id", "").strip()
                save_checklist_item(
                    label=request.form.get("label", ""),
                    checklist_type=request.form.get("checklist_type", "website"),
                    sort_order=request.form.get("sort_order", "0"),
                    is_active=request.form.get("is_active") == "1",
                    item_id=int(item_id) if item_id.isdigit() else None,
                )
                state["success"] = "Checklist item saved."
        except ValueError as exc:
            state["error"] = str(exc)
        except Exception:
            logger.exception("checklist manager action failed")
            state["error"] = "An error occurred while saving the checklist."

    return render_template(
        "checklists.html",
        **base_template_context(),
        **state,
        checklist_groups=checklist_items_by_type(),
        type_labels=CHECKLIST_TYPE_LABELS,
    )


def website_checklist_dashboard():
    state = {"error": None, "success": None}
    if request.method == "POST":
        try:
            save_checklist_subject_state(
                "website",
                request.form.get("subject_type", "brand"),
                request.form.get("subject_id", ""),
                request.form.getlist("checked_item_ids"),
            )
            state["success"] = "Website checklist saved."
        except ValueError as exc:
            state["error"] = str(exc)
        except Exception:
            logger.exception("website checklist save failed")
            state["error"] = "An error occurred while saving the website checklist."

    website_items = list_checklist_items("website", active_only=True)
    checked_states = list_checklist_states("website")
    checked_by_subject = {}
    for item_state in checked_states:
        key = (item_state.get("subject_type", ""), str(item_state.get("subject_id", "")))
        checked_by_subject.setdefault(key, set()).add(int(item_state.get("checklist_item_id", 0) or 0))

    brands = []
    for brand in list_brand_records():
        if not brand.get("include_in_website_checklist"):
            continue
        item = dict(brand)
        item["subject_type"] = "brand"
        item["subject_id"] = str(item.get("id", ""))
        item["checked_item_ids"] = checked_by_subject.get(("brand", item["subject_id"]), set())
        item["display_type"] = "Brand"
        item["title"] = item.get("name", "")
        item["subtitle"] = item.get("website") or item.get("niche") or "Brand"
        item["logo_url"] = image_url(item.get("logo_path", ""))
        brands.append(item)

    mediums = []
    for medium in list_backlinks():
        if not medium.get("include_in_website_checklist"):
            continue
        item = dict(medium)
        item["subject_type"] = "medium"
        item["subject_id"] = str(item.get("id", ""))
        item["checked_item_ids"] = checked_by_subject.get(("medium", item["subject_id"]), set())
        item["display_type"] = "Medium"
        item["title"] = _medium_title(item)
        item["subtitle"] = item.get("blog_url") or item.get("website_type", "medium").replace("_", " ").title()
        item["logo_url"] = ""
        mediums.append(item)

    return render_template(
        "website_checklist_dashboard.html",
        **base_template_context(),
        **state,
        checklist_items=website_items,
        websites=brands + mediums,
    )


def _medium_title(medium: dict) -> str:
    name = (medium.get("website_name") or "").strip()
    account = (medium.get("blog_name") or medium.get("account_name") or "").strip()
    if name and account:
        return f"{name} - {account}"
    return name or "Untitled Medium"
