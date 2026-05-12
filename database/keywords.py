import sqlite3
from typing import Optional

from database.common import get_connection, normalize_keyword, row_to_dict


def get_or_create_keyword(keyword: str, connection: sqlite3.Connection | None = None) -> Optional[dict]:
    keyword_value = (keyword or "").strip()
    normalized = normalize_keyword(keyword_value)
    if not normalized:
        return None

    if connection is not None:
        return _get_or_create_keyword_with_connection(connection, keyword_value, normalized)

    with get_connection() as owned_connection:
        return _get_or_create_keyword_with_connection(owned_connection, keyword_value, normalized)


def _get_or_create_keyword_with_connection(
    connection: sqlite3.Connection,
    keyword_value: str,
    normalized: str,
) -> Optional[dict]:
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
