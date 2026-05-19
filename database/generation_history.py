import json

from database.brands import upsert_brand
from database.common import get_connection, row_to_dict, rows_to_dicts


def record_generation(
    content_type: str,
    brand_name: str = "",
    title: str = "",
    primary_keyword: str = "",
    medium_name: str = "",
    word_count: int = 0,
    meta_description: str = "",
    post_link: str = "",
    tags: list[str] | str | None = None,
    prompt_inputs: dict | None = None,
    content: str = "",
    quality_report: dict | None = None,
    history_id: int | str | None = None,
) -> int:
    tags_text = ", ".join(tags) if isinstance(tags, list) else (tags or "")
    content_type_text = (content_type or "").strip()
    title_text = (title or "").strip()
    primary_keyword_text = (primary_keyword or "").strip()
    medium_name_text = (medium_name or "").strip()
    meta_description_text = (meta_description or "").strip()
    post_link_text = (post_link or "").strip()
    prompt_inputs_text = json.dumps(prompt_inputs or {}, ensure_ascii=True)
    quality_report_text = json.dumps(quality_report or {}, ensure_ascii=True)
    brand_id = None
    if (brand_name or "").strip():
        brand_record = upsert_brand(brand_name)
        if brand_record:
            brand_id = brand_record["id"]

    with get_connection() as connection:
        target_history_id = _coerce_history_id(history_id)
        if target_history_id and _generation_exists(connection, target_history_id):
            _update_generation_history(
                connection,
                history_id=target_history_id,
                content_type=content_type_text,
                brand_id=brand_id,
                title=title_text,
                primary_keyword=primary_keyword_text,
                medium_name=medium_name_text,
                word_count=word_count,
                meta_description=meta_description_text,
                post_link=post_link_text,
                tags=tags_text.strip(),
                prompt_inputs=prompt_inputs_text,
                content=content or "",
                quality_report=quality_report_text,
            )
            return target_history_id

        existing_id = _find_existing_generation_id(
            connection,
            content_type=content_type_text,
            brand_id=brand_id,
            title=title_text,
            primary_keyword=primary_keyword_text,
            medium_name=medium_name_text,
        )
        if existing_id:
            _update_generation_history(
                connection,
                history_id=existing_id,
                content_type=content_type_text,
                brand_id=brand_id,
                title=title_text,
                primary_keyword=primary_keyword_text,
                medium_name=medium_name_text,
                word_count=word_count,
                meta_description=meta_description_text,
                post_link=post_link_text,
                tags=tags_text.strip(),
                prompt_inputs=prompt_inputs_text,
                content=content or "",
                quality_report=quality_report_text,
            )
            return int(existing_id)

        cursor = connection.execute(
            """
            INSERT INTO generation_history (
                content_type, brand_id, title, primary_keyword, medium_name, word_count,
                meta_description, post_link, saved_at, tags, prompt_inputs, content, quality_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CASE WHEN TRIM(?) <> '' THEN datetime('now') ELSE '' END, ?, ?, ?, ?)
            """,
            (
                content_type_text,
                brand_id,
                title_text,
                primary_keyword_text,
                medium_name_text,
                int(word_count or 0),
                meta_description_text,
                post_link_text,
                post_link_text,
                tags_text.strip(),
                prompt_inputs_text,
                content or "",
                quality_report_text,
            ),
        )
        return int(cursor.lastrowid)


def _coerce_history_id(value: int | str | None) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _generation_exists(connection, history_id: int) -> bool:
    row = connection.execute("SELECT id FROM generation_history WHERE id = ?", (history_id,)).fetchone()
    return bool(row)


