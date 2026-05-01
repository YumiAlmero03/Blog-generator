from flask import render_template, request

from database import get_backlink, list_backlinks, save_backlink

from app.controllers.helpers import base_template_context


TIER_OPTIONS = ("Tier 1", "Tier 2", "Tier 3")
WEBSITE_TYPE_OPTIONS = (
    ("blog", "Blog"),
    ("google_sites", "Google Sites"),
    ("review", "Review Site"),
    ("forum", "Forum"),
    ("social_media", "Social Media"),
    ("twitter", "Twitter / X"),
    ("directory", "Directory"),
    ("news", "News Site"),
    ("community", "Community Site"),
    ("other", "Other"),
)


def backlinks():
    state = {
        "backlink_id": "",
        "website_name": "",
        "blog_name": "",
        "writer_name": "",
        "website_type": "blog",
        "title_max_characters": 0,
        "max_characters": 0,
        "blog_url": "",
        "tier_level": "Tier 1",
        "content_guidelines": "",
        "notes": "",
        "success": None,
        "error": None,
        "tier_options": TIER_OPTIONS,
        "website_type_options": WEBSITE_TYPE_OPTIONS,
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
    state["blog_name"] = backlink.get("blog_name", "") or backlink.get("account_name", "")
    state["writer_name"] = backlink.get("writer_name", "")
    state["website_type"] = backlink.get("website_type", "blog") or "blog"
    state["title_max_characters"] = backlink.get("title_max_characters", 0) or 0
    state["max_characters"] = backlink.get("max_characters", 0) or 0
    state["blog_url"] = backlink.get("blog_url", "")
    state["tier_level"] = backlink.get("tier_level", "Tier 1")
    state["content_guidelines"] = backlink.get("content_guidelines", "")
    state["notes"] = backlink.get("notes", "")


def _handle_save_backlink(state: dict):
    state["backlink_id"] = request.form.get("backlink_id", "").strip()
    state["website_name"] = request.form.get("website_name", "").strip()
    state["blog_name"] = request.form.get("blog_name", "").strip()
    state["writer_name"] = request.form.get("writer_name", "").strip()
    state["website_type"] = request.form.get("website_type", "blog").strip() or "blog"
    state["title_max_characters"] = request.form.get("title_max_characters", "0").strip()
    state["max_characters"] = request.form.get("max_characters", "0").strip()
    state["blog_url"] = request.form.get("blog_url", "").strip()
    state["tier_level"] = request.form.get("tier_level", "Tier 1").strip() or "Tier 1"
    state["content_guidelines"] = request.form.get("content_guidelines", "").strip()
    state["notes"] = request.form.get("notes", "").strip()

    if not state["website_name"]:
        state["error"] = "Please enter the medium name."
        return

    if state["tier_level"] not in TIER_OPTIONS:
        state["tier_level"] = "Tier 1"
    valid_website_types = {value for value, _label in WEBSITE_TYPE_OPTIONS}
    if state["website_type"] not in valid_website_types:
        state["website_type"] = "blog"
    try:
        state["title_max_characters"] = max(0, int(state["title_max_characters"] or 0))
    except ValueError:
        state["title_max_characters"] = 0
    try:
        state["max_characters"] = max(0, int(state["max_characters"] or 0))
    except ValueError:
        state["max_characters"] = 0

    backlink_id = int(state["backlink_id"]) if state["backlink_id"].isdigit() else None
    save_backlink(
        website_name=state["website_name"],
        blog_name=state["blog_name"],
        writer_name=state["writer_name"],
        website_type=state["website_type"],
        title_max_characters=state["title_max_characters"],
        max_characters=state["max_characters"],
        blog_url=state["blog_url"],
        tier_level=state["tier_level"],
        content_guidelines=state["content_guidelines"],
        notes=state["notes"],
        backlink_id=backlink_id,
    )

    state.update(
        {
            "backlink_id": "",
            "website_name": "",
            "blog_name": "",
            "writer_name": "",
            "website_type": "blog",
            "title_max_characters": 0,
            "max_characters": 0,
            "blog_url": "",
            "tier_level": "Tier 1",
            "content_guidelines": "",
            "notes": "",
            "success": "Medium saved.",
        }
    )
