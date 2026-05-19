import json
import csv
from io import StringIO

from flask import Response, redirect, render_template, request, url_for

from app.controllers.helpers import base_template_context
from database import list_backlinks, list_brand_records, upsert_brand
from database.common import get_connection, rows_to_dicts


def brand_medium_table():
    if request.method == "POST":
        action = request.form.get("action", "").strip()
        if action == "download_import_template":
            return _download_import_template_csv()
        if action == "download_saved_links":
            return _download_saved_links_csv()
        if action == "save_link":
            result = _save_link_form()
            return redirect(url_for("web.brand_medium_table", imported=result["imported"], skipped=result["skipped"]))
        if action == "import_posts":
            result = _import_posts_csv()
            return redirect(url_for("web.brand_medium_table", imported=result["imported"], skipped=result["skipped"]))

    mediums = _unique_mediums()
    brands = [brand for brand in list_brand_records() if brand.get("include_in_backlink_follow_up", 0)]
    posts = _medium_blog_posts()
    cells = _build_cells(brands, mediums, posts)
    return render_template(
        "brand_medium_table.html",
        **base_template_context(),
        mediums=mediums,
        brands=brands,
        cells=cells,
        imported_count=_int_arg("imported"),
        skipped_count=_int_arg("skipped"),
    )


def _import_posts_csv() -> dict:
    upload = request.files.get("posts_file")
    if not upload or not upload.filename:
        return {"imported": 0, "skipped": 0}

    text = upload.read().decode("utf-8-sig")
    reader = csv.DictReader(StringIO(text))
    imported = 0
    skipped = 0
    for row in reader:
        brand_name = _clean(row.get("brand"))
        medium_name = _clean(row.get("medium"))
        post_link = _normalize_post_link(row.get("post_link", ""))
        if not brand_name or not medium_name or not _valid_post_link(post_link) or _post_link_exists(post_link):
            skipped += 1
            continue

        brand = upsert_brand(brand_name, include_in_backlink_follow_up=True)
        if not brand:
            skipped += 1
            continue

        _insert_imported_post(
            brand_id=brand["id"],
            title=_clean(row.get("title")) or "Imported Medium Blog",
            keyword=_clean(row.get("keyword")),
            medium_name=medium_name,
            post_link=post_link,
            created_at=_clean(row.get("created_at")),
        )
        imported += 1

    return {"imported": imported, "skipped": skipped}


def _save_link_form() -> dict:
    brand_name = _clean(request.form.get("brand"))
    medium_name = _clean(request.form.get("medium"))
    post_link = _normalize_post_link(request.form.get("post_link", ""))
    if not brand_name or not medium_name or not _valid_post_link(post_link) or _post_link_exists(post_link):
        return {"imported": 0, "skipped": 1}

    brand = upsert_brand(brand_name, include_in_backlink_follow_up=True)
    if not brand:
        return {"imported": 0, "skipped": 1}

    _insert_imported_post(
        brand_id=brand["id"],
        title=_clean(request.form.get("title")) or "Imported Medium Blog",
        keyword=_clean(request.form.get("keyword")),
        medium_name=medium_name,
        post_link=post_link,
        created_at=_clean(request.form.get("created_at")),
    )
    return {"imported": 1, "skipped": 0}


def _insert_imported_post(
    brand_id: int,
    title: str,
    keyword: str,
    medium_name: str,
    post_link: str,
    created_at: str = "",
) -> None:
    prompt_inputs = json.dumps({"imported": True, "source": "brand_medium_table"}, ensure_ascii=True)
    date_sql = ", created_at, saved_at" if created_at else ", saved_at"
    date_placeholder = ", ?, ?" if created_at else ", datetime('now')"
    params = [
        "Medium Blog",
        brand_id,
        title,
        keyword,
        medium_name,
        post_link,
        prompt_inputs,
    ]
    if created_at:
        params.append(created_at)
        params.append(created_at)
    with get_connection() as connection:
        connection.execute(
            f"""
            INSERT INTO generation_history (
                content_type, brand_id, title, primary_keyword, medium_name,
                post_link, prompt_inputs, content, quality_report{date_sql}
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, '', ''{date_placeholder})
            """,
            params,
        )


def _download_import_template_csv():
    output = StringIO()
    fieldnames = ["brand", "medium", "title", "keyword", "post_link", "created_at"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerow(
        {
            "brand": "Example Brand",
            "medium": "Blogger",
            "title": "Imported post title",
            "keyword": "example keyword",
            "post_link": "https://example.com/imported-post",
            "created_at": "2026-05-14 09:00:00",
        }
    )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=brand-medium-post-import-template.csv"},
    )


