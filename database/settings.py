from database.common import get_connection, row_to_dict


def set_setting(key: str, value: str) -> None:
    setting_key = (key or "").strip()
    if not setting_key:
        return

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (setting_key, (value or "").strip()),
        )


def get_setting(key: str, default: str = "") -> str:
    setting_key = (key or "").strip()
    if not setting_key:
        return default

    with get_connection() as connection:
        row = connection.execute("SELECT value FROM settings WHERE key = ?", (setting_key,)).fetchone()
        if not row:
            return default
        return row["value"] or default


def list_settings() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
        return [row_to_dict(row) for row in rows]