def _update_generation_history(
    connection,
    history_id: int,
    content_type: str,
    brand_id: int | None,
    title: str,
    primary_keyword: str,
    medium_name: str,
    word_count: int,
    meta_description: str,
    post_link: str,
    tags: str,
    prompt_inputs: str,
    content: str,
    quality_report: str,
) -> None:
    connection.execute(
        """
        UPDATE generation_history
        SET content_type = ?,
            brand_id = ?,
            title = ?,
            primary_keyword = ?,
            medium_name = ?,
            word_count = ?,
            meta_description = ?,
            post_link = ?,
            saved_at = CASE
                WHEN TRIM(?) <> '' AND TRIM(COALESCE(saved_at, '')) = '' THEN datetime('now')
                WHEN TRIM(?) = '' THEN ''
                ELSE saved_at
            END,
            tags = ?,
            prompt_inputs = ?,
            content = ?,
            quality_report = ?
        WHERE id = ?
        """,
        (
            content_type,
            brand_id,
            title,
            primary_keyword,
            medium_name,
            int(word_count or 0),
            meta_description,
            post_link,
            post_link,
            post_link,
            tags,
            prompt_inputs,
            content,
            quality_report,
            history_id,
        ),
    )


def _find_existing_generation_id(
    connection,
    content_type: str,
    brand_id: int | None,
    title: str,
    primary_keyword: str,
    medium_name: str,
) -> int | None:
    if not content_type or not title:
        return None

    brand_condition = "brand_id IS NULL" if brand_id is None else "brand_id = ?"
    params: list = [content_type]
    if brand_id is not None:
        params.append(brand_id)
    params.extend([title, primary_keyword, medium_name])

    row = connection.execute(
        f"""
        SELECT id
        FROM generation_history
        WHERE content_type = ?
          AND {brand_condition}
          AND title = ?
          AND primary_keyword = ?
          AND medium_name = ?
          AND TRIM(COALESCE(post_link, '')) = ''
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT 1
        """,
        params,
    ).fetchone()
    return int(row["id"]) if row else None


def list_generation_history(
    limit: int = 100,
    content_type: str = "",
    status: str = "",
    selected_date: str = "",
    medium_name: str = "",
    search: str = "",
) -> list[dict]:
    where_clauses = []
    params: list[str] = []

    cleaned_content_type = (content_type or "").strip()
    if cleaned_content_type:
        where_clauses.append("gh.content_type = ?")
        params.append(cleaned_content_type)

    cleaned_status = (status or "").strip().lower()
    if cleaned_status == "saved":
        where_clauses.append("TRIM(COALESCE(gh.post_link, '')) <> ''")
    elif cleaned_status == "draft":
        where_clauses.append("TRIM(COALESCE(gh.post_link, '')) = ''")

    cleaned_date = (selected_date or "").strip()
    if cleaned_date:
        if cleaned_status == "draft":
            where_clauses.append("date(gh.created_at) = ?")
            params.append(cleaned_date)
        elif cleaned_status == "saved":
            where_clauses.append("date(gh.saved_at) = ?")
            params.append(cleaned_date)
        else:
            where_clauses.append(
                """
                (
                    (TRIM(COALESCE(gh.post_link, '')) <> '' AND date(gh.saved_at) = ?)
                    OR (TRIM(COALESCE(gh.post_link, '')) = '' AND date(gh.created_at) = ?)
                )
                """
            )
            params.extend([cleaned_date, cleaned_date])

    cleaned_medium = (medium_name or "").strip()
    if cleaned_medium:
        where_clauses.append("gh.medium_name = ?")
        params.append(cleaned_medium)

    cleaned_search = (search or "").strip()
    if cleaned_search:
        where_clauses.append(
            """
            (
                gh.title LIKE ?
                OR gh.primary_keyword LIKE ?
                OR gh.medium_name LIKE ?
                OR gh.content_type LIKE ?
                OR gh.post_link LIKE ?
                OR gh.tags LIKE ?
                OR b.name LIKE ?
            )
            """
        )
        search_param = f"%{cleaned_search}%"
        params.extend([search_param] * 7)

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT
                gh.id,
                gh.created_at,
                gh.content_type,
                gh.brand_id,
                gh.title,
                gh.primary_keyword,
                gh.medium_name,
                gh.word_count,
                gh.meta_description,
                gh.post_link,
                gh.saved_at,
                gh.tags,
                gh.prompt_inputs,
                gh.content,
                gh.quality_report,
                b.name AS brand_name
            FROM generation_history gh
            LEFT JOIN brands b ON b.id = gh.brand_id
            {where_sql}
            ORDER BY datetime(COALESCE(NULLIF(gh.saved_at, ''), gh.created_at)) DESC, gh.id DESC
            LIMIT ?
            """,
            (*params, max(1, int(limit or 100))),
        ).fetchall()
        return rows_to_dicts(rows)


def list_generation_history_medium_names() -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT medium_name
            FROM generation_history
            WHERE TRIM(COALESCE(medium_name, '')) <> ''
            ORDER BY LOWER(medium_name)
            """
        ).fetchall()
        return [row["medium_name"] for row in rows]