def _download_saved_links_csv():
    output = StringIO()
    fieldnames = ["brand", "medium", "title", "keyword", "post_link", "created_at"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in _saved_link_rows():
        writer.writerow(row)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=brand-medium-saved-links.csv"},
    )


def _saved_link_rows() -> list[dict]:
    mediums = _unique_mediums()
    brands = [brand for brand in list_brand_records() if brand.get("include_in_backlink_follow_up", 0)]
    posts = _medium_blog_posts()
    brand_ids = {brand.get("id") for brand in brands}
    medium_keys = {medium["key"] for medium in mediums}
    rows = []
    for post in posts:
        if not post.get("post_link"):
            continue
        if post.get("brand_id") not in brand_ids or post.get("medium_key") not in medium_keys:
            continue
        rows.append(
            {
                "brand": post.get("brand_name", ""),
                "medium": post.get("medium_name", ""),
                "title": post.get("title", ""),
                "keyword": post.get("primary_keyword", ""),
                "post_link": post.get("post_link", ""),
                "created_at": post.get("created_at", ""),
            }
        )
    return rows


def _unique_mediums() -> list[dict]:
    seen = {}
    for medium in list_backlinks():
        if not medium.get("include_in_tier1", 1):
            continue
        name = (medium.get("website_name") or "").strip()
        if not name:
            continue
        key = name.lower()
        if key not in seen:
            seen[key] = {"key": key, "name": name, "count": 0, "ids": []}
        seen[key]["count"] += 1
        seen[key]["ids"].append(medium.get("id"))
    return sorted(seen.values(), key=lambda item: item["name"].lower())


def _post_link_exists(post_link: str) -> bool:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id FROM generation_history WHERE post_link = ? LIMIT 1",
            ((post_link or "").strip(),),
        ).fetchone()
    return bool(row)


def _medium_blog_posts() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                gh.id,
                gh.created_at,
                gh.saved_at,
                gh.title,
                gh.primary_keyword,
                gh.medium_name,
                gh.post_link,
                gh.prompt_inputs,
                gh.brand_id,
                b.name AS brand_name
            FROM generation_history gh
            JOIN brands b ON b.id = gh.brand_id
            WHERE gh.content_type = 'Medium Blog'
            ORDER BY datetime(COALESCE(NULLIF(gh.saved_at, ''), gh.created_at)) DESC, gh.id DESC
            """
        ).fetchall()
    posts = rows_to_dicts(rows)
    for post in posts:
        post["medium_key"] = _post_medium_key(post)
    return posts


def _build_cells(brands: list[dict], mediums: list[dict], posts: list[dict]) -> dict[tuple[int, str], list[dict]]:
    cells: dict[tuple[int, str], list[dict]] = {}
    brand_ids = {brand.get("id") for brand in brands}
    medium_keys = {medium["key"] for medium in mediums}
    for post in posts:
        brand_id = post.get("brand_id")
        medium_key = post.get("medium_key")
        if brand_id in brand_ids and medium_key in medium_keys:
            cells.setdefault((brand_id, medium_key), []).append(post)
    return cells


def _post_medium_key(post: dict) -> str:
    prompt_inputs = _loads(post.get("prompt_inputs", "{}"))
    medium = prompt_inputs.get("medium") if isinstance(prompt_inputs.get("medium"), dict) else {}
    medium_name = (
        medium.get("backlink_website_name")
        or medium.get("website_name")
        or post.get("medium_name")
        or ""
    ).strip()
    if " · " in medium_name:
        medium_name = medium_name.split(" · ", 1)[0].strip()
    return medium_name.lower()


def _loads(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _clean(value) -> str:
    return str(value or "").strip()


def _valid_post_link(value: str) -> bool:
    cleaned = (value or "").strip().lower()
    return cleaned.startswith("https://") or cleaned.startswith("http://")


def _normalize_post_link(value: str) -> str:
    cleaned = (value or "").strip()
    lowered = cleaned.lower()
    if lowered.startswith(("http://", "https://")):
        return cleaned
    if "." in cleaned and " " not in cleaned:
        return f"https://{cleaned}"
    return cleaned


def _int_arg(name: str) -> int:
    try:
        return max(0, int(request.args.get(name, "0")))
    except ValueError:
        return 0
