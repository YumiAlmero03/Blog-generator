from database.common import get_connection, row_to_dict, rows_to_dicts


def list_find_replace_rules(active_only: bool = False) -> list[dict]:
    query = """
        SELECT id, created_at, find_text, replace_text, is_active, notes
        FROM find_replace_rules
    """
    params = ()
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY is_active DESC, id DESC"

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return rows_to_dicts(rows)


def get_find_replace_rule(rule_id: int) -> dict | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, created_at, find_text, replace_text, is_active, notes
            FROM find_replace_rules
            WHERE id = ?
            """,
            (rule_id,),
        ).fetchone()
    return row_to_dict(row)


def save_find_replace_rule(
    find_text: str,
    replace_text: str,
    notes: str = "",
    is_active: bool = True,
    rule_id: int | None = None,
) -> int:
    cleaned_find = (find_text or "").strip()
    if not cleaned_find:
        raise ValueError("Find text is required.")

    cleaned_replace = (replace_text or "").strip()
    cleaned_notes = (notes or "").strip()
    active_value = 1 if is_active else 0

    with get_connection() as connection:
        if rule_id:
            connection.execute(
                """
                UPDATE find_replace_rules
                SET find_text = ?, replace_text = ?, is_active = ?, notes = ?
                WHERE id = ?
                """,
                (cleaned_find, cleaned_replace, active_value, cleaned_notes, rule_id),
            )
            return rule_id

        cursor = connection.execute(
            """
            INSERT INTO find_replace_rules (find_text, replace_text, is_active, notes)
            VALUES (?, ?, ?, ?)
            """,
            (cleaned_find, cleaned_replace, active_value, cleaned_notes),
        )
        return cursor.lastrowid


def delete_find_replace_rule(rule_id: int) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM find_replace_rules WHERE id = ?", (rule_id,))
