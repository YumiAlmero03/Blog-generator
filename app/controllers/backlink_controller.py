from flask import render_template, request

from database import delete_backlink, get_backlink, list_backlinks, save_backlink
from logger import logger

from app.controllers.helpers import base_template_context


POST_TYPE_OPTIONS = (
    ("html", "HTML"),
    ("markdown", "Markdown"),
    ("gutenberg", "Gutenberg"),
    ("text", "Text"),
)
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
        "post_type": "html",
        "title_max_characters": 0,
        "min_words": 0,
        "max_characters": 0,
        "blog_url": "",
        "posts_per_day": 0,
        "include_in_tier1": True,
        "brand_topic_mode": "example",
        "content_guidelines": "",
        "notes": "",
        "success": None,
        "error": None,
        "post_type_options": POST_TYPE_OPTIONS,
        "website_type_options": WEBSITE_TYPE_OPTIONS,
        "medium_presets": _medium_presets(),
    }

    edit_id = request.args.get("edit", "").strip()
    if request.method == "GET" and edit_id.isdigit():
        _populate_for_edit(state, int(edit_id))

    if request.method == "POST":
        action = request.form.get("action", "save_backlink").strip()
        if action == "delete_backlink":
            _handle_delete_backlink(state)
        else:
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
    state["post_type"] = backlink.get("post_type", "html") or "html"
    state["title_max_characters"] = backlink.get("title_max_characters", 0) or 0
    state["min_words"] = backlink.get("min_words", 0) or 0
    state["max_characters"] = backlink.get("max_characters", 0) or 0
    state["blog_url"] = backlink.get("blog_url", "")
    state["posts_per_day"] = backlink.get("posts_per_day", 0) or 0
    state["include_in_tier1"] = bool(backlink.get("include_in_tier1", 1))
    state["brand_topic_mode"] = backlink.get("brand_topic_mode", "example") or "example"
    state["content_guidelines"] = backlink.get("content_guidelines", "")
    state["notes"] = backlink.get("notes", "")


def _handle_save_backlink(state: dict):
    state["backlink_id"] = request.form.get("backlink_id", "").strip()
    state["website_name"] = request.form.get("website_name", "").strip()
    state["blog_name"] = request.form.get("blog_name", "").strip()
    state["writer_name"] = request.form.get("writer_name", "").strip()
    state["website_type"] = request.form.get("website_type", "blog").strip() or "blog"
    state["post_type"] = request.form.get("post_type", "html").strip().lower() or "html"
    state["title_max_characters"] = request.form.get("title_max_characters", "0").strip()
    state["min_words"] = request.form.get("min_words", "0").strip()
    state["max_characters"] = request.form.get("max_characters", "0").strip()
    state["blog_url"] = request.form.get("blog_url", "").strip()
    state["posts_per_day"] = request.form.get("posts_per_day", "0").strip()
    state["include_in_tier1"] = request.form.get("include_in_tier1") == "1"
    state["brand_topic_mode"] = request.form.get("brand_topic_mode", "example").strip() or "example"
    state["content_guidelines"] = request.form.get("content_guidelines", "").strip()
    state["notes"] = request.form.get("notes", "").strip()
    medium_preset = request.form.get("medium_preset", "").strip()
    _apply_medium_preset(state, medium_preset)

    if not state["website_name"]:
        state["error"] = "Please enter the medium name."
        return

    valid_website_types = {value for value, _label in WEBSITE_TYPE_OPTIONS}
    if state["website_type"] not in valid_website_types:
        state["website_type"] = "blog"
    valid_post_types = {value for value, _label in POST_TYPE_OPTIONS}
    if state["post_type"] not in valid_post_types:
        state["post_type"] = "html"
    try:
        state["title_max_characters"] = max(0, int(state["title_max_characters"] or 0))
    except ValueError:
        state["title_max_characters"] = 0
    try:
        state["min_words"] = max(0, int(state["min_words"] or 0))
    except ValueError:
        state["min_words"] = 0
    try:
        state["max_characters"] = max(0, int(state["max_characters"] or 0))
    except ValueError:
        state["max_characters"] = 0
    try:
        state["posts_per_day"] = max(0, int(state["posts_per_day"] or 0))
    except ValueError:
        state["posts_per_day"] = 0

    backlink_id = int(state["backlink_id"]) if state["backlink_id"].isdigit() else None
    save_backlink(
        website_name=state["website_name"],
        blog_name=state["blog_name"],
        writer_name=state["writer_name"],
        website_type=state["website_type"],
        post_type=state["post_type"],
        title_max_characters=state["title_max_characters"],
        min_words=state["min_words"],
        max_characters=state["max_characters"],
        blog_url=state["blog_url"],
        tier_level="Tier 1",
        posts_per_day=state["posts_per_day"],
        content_guidelines=state["content_guidelines"],
        notes=state["notes"],
        include_in_tier1=state["include_in_tier1"],
        brand_topic_mode=state["brand_topic_mode"],
        backlink_id=backlink_id,
    )

    state.update(
        {
            "backlink_id": "",
            "website_name": "",
            "blog_name": "",
            "writer_name": "",
            "website_type": "blog",
            "post_type": "html",
            "title_max_characters": 0,
            "min_words": 0,
            "max_characters": 0,
            "blog_url": "",
            "posts_per_day": 0,
            "include_in_tier1": True,
            "brand_topic_mode": "example",
            "content_guidelines": "",
            "notes": "",
            "success": "Medium saved.",
        }
    )


