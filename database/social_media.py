from database.common import get_connection, row_to_dict, rows_to_dicts


def list_social_profiles() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM social_profiles
            ORDER BY LOWER(brand_name), LOWER(social_type), id DESC
            """
        ).fetchall()
        return rows_to_dicts(rows)


def get_social_profile(profile_id: int) -> dict | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM social_profiles WHERE id = ?", (profile_id,)).fetchone()
        return row_to_dict(row)


def save_social_profile(
    brand_name: str,
    social_type: str,
    posts_per_day: int | str = 0,
    profile_id: int | None = None,
) -> dict:
    cleaned_brand = (brand_name or "").strip()
    cleaned_type = (social_type or "").strip()
    try:
        cleaned_posts_per_day = max(0, int(posts_per_day or 0))
    except (TypeError, ValueError):
        cleaned_posts_per_day = 0

    if profile_id:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE social_profiles
                SET brand_name = ?, social_type = ?, posts_per_day = ?
                WHERE id = ?
                """,
                (cleaned_brand, cleaned_type, cleaned_posts_per_day, profile_id),
            )
            row = connection.execute("SELECT * FROM social_profiles WHERE id = ?", (profile_id,)).fetchone()
            return row_to_dict(row) or {}

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO social_profiles (brand_name, social_type, posts_per_day)
            VALUES (?, ?, ?)
            """,
            (cleaned_brand, cleaned_type, cleaned_posts_per_day),
        )
        row = connection.execute("SELECT * FROM social_profiles WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return row_to_dict(row) or {}


def delete_social_profile(profile_id: int):
    with get_connection() as connection:
        connection.execute("DELETE FROM social_profiles WHERE id = ?", (profile_id,))
