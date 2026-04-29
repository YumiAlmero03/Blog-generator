from database.common import get_connection


def init_db():
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS brands (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL UNIQUE,
                website TEXT NOT NULL DEFAULT '',
                money_site TEXT NOT NULL DEFAULT '',
                tone TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                niche TEXT NOT NULL DEFAULT '',
                main_keywords TEXT NOT NULL DEFAULT '',
                logo_path TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS keywords (
                id INTEGER PRIMARY KEY,
                keyword TEXT NOT NULL,
                normalized_keyword TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY,
                brand_name TEXT NOT NULL,
                brand_normalized_name TEXT NOT NULL,
                page_title TEXT NOT NULL DEFAULT '',
                page_type TEXT NOT NULL DEFAULT '',
                primary_keyword TEXT NOT NULL DEFAULT '',
                supporting_keywords TEXT NOT NULL DEFAULT '',
                expectations TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS blogs (
                id INTEGER PRIMARY KEY,
                brand_name TEXT NOT NULL,
                brand_normalized_name TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                primary_keyword TEXT NOT NULL DEFAULT '',
                supporting_keyword TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS page_keywords (
                id INTEGER PRIMARY KEY,
                page_id INTEGER NOT NULL,
                keyword_id INTEGER NOT NULL,
                is_primary INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(page_id) REFERENCES pages(id) ON DELETE CASCADE,
                FOREIGN KEY(keyword_id) REFERENCES keywords(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS blog_keywords (
                id INTEGER PRIMARY KEY,
                blog_id INTEGER NOT NULL,
                keyword_id INTEGER NOT NULL,
                is_primary INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(blog_id) REFERENCES blogs(id) ON DELETE CASCADE,
                FOREIGN KEY(keyword_id) REFERENCES keywords(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS legacy_used_keywords (
                id INTEGER PRIMARY KEY,
                brand_name TEXT NOT NULL DEFAULT '',
                brand_normalized_name TEXT NOT NULL DEFAULT '',
                keyword TEXT NOT NULL DEFAULT '',
                normalized_keyword TEXT NOT NULL DEFAULT '',
                content_type TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS backlinks (
                id INTEGER PRIMARY KEY,
                website_name TEXT NOT NULL DEFAULT '',
                account_name TEXT NOT NULL DEFAULT '',
                blog_name TEXT NOT NULL DEFAULT '',
                writer_name TEXT NOT NULL DEFAULT '',
                website_type TEXT NOT NULL DEFAULT 'blog',
                max_characters INTEGER NOT NULL DEFAULT 0,
                blog_url TEXT NOT NULL DEFAULT '',
                tier_level TEXT NOT NULL DEFAULT 'Tier 1',
                notes TEXT NOT NULL DEFAULT ''
            );
            """
        )
        _ensure_column(connection, "backlinks", "account_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "backlinks", "blog_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "backlinks", "writer_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "backlinks", "website_type", "TEXT NOT NULL DEFAULT 'blog'")
        _ensure_column(connection, "backlinks", "max_characters", "INTEGER NOT NULL DEFAULT 0")
        connection.execute(
            """
            UPDATE backlinks
            SET blog_name = account_name
            WHERE TRIM(COALESCE(blog_name, '')) = ''
              AND TRIM(COALESCE(account_name, '')) <> ''
            """
        )


def _ensure_column(connection, table_name: str, column_name: str, column_definition: str):
    existing_columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in existing_columns:
        return

    connection.execute(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
    )
