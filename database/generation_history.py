import json

from database.common import get_connection, row_to_dict, rows_to_dicts


def record_generation(
    content_type: str,
    brand_name: str = "",
    title: str = "",
    primary_keyword: str = "",
    medium_name: str = "",
    word_count: int = 0,
    meta_description: str = "",
    tags: list[str] | str | None = None,
    prompt_inputs: dict | None = None,
    content: str = "",
    quality_report: dict | None = None,
) -> int:
    tags_text = ", ".join(tags) if isinstance(tags, list) else (tags or "")
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO generation_history (
                content_type, brand_name, title, primary_keyword, medium_name, word_count,
                meta_description, tags, prompt_inputs, content, quality_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (content_type or "").strip(),
                (brand_name or "").strip(),
                (title or "").strip(),
                (primary_keyword or "").strip(),
                (medium_name or "").strip(),
                int(word_count or 0),
                (meta_description or "").strip(),
                tags_text.strip(),
                json.dumps(prompt_inputs or {}, ensure_ascii=True),
                content or "",
                json.dumps(quality_report or {}, ensure_ascii=True),
            ),
        )
        return int(cursor.lastrowid)


def list_generation_history(limit: int = 100) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM generation_history
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ?
            """,
            (max(1, int(limit or 100)),),
        ).fetchall()
        return rows_to_dicts(rows)


def get_generation_history_item(history_id: int) -> dict | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM generation_history WHERE id = ?",
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
              COUNT(DISTINCT NULLIF(TRIM(brand_name), '')) AS brand_count
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