def delete_generation_history_item(history_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM generation_history WHERE id = ?", (history_id,))
        return cursor.rowcount > 0


def update_generation_history_post_link(history_id: int, post_link: str) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE generation_history
            SET post_link = ?,
                saved_at = CASE
                    WHEN TRIM(?) <> '' THEN datetime('now')
                    ELSE ''
                END
            WHERE id = ?
            """,
            ((post_link or "").strip(), (post_link or "").strip(), history_id),
        )
        return cursor.rowcount > 0


def mark_generation_history_draft(history_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE generation_history SET post_link = '', saved_at = '' WHERE id = ?",
            (history_id,),
        )
        return cursor.rowcount > 0


def get_generation_history_item(history_id: int) -> dict | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                gh.id,
                gh.created_at,
                gh.content_type,
                gh.brand_id,
                gh.title,
                gh.primary_keyword,
                gh.medium_name,
                gh.word_count,
                gh.meta_description,
                gh.post_link,
                gh.saved_at,
                gh.tags,
                gh.prompt_inputs,
                gh.content,
                gh.quality_report,
                b.name AS brand_name
            FROM generation_history gh
            LEFT JOIN brands b ON b.id = gh.brand_id
            WHERE gh.id = ?
            """,
            (history_id,),
        ).fetchone()
        return row_to_dict(row)


def generation_dashboard_stats() -> dict:
    with get_connection() as connection:
        totals = connection.execute(
            """
            SELECT
              COUNT(*) AS total_count,
              COALESCE(SUM(word_count), 0) AS total_words,
              COUNT(DISTINCT brand_id) AS brand_count
            FROM generation_history
            """
        ).fetchone()
        by_type = connection.execute(
            """
            SELECT content_type, COUNT(*) AS count, COALESCE(SUM(word_count), 0) AS words
            FROM generation_history
            GROUP BY content_type
            ORDER BY count DESC, content_type
            """
        ).fetchall()
        recent = connection.execute(
            """
            SELECT *
            FROM generation_history
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT 8
            """
        ).fetchall()
    return {
        "total_count": int(totals["total_count"] or 0),
        "total_words": int(totals["total_words"] or 0),
        "brand_count": int(totals["brand_count"] or 0),
        "by_type": rows_to_dicts(by_type),
        "recent": rows_to_dicts(recent),
    }


def count_sent_posts_for_date(selected_date: str) -> dict[tuple[str, str], int]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT content_type, medium_name, prompt_inputs
            FROM generation_history
            WHERE TRIM(COALESCE(post_link, '')) <> ''
              AND date(saved_at) = ?
            """,
            ((selected_date or "").strip(),),
        ).fetchall()

    counts: dict[tuple[str, str], int] = {}
    for row in rows_to_dicts(rows):
        key = ((row.get("content_type") or "").strip(), planner_medium_key(row))
        counts[key] = counts.get(key, 0) + 1
    return counts


def list_sent_posts_for_date(selected_date: str) -> dict[str, list[dict]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                gh.id,
                gh.created_at,
                gh.saved_at,
                gh.content_type,
                gh.title,
                gh.medium_name,
                gh.post_link,
                gh.prompt_inputs,
                b.name AS brand_name
            FROM generation_history gh
            LEFT JOIN brands b ON b.id = gh.brand_id
            WHERE TRIM(COALESCE(gh.post_link, '')) <> ''
              AND date(gh.saved_at) = ?
            ORDER BY datetime(gh.saved_at) DESC, gh.id DESC
            """,
            ((selected_date or "").strip(),),
        ).fetchall()

    grouped: dict[str, list[dict]] = {}
    for row in rows_to_dicts(rows):
        grouped.setdefault(planner_medium_key(row), []).append(row)
    return grouped