def _handle_delete_backlink(state: dict):
    backlink_id = request.form.get("backlink_id", "").strip()
    if not backlink_id.isdigit():
        state["error"] = "Please select a medium to delete."
        return

    try:
        if delete_backlink(int(backlink_id)):
            state["success"] = "Medium deleted."
        else:
            state["error"] = "Medium not found."
    except Exception:
        logger.exception("mediums delete_backlink action failed")
        state["error"] = "An error occurred while deleting the medium. Check logs/app.log for details."


def _apply_medium_preset(state: dict, preset_key: str):
    preset = _medium_presets().get(preset_key)
    if not preset:
        return
    for key in ("website_type", "post_type", "title_max_characters", "min_words", "max_characters", "content_guidelines", "brand_topic_mode"):
        current = str(state.get(key, "")).strip()
        if current and current not in {"0", "blog", "html", "example"}:
            continue
        state[key] = preset.get(key, state.get(key, ""))


def _medium_presets() -> dict:
    return {
        "twitter": {
            "label": "Twitter / X",
            "website_type": "twitter",
            "post_type": "text",
            "title_max_characters": 70,
            "min_words": 15,
            "max_characters": 40,
            "content_guidelines": "Short social post. Keep the title compact, use plain text, insert the brand URL once anywhere in the article, and avoid long article sections.",
        },
        "facebook": {
            "label": "Facebook",
            "website_type": "social_media",
            "post_type": "text",
            "title_max_characters": 80,
            "min_words": 40,
            "max_characters": 180,
            "content_guidelines": "Write a friendly, skimmable Facebook-style post with a clear hook, short paragraphs, and natural tags when useful.",
        },
        "youtube": {
            "label": "YouTube",
            "website_type": "social_media",
            "post_type": "text",
            "title_max_characters": 70,
            "min_words": 60,
            "max_characters": 220,
            "content_guidelines": "Write a YouTube community or description-style post with a clear title angle, concise body, and viewer-friendly wording.",
        },
        "instagram": {
            "label": "Instagram",
            "website_type": "social_media",
            "post_type": "text",
            "title_max_characters": 70,
            "min_words": 25,
            "max_characters": 120,
            "content_guidelines": "Write a visual, caption-style Instagram post with concise copy, sensory detail, and a few clean hashtags.",
        },
        "google_sites": {
            "label": "Google Sites",
            "website_type": "google_sites",
            "post_type": "html",
            "title_max_characters": 58,
            "min_words": 350,
            "max_characters": 700,
            "content_guidelines": "Use a compact title, clear H2 sections, short paragraphs, and simple HTML that pastes cleanly into Google Sites.",
        },
        "wordpress": {
            "label": "WordPress Gutenberg",
            "website_type": "blog",
            "post_type": "gutenberg",
            "title_max_characters": 60,
            "min_words": 800,
            "max_characters": 1200,
            "content_guidelines": "Use Gutenberg block HTML, editorial sections, compact paragraphs, and one natural brand URL placement.",
            "brand_topic_mode": "example",
        },
        "github": {
            "label": "GitHub",
            "website_type": "community",
            "post_type": "markdown",
            "title_max_characters": 70,
            "min_words": 500,
            "max_characters": 900,
            "content_guidelines": "Write a README or discussion-style Markdown post where the brand can be the main project/topic. Keep it useful and technical, not promotional.",
            "brand_topic_mode": "main",
        },
        "gitbook": {
            "label": "GitBook",
            "website_type": "blog",
            "post_type": "markdown",
            "title_max_characters": 70,
            "min_words": 600,
            "max_characters": 1000,
            "content_guidelines": "Write a documentation-style Markdown article where the brand can be the main topic. Use clear sections and practical context.",
            "brand_topic_mode": "main",
        },
        "forum": {
            "label": "Forum",
            "website_type": "forum",
            "post_type": "text",
            "title_max_characters": 80,
            "min_words": 120,
            "max_characters": 280,
            "content_guidelines": "Make it discussion-oriented, practical, and concise. Avoid sounding like a formal article or ad.",
        },
        "review": {
            "label": "Review Site",
            "website_type": "review",
            "post_type": "html",
            "title_max_characters": 62,
            "min_words": 700,
            "max_characters": 1100,
            "content_guidelines": "Use a balanced editorial review angle with pros, fit, limitations, and practical user context.",
        },
        "pinterest": {
            "label": "Pinterest",
            "website_type": "social_media",
            "post_type": "text",
            "title_max_characters": 70,
            "min_words": 40,
            "max_characters": 90,
            "content_guidelines": "Write a short pin-style description with visual language, simple tags, and insert the brand URL once anywhere in the article.",
        },
    }
