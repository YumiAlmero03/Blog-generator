import json
from datetime import date

from flask import redirect, render_template, request, url_for

from app.controllers.helpers import base_template_context
from database import count_sent_posts_for_date, list_backlinks, list_brand_posts_for_planner_date, list_brand_records, list_posts_for_planner_date, list_sent_posts_export_for_date, update_backlink_notes, update_brand_notes


def posting_planner():
    if request.method == "POST":
        _handle_update_notes()
        return redirect(url_for("web.posting_planner", date=_selected_date()))

    planner_rows = []
    selected_date = _selected_date()
    sent_counts = count_sent_posts_for_date(selected_date)
    posts_by_medium = list_posts_for_planner_date(selected_date)
    posts_by_brand = list_brand_posts_for_planner_date(selected_date)
    export_rows = _export_rows(selected_date)

    for medium in list_backlinks():
        medium_name = medium.get("website_name", "")
        medium_key = _medium_key(medium)
        account = medium.get("blog_name", "") or medium.get("account_name", "")
        label_key = _medium_label_key(medium)
        medium_posts = posts_by_medium.get(medium_key, []) + posts_by_medium.get(label_key, [])
        if not account:
            medium_posts += posts_by_medium.get(_medium_name_key(medium), [])
        medium_posts = _unique_posts(medium_posts)
        planner_rows.append(
            {
                "source": "medium",
                "id": medium.get("id"),
                "name": medium_name,
                "account": account,
                "brand": "",
                "notes": medium.get("notes", ""),
                "type": (medium.get("website_type", "") or "blog").replace("_", " ").title(),
                "posts_per_day": medium.get("posts_per_day", 0) or 0,
                "post_sent": (
                    sent_counts.get(("Medium Blog", medium_key), 0)
                    + sent_counts.get(("Tier 2 Blog", medium_key), 0)
                    + sent_counts.get(("Neutral Post", medium_key), 0)
                    + sent_counts.get(("Medium Blog", label_key), 0)
                    + sent_counts.get(("Tier 2 Blog", label_key), 0)
                    + sent_counts.get(("Neutral Post", label_key), 0)
                    + (sent_counts.get(("Medium Blog", _medium_name_key(medium)), 0) if not account else 0)
                    + (sent_counts.get(("Tier 2 Blog", _medium_name_key(medium)), 0) if not account else 0)
                    + (sent_counts.get(("Neutral Post", _medium_name_key(medium)), 0) if not account else 0)
                ),
                "posts": medium_posts,
                "medium_blog_url": f"/medium-blog-generator?medium_id={medium.get('id')}" if medium.get("include_in_tier1", 1) else "",
                "tier2_blog_url": f"/tier-2-blog-generator?medium_id={medium.get('id')}",
                "neutral_url": f"/neutral-blog-generator?medium_id={medium.get('id')}",
                "edit_url": f"/mediums?edit={medium.get('id')}",
            }
        )

    for brand in list_brand_records():
        if not brand.get("include_in_posting_planner", 0):
            continue
        brand_name = brand.get("name", "")
        planner_rows.append(
            {
                "source": "brand",
                "id": brand.get("id"),
                "name": brand_name,
                "account": brand.get("website", ""),
                "brand": brand_name,
                "notes": brand.get("planner_notes", ""),
                "type": "Brand",
                "posts_per_day": 1,
                "post_sent": sum(
                    1
                    for post in posts_by_brand.get(brand_name, [])
                    if post.get("post_link") and str(post.get("saved_at", "")).startswith(selected_date)
                ),
                "posts": _unique_posts(posts_by_brand.get(brand_name, [])),
                "blog_url": f"/?brand={brand_name}",
                "medium_blog_url": "",
                "tier2_blog_url": "",
                "neutral_url": "",
                "edit_url": f"/brands?edit={brand_name}",
            }
        )

    planner_rows.sort(key=lambda item: (-int(item["posts_per_day"] or 0), item["name"].lower(), item["account"].lower(), item["source"]))

    return render_template(
        "posting_planner.html",
        **base_template_context(),
        rows=planner_rows,
        selected_date=selected_date,
        total_posts_per_day=sum(row["posts_per_day"] for row in planner_rows),
        total_posts_sent=sum(row["post_sent"] for row in planner_rows),
        export_rows=export_rows,
    )


def _handle_update_notes() -> None:
    source = request.form.get("source", "").strip()
    item_id = request.form.get("item_id", "").strip()
    notes = request.form.get("notes", "")
    if not item_id.isdigit():
        return
    if source == "medium":
        update_backlink_notes(int(item_id), notes)
    elif source == "brand":
        update_brand_notes(int(item_id), notes)


def _export_rows(selected_date: str) -> list[dict]:
    rows = list_sent_posts_export_for_date(selected_date)
    return [
        {
            "medium": _export_medium(row),
            "subject": _export_subject(row),
            "link": row.get("post_link", ""),
            "saved_at": row.get("saved_at", "") or row.get("created_at", ""),
        }
        for row in rows
    ]


def _selected_date() -> str:
    raw_date = request.args.get("date", "").strip()
    if not raw_date:
        return date.today().isoformat()
    try:
        return date.fromisoformat(raw_date).isoformat()
    except ValueError:
        return date.today().isoformat()


def _export_medium(row: dict) -> str:
    medium_name = (row.get("medium_name") or "").strip()
    prompt_inputs = _prompt_inputs(row)
    medium = prompt_inputs.get("medium") if isinstance(prompt_inputs.get("medium"), dict) else {}
    account = (
        medium.get("backlink_blog_name")
        or medium.get("blog_name")
        or medium.get("account_name")
        or ""
    ).strip()
    if medium_name and account and account.lower() not in medium_name.lower():
        return f"{medium_name} · {account}"
    if medium_name:
        return medium_name
    return (row.get("content_type") or "").strip()


def _export_subject(row: dict) -> str:
    content_type = (row.get("content_type") or "").strip().lower()
    if content_type == "tier 2 blog":
        prompt_inputs = _prompt_inputs(row)
        return (prompt_inputs.get("anchor_text") or row.get("primary_keyword") or "").strip()
    if content_type == "neutral post":
        return "neutral"
    if content_type == "blog":
        return (row.get("primary_keyword") or "").strip()
    return (row.get("brand_name") or row.get("primary_keyword") or "").strip()


def _prompt_inputs(row: dict) -> dict:
    try:
        parsed = json.loads(row.get("prompt_inputs") or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _unique_posts(posts: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for post in posts:
        post_id = post.get("id")
        key = post_id if post_id is not None else (
            post.get("content_type"),
            post.get("title"),
            post.get("saved_at") or post.get("created_at"),
            post.get("post_link"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(post)
    return unique


def _medium_key(medium: dict) -> str:
    medium_id = medium.get("id")
    if medium_id:
        return f"id:{medium_id}"
    return _medium_label_key(medium)


def _medium_label_key(medium: dict) -> str:
    name = (medium.get("website_name") or "").strip().lower()
    account = (medium.get("blog_name") or medium.get("account_name") or "").strip().lower()
    if name and account:
        return f"label:{name} · {account}"
    return _medium_name_key(medium)


def _medium_name_key(medium: dict) -> str:
    return f"name:{((medium.get('website_name') or '').strip().lower())}"