def list_sent_posts_export_for_date(selected_date: str) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                gh.id,
                gh.created_at,
                gh.saved_at,
                gh.content_type,
                gh.title,
                gh.primary_keyword,
                gh.medium_name,
                gh.post_link,
                gh.prompt_inputs,
                b.name AS brand_name
            FROM generation_history gh
            LEFT JOIN brands b ON b.id = gh.brand_id
            WHERE TRIM(COALESCE(gh.post_link, '')) <> ''
              AND date(gh.saved_at) = ?
            ORDER BY datetime(gh.saved_at) DESC, gh.id DESC
            """,
            ((selected_date or "").strip(),),
        ).fetchall()
        return rows_to_dicts(rows)


def list_posts_for_planner_date(selected_date: str) -> dict[str, list[dict]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                gh.id,
                gh.created_at,
                gh.saved_at,
                gh.content_type,
                gh.title,
                gh.medium_name,
                gh.post_link,
                gh.prompt_inputs,
                b.name AS brand_name
            FROM generation_history gh
            LEFT JOIN brands b ON b.id = gh.brand_id
            WHERE (TRIM(COALESCE(gh.post_link, '')) <> '' AND date(gh.saved_at) = ?)
               OR TRIM(COALESCE(gh.post_link, '')) = ''
            ORDER BY datetime(COALESCE(NULLIF(gh.saved_at, ''), gh.created_at)) DESC, gh.id DESC
            """,
            ((selected_date or "").strip(),),
        ).fetchall()

    grouped: dict[str, list[dict]] = {}
    for row in rows_to_dicts(rows):
        grouped.setdefault(planner_medium_key(row), []).append(row)
    return grouped


def planner_medium_key(row: dict) -> str:
    prompt_inputs = _prompt_inputs(row)
    medium_id = (
        prompt_inputs.get("medium_id")
        or prompt_inputs.get("publishing_medium_id")
        or prompt_inputs.get("selected_medium_id")
    )
    if medium_id:
        return f"id:{medium_id}"
    medium = prompt_inputs.get("medium") if isinstance(prompt_inputs.get("medium"), dict) else {}
    medium_name = (
        medium.get("backlink_website_name")
        or medium.get("website_name")
        or (row.get("medium_name") or "")
    ).strip()
    account = (
        medium.get("backlink_blog_name")
        or medium.get("blog_name")
        or medium.get("account_name")
        or ""
    ).strip()
    if medium_name and account:
        return f"label:{medium_name.lower()} · {account.lower()}"
    return f"name:{((row.get('medium_name') or '').strip().lower())}"


def _prompt_inputs(row: dict) -> dict:
    try:
        parsed = json.loads(row.get("prompt_inputs") or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def list_brand_posts_for_planner_date(selected_date: str) -> dict[str, list[dict]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                gh.id,
                gh.created_at,
                gh.saved_at,
                gh.content_type,
                gh.title,
                gh.medium_name,
                gh.post_link,
                b.name AS brand_name
            FROM generation_history gh
            JOIN brands b ON b.id = gh.brand_id
            WHERE (TRIM(COALESCE(gh.post_link, '')) <> '' AND date(gh.saved_at) = ?)
               OR TRIM(COALESCE(gh.post_link, '')) = ''
            ORDER BY datetime(COALESCE(NULLIF(gh.saved_at, ''), gh.created_at)) DESC, gh.id DESC
            """,
            ((selected_date or "").strip(),),
        ).fetchall()

    grouped: dict[str, list[dict]] = {}
    for row in rows_to_dicts(rows):
        grouped.setdefault((row.get("brand_name") or "").strip(), []).append(row)
    return grouped
