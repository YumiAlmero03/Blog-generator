import json
import sqlite3

from database.common import LEGACY_DB_PATH, get_connection


def migrate_from_tinydb_json_if_needed():
    if not LEGACY_DB_PATH.exists():
        _migrate_money_site_to_settings_if_needed()
        return

    with get_connection() as connection:
        existing_brand = connection.execute("SELECT COUNT(*) FROM brands").fetchone()[0]
        existing_page = connection.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        existing_blog = connection.execute("SELECT COUNT(*) FROM blogs").fetchone()[0]
        existing_keyword = connection.execute("SELECT COUNT(*) FROM keywords").fetchone()[0]
        if any((existing_brand, existing_page, existing_blog, existing_keyword)):
            _migrate_money_site_to_settings_if_needed()
            return

    legacy_data = json.loads(LEGACY_DB_PATH.read_text(encoding="utf-8"))
    with get_connection() as connection:
        connection.execute("BEGIN")
        try:
            _migrate_table(
                connection,
                "brands",
                legacy_data.get("brands", {}),
                [
                    "name",
                    "normalized_name",
                    "website",
                    "money_site",
                    "tone",
                    "notes",
                    "niche",
                    "main_keywords",
                    "logo_path",
                ],
            )
            _migrate_table(
                connection,
                "keywords",
                legacy_data.get("keywords", {}),
                ["keyword", "normalized_keyword"],
            )
            _migrate_table(
                connection,
                "pages",
                legacy_data.get("pages", {}),
                [
                    "brand_name",
                    "brand_normalized_name",
                    "page_title",
                    "page_type",
                    "primary_keyword",
                    "supporting_keywords",
                    "expectations",
                ],
            )
            _migrate_table(
                connection,
                "blogs",
                legacy_data.get("blogs", {}),
                [
                    "brand_name",
                    "brand_normalized_name",
                    "title",
                    "primary_keyword",
                    "supporting_keyword",
                ],
            )
            _migrate_table(
                connection,
                "page_keywords",
                legacy_data.get("page_keywords", {}),
                ["page_id", "keyword_id", "is_primary"],
            )
            _migrate_table(
                connection,
                "blog_keywords",
                legacy_data.get("blog_keywords", {}),
                ["blog_id", "keyword_id", "is_primary"],
            )
            _migrate_table(
                connection,
                "legacy_used_keywords",
                legacy_data.get("used_keywords", {}),
                [
                    "brand_name",
                    "brand_normalized_name",
                    "keyword",
                    "normalized_keyword",
                    "content_type",
                    "title",
                ],
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    _migrate_money_site_to_settings_if_needed()


def _migrate_table(connection: sqlite3.Connection, table_name: str, records: dict, columns: list[str]):
    if not records:
        return

    sql = f"INSERT INTO {table_name} ({', '.join(['id', *columns])}) VALUES ({', '.join(['?'] * (len(columns) + 1))})"
    for record_id, payload in sorted(records.items(), key=lambda item: int(item[0])):
        values = [int(record_id)]
        for column in columns:
            value = payload.get(column, "")
            if column == "is_primary":
                value = int(bool(value))
            values.append(value)
        connection.execute(sql, values)


def _migrate_money_site_to_settings_if_needed():
    with get_connection() as connection:
        existing = connection.execute("SELECT value FROM settings WHERE key = 'money_site'").fetchone()
        if existing and (existing["value"] or "").strip():
            return

        row = connection.execute(
            """
            SELECT money_site
            FROM brands
            WHERE TRIM(COALESCE(money_site, '')) <> ''
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return

        connection.execute(
            """
            INSERT INTO settings (key, value)
            VALUES ('money_site', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (row["money_site"].strip(),),
        )
