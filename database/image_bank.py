from database.common import get_connection, row_to_dict, rows_to_dicts


def list_image_bank_items() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM image_bank
            ORDER BY datetime(created_at) DESC, id DESC
            """
        ).fetchall()
        return rows_to_dicts(rows)


def get_image_bank_item(item_id: int) -> dict | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM image_bank WHERE id = ?", (item_id,)).fetchone()
        return row_to_dict(row)


def save_image_bank_item(
    query: str,
    title: str,
    source_url: str,
    file_path: str,
    file_name: str,
    file_size: int = 0,
    width: int = 0,
    height: int = 0,
    notes: str = "",
) -> dict:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO image_bank (query, title, source_url, file_path, file_name, file_size, width, height, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (query or "").strip(),
                (title or "").strip(),
                (source_url or "").strip(),
                (file_path or "").strip(),
                (file_name or "").strip(),
                int(file_size or 0),
                int(width or 0),
                int(height or 0),
                (notes or "").strip(),
            ),
        )
        row = connection.execute("SELECT * FROM image_bank WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return row_to_dict(row) or {}
