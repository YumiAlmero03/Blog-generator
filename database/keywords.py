from typing import Optional

from database.common import get_connection, normalize_keyword, row_to_dict


def get_or_create_keyword(keyword: str) -> Optional[dict]:
    keyword_value = (keyword or "").strip()
    normalized = normalize_keyword(keyword_value)
    if not normalized:
        return None

    with get_connection() as connection:
        existing = connection.execute(
            "SELECT * FROM keywords WHERE normalized_keyword = ?",
            (normalized,),
        ).fetchone()
        if existing:
            return row_to_dict(existing)

        cursor = connection.execute(
            "INSERT INTO keywords (keyword, normalized_keyword) VALUES (?, ?)",
            (keyword_value, normalized),
        )
        return row_to_dict(
            connection.execute("SELECT * FROM keywords WHERE id = ?", (cursor.lastrowid,)).fetchone()
        )
