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
    account_name: str = "",
    platform_account_id: str = "",
    profile_url: str = "",
    api_key: str = "",
    api_secret: str = "",
    access_token: str = "",
    refresh_token: str = "",
    is_active: bool | int = True,
    notes: str = "",
) -> dict:
    cleaned_brand = (brand_name or "").strip()
    cleaned_type = (social_type or "").strip()
    cleaned_account = (account_name or "").strip()
    cleaned_platform_account_id = (platform_account_id or "").strip()
    cleaned_profile_url = (profile_url or "").strip()
    cleaned_api_key = (api_key or "").strip()
    cleaned_api_secret = (api_secret or "").strip()
    cleaned_access_token = (access_token or "").strip()
    cleaned_refresh_token = (refresh_token or "").strip()
    cleaned_notes = (notes or "").strip()
    try:
        cleaned_posts_per_day = max(0, int(posts_per_day or 0))
    except (TypeError, ValueError):
        cleaned_posts_per_day = 0
    cleaned_is_active = 1 if is_active else 0

    if profile_id:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE social_profiles
                SET brand_name = ?, social_type = ?, account_name = ?, platform_account_id = ?, profile_url = ?, api_key = ?, api_secret = ?, access_token = ?, refresh_token = ?, posts_per_day = ?, is_active = ?, notes = ?
                WHERE id = ?
                """,
                (
                    cleaned_brand,
                    cleaned_type,
                    cleaned_account,
                    cleaned_platform_account_id,
                    cleaned_profile_url,
                    cleaned_api_key,
                    cleaned_api_secret,
                    cleaned_access_token,
                    cleaned_refresh_token,
                    cleaned_posts_per_day,
                    cleaned_is_active,
                    cleaned_notes,
                    profile_id,
                ),
            )
            row = connection.execute("SELECT * FROM social_profiles WHERE id = ?", (profile_id,)).fetchone()
            return row_to_dict(row) or {}

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO social_profiles (brand_name, social_type, account_name, platform_account_id, profile_url, api_key, api_secret, access_token, refresh_token, posts_per_day, is_active, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cleaned_brand,
                cleaned_type,
                cleaned_account,
                cleaned_platform_account_id,
                cleaned_profile_url,
                cleaned_api_key,
                cleaned_api_secret,
                cleaned_access_token,
                cleaned_refresh_token,
                cleaned_posts_per_day,
                cleaned_is_active,
                cleaned_notes,
            ),
        )
        row = connection.execute("SELECT * FROM social_profiles WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return row_to_dict(row) or {}


def delete_social_profile(profile_id: int):
    with get_connection() as connection:
        connection.execute("DELETE FROM social_profiles WHERE id = ?", (profile_id,))
