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
    blog_name: str,
    writer_name: str,
    website_type: str,
    title_max_characters: int | str,
    max_characters: int | str,
    blog_url: str,
    tier_level: str,
    content_guidelines: str = "",
    notes: str = "",
    backlink_id: int | None = None,
) -> dict:
    cleaned_name = (website_name or "").strip()
    cleaned_blog_name = (blog_name or "").strip()
    cleaned_writer_name = (writer_name or "").strip()
    cleaned_website_type = (website_type or "").strip() or "blog"
    try:
        cleaned_title_max_characters = max(0, int(title_max_characters or 0))
    except (TypeError, ValueError):
        cleaned_title_max_characters = 0
    try:
        cleaned_max_characters = max(0, int(max_characters or 0))
    except (TypeError, ValueError):
        cleaned_max_characters = 0
    cleaned_url = (blog_url or "").strip()
    cleaned_tier = (tier_level or "").strip() or "Tier 1"
    cleaned_content_guidelines = (content_guidelines or "").strip()
    cleaned_notes = (notes or "").strip()

    if backlink_id:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE backlinks
                SET website_name = ?, blog_name = ?, writer_name = ?, website_type = ?, title_max_characters = ?, max_characters = ?, blog_url = ?, tier_level = ?, content_guidelines = ?, notes = ?
                WHERE id = ?
                """,
                (
                    cleaned_name,
                    cleaned_blog_name,
                    cleaned_writer_name,
                    cleaned_website_type,
                    cleaned_title_max_characters,
                    cleaned_max_characters,
                    cleaned_url,
                    cleaned_tier,
                    cleaned_content_guidelines,
                    cleaned_notes,
                    backlink_id,
                ),
            )
            row = connection.execute("SELECT * FROM backlinks WHERE id = ?", (backlink_id,)).fetchone()
            return row_to_dict(row) or {}

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO backlinks (website_name, blog_name, writer_name, website_type, title_max_characters, max_characters, blog_url, tier_level, content_guidelines, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cleaned_name,
                cleaned_blog_name,
                cleaned_writer_name,
                cleaned_website_type,
                cleaned_title_max_characters,
                cleaned_max_characters,
                cleaned_url,
                cleaned_tier,
                cleaned_content_guidelines,
                cleaned_notes,
            ),
        )
        row = connection.execute("SELECT * FROM backlinks WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return row_to_dict(row) or {}
