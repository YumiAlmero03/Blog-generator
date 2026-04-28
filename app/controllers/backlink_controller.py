from flask import render_template, request

from database import get_backlink, list_backlinks, save_backlink

from app.controllers.helpers import base_template_context


TIER_OPTIONS = ("Tier 1", "Tier 2", "Tier 3")


def backlinks():
    state = {
        "backlink_id": "",
        "website_name": "",
        "account_name": "",
        "blog_url": "",
        "tier_level": "Tier 1",
        "notes": "",
        "success": None,
        "error": None,
        "tier_options": TIER_OPTIONS,
    }

    edit_id = request.args.get("edit", "").strip()
    if request.method == "GET" and edit_id.isdigit():
        _populate_for_edit(state, int(edit_id))

    if request.method == "POST":
        _handle_save_backlink(state)

    return render_template(
        "backlinks.html",
        **base_template_context(),
        **state,
        backlinks=list_backlinks(),
    )


def _populate_for_edit(state: dict, backlink_id: int):
    backlink = get_backlink(backlink_id)
    if not backlink:
        return

    state["backlink_id"] = str(backlink.get("id", ""))
    state["website_name"] = backlink.get("website_name", "")
    state["account_name"] = backlink.get("account_name", "")
    state["blog_url"] = backlink.get("blog_url", "")
    state["tier_level"] = backlink.get("tier_level", "Tier 1")
    state["notes"] = backlink.get("notes", "")


def _handle_save_backlink(state: dict):
    state["backlink_id"] = request.form.get("backlink_id", "").strip()
    state["website_name"] = request.form.get("website_name", "").strip()
    state["account_name"] = request.form.get("account_name", "").strip()
    state["blog_url"] = request.form.get("blog_url", "").strip()
    state["tier_level"] = request.form.get("tier_level", "Tier 1").strip() or "Tier 1"
    state["notes"] = request.form.get("notes", "").strip()

    if not state["website_name"]:
        state["error"] = "Please enter the website or blog name."
        return

    if not state["blog_url"]:
        state["error"] = "Please enter the blog URL."
        return

    if state["tier_level"] not in TIER_OPTIONS:
        state["tier_level"] = "Tier 1"

    backlink_id = int(state["backlink_id"]) if state["backlink_id"].isdigit() else None
    save_backlink(
        website_name=state["website_name"],
        account_name=state["account_name"],
        blog_url=state["blog_url"],
        tier_level=state["tier_level"],
        notes=state["notes"],
        backlink_id=backlink_id,
    )

    state.update(
        {
            "backlink_id": "",
            "website_name": "",
            "account_name": "",
            "blog_url": "",
            "tier_level": "Tier 1",
            "notes": "",
            "success": "Backlink site saved.",
        }
    )
