from database.common import get_connection, row_to_dict, rows_to_dicts


def list_backlinks() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM backlinks ORDER BY LOWER(website_name), LOWER(blog_url), id DESC"
        ).fetchall()
        return rows_to_dicts(rows)


def get_backlink(backlink_id: int) -> dict | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM backlinks WHERE id = ?", (backlink_id,)).fetchone()
        return row_to_dict(row)


def save_backlink(
    website_name: str,
    account_name: str,
    blog_url: str,
    tier_level: str,
    notes: str = "",
    backlink_id: int | None = None,
) -> dict:
    cleaned_name = (website_name or "").strip()
    cleaned_account_name = (account_name or "").strip()
    cleaned_url = (blog_url or "").strip()
    cleaned_tier = (tier_level or "").strip() or "Tier 1"
    cleaned_notes = (notes or "").strip()

    if backlink_id:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE backlinks
                SET website_name = ?, account_name = ?, blog_url = ?, tier_level = ?, notes = ?
                WHERE id = ?
                """,
                (cleaned_name, cleaned_account_name, cleaned_url, cleaned_tier, cleaned_notes, backlink_id),
            )
            row = connection.execute("SELECT * FROM backlinks WHERE id = ?", (backlink_id,)).fetchone()
            return row_to_dict(row) or {}

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO backlinks (website_name, account_name, blog_url, tier_level, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (cleaned_name, cleaned_account_name, cleaned_url, cleaned_tier, cleaned_notes),
        )
        row = connection.execute("SELECT * FROM backlinks WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return row_to_dict(row) or {}
