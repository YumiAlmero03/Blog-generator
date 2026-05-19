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


def delete_backlink(backlink_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM backlinks WHERE id = ?", (backlink_id,))
        return cursor.rowcount > 0


def update_backlink_notes(backlink_id: int, notes: str) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE backlinks SET notes = ? WHERE id = ?",
            ((notes or "").strip(), backlink_id),
        )
        return cursor.rowcount > 0


def save_backlink(
    website_name: str,
    blog_name: str,
    writer_name: str,
    website_type: str,
    post_type: str,
    title_max_characters: int | str,
    min_words: int | str,
    max_characters: int | str,
    blog_url: str,
    tier_level: str,
    posts_per_day: int | str = 0,
    content_guidelines: str = "",
    notes: str = "",
    include_in_tier1: int | bool | str = 1,
    brand_topic_mode: str = "example",
    backlink_id: int | None = None,
) -> dict:
    cleaned_name = (website_name or "").strip()
    cleaned_blog_name = (blog_name or "").strip()
    cleaned_writer_name = (writer_name or "").strip()
    cleaned_website_type = (website_type or "").strip() or "blog"
    cleaned_post_type = (post_type or "").strip().lower() or "html"
    if cleaned_post_type not in {"html", "markdown", "gutenberg", "text"}:
        cleaned_post_type = "html"
    try:
        cleaned_title_max_characters = max(0, int(title_max_characters or 0))
    except (TypeError, ValueError):
        cleaned_title_max_characters = 0
    try:
        cleaned_min_words = max(0, int(min_words or 0))
    except (TypeError, ValueError):
        cleaned_min_words = 0
    try:
        cleaned_max_characters = max(0, int(max_characters or 0))
    except (TypeError, ValueError):
        cleaned_max_characters = 0
    cleaned_url = (blog_url or "").strip()
    cleaned_tier = (tier_level or "").strip() or "Tier 1"
    try:
        cleaned_posts_per_day = max(0, int(posts_per_day or 0))
    except (TypeError, ValueError):
        cleaned_posts_per_day = 0
    cleaned_content_guidelines = (content_guidelines or "").strip()
    cleaned_notes = (notes or "").strip()
    cleaned_include_in_tier1 = _normalize_flag(include_in_tier1)
    cleaned_brand_topic_mode = _normalize_brand_topic_mode(brand_topic_mode, cleaned_name, cleaned_website_type)

    if backlink_id:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE backlinks
                SET website_name = ?, blog_name = ?, writer_name = ?, website_type = ?, post_type = ?, title_max_characters = ?, min_words = ?, max_characters = ?, blog_url = ?, tier_level = ?, posts_per_day = ?, content_guidelines = ?, notes = ?, include_in_tier1 = ?, brand_topic_mode = ?
                WHERE id = ?
                """,
                (
                    cleaned_name,
                    cleaned_blog_name,
                    cleaned_writer_name,
                    cleaned_website_type,
                    cleaned_post_type,
                    cleaned_title_max_characters,
                    cleaned_min_words,
                    cleaned_max_characters,
                    cleaned_url,
                    cleaned_tier,
                    cleaned_posts_per_day,
                    cleaned_content_guidelines,
                    cleaned_notes,
                    cleaned_include_in_tier1,
                    cleaned_brand_topic_mode,
                    backlink_id,
                ),
            )
            row = connection.execute("SELECT * FROM backlinks WHERE id = ?", (backlink_id,)).fetchone()
            return row_to_dict(row) or {}

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO backlinks (website_name, blog_name, writer_name, website_type, post_type, title_max_characters, min_words, max_characters, blog_url, tier_level, posts_per_day, content_guidelines, notes, include_in_tier1, brand_topic_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cleaned_name,
                cleaned_blog_name,
                cleaned_writer_name,
                cleaned_website_type,
                cleaned_post_type,
                cleaned_title_max_characters,
                cleaned_min_words,
                cleaned_max_characters,
                cleaned_url,
                cleaned_tier,
                cleaned_posts_per_day,
                cleaned_content_guidelines,
                cleaned_notes,
                cleaned_include_in_tier1,
                cleaned_brand_topic_mode,
            ),
        )
        row = connection.execute("SELECT * FROM backlinks WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return row_to_dict(row) or {}


def _normalize_flag(value) -> int:
    if isinstance(value, str):
        return 1 if value.strip().lower() in {"1", "true", "yes", "on"} else 0
    return 1 if value else 0


def _normalize_brand_topic_mode(value: str, website_name: str = "", website_type: str = "") -> str:
    cleaned = (value or "").strip().lower()
    if cleaned in {"main", "main_topic"}:
        return "main"
    if cleaned == "example":
        return "example"
    medium_text = f"{website_name} {website_type}".lower()
    if "github" in medium_text or "gitbook" in medium_text:
        return "main"
    return "example"
