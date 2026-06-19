from database.common import get_connection, normalize_brand_name


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
                planner_notes TEXT NOT NULL DEFAULT '',
                niche TEXT NOT NULL DEFAULT '',
                main_keywords TEXT NOT NULL DEFAULT '',
                logo_path TEXT NOT NULL DEFAULT '',
                brand_color TEXT NOT NULL DEFAULT '',
                include_in_posting_planner INTEGER NOT NULL DEFAULT 0,
                include_in_backlink_follow_up INTEGER NOT NULL DEFAULT 0,
                include_in_website_checklist INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS keywords (
                id INTEGER PRIMARY KEY,
                keyword TEXT NOT NULL,
                normalized_keyword TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY,
                brand_id INTEGER,
                brand_normalized_name TEXT NOT NULL DEFAULT '',
                page_title TEXT NOT NULL DEFAULT '',
                page_type TEXT NOT NULL DEFAULT '',
                primary_keyword TEXT NOT NULL DEFAULT '',
                supporting_keywords TEXT NOT NULL DEFAULT '',
                expectations TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(brand_id) REFERENCES brands(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS blogs (
                id INTEGER PRIMARY KEY,
                brand_id INTEGER,
                brand_normalized_name TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                primary_keyword TEXT NOT NULL DEFAULT '',
                supporting_keyword TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(brand_id) REFERENCES brands(id) ON DELETE CASCADE
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
                brand_id INTEGER,
                brand_normalized_name TEXT NOT NULL DEFAULT '',
                keyword TEXT NOT NULL DEFAULT '',
                normalized_keyword TEXT NOT NULL DEFAULT '',
                content_type TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(brand_id) REFERENCES brands(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS banned_words (
                id INTEGER PRIMARY KEY,
                term TEXT NOT NULL,
                normalized_term TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS backlinks (
                id INTEGER PRIMARY KEY,
                website_name TEXT NOT NULL DEFAULT '',
                account_name TEXT NOT NULL DEFAULT '',
                blog_name TEXT NOT NULL DEFAULT '',
                writer_name TEXT NOT NULL DEFAULT '',
                website_type TEXT NOT NULL DEFAULT 'blog',
                post_type TEXT NOT NULL DEFAULT 'html',
                title_max_characters INTEGER NOT NULL DEFAULT 0,
                min_words INTEGER NOT NULL DEFAULT 0,
                max_characters INTEGER NOT NULL DEFAULT 0,
                blog_url TEXT NOT NULL DEFAULT '',
                tier_level TEXT NOT NULL DEFAULT 'Tier 1',
                include_in_tier1 INTEGER NOT NULL DEFAULT 1,
                brand_topic_mode TEXT NOT NULL DEFAULT 'example',
                posts_per_day INTEGER NOT NULL DEFAULT 0,
                include_in_website_checklist INTEGER NOT NULL DEFAULT 0,
                content_guidelines TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS checklist_items (
                id INTEGER PRIMARY KEY,
                checklist_type TEXT NOT NULL DEFAULT 'website',
                label TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS checklist_item_states (
                id INTEGER PRIMARY KEY,
                checklist_type TEXT NOT NULL DEFAULT 'website',
                subject_type TEXT NOT NULL DEFAULT '',
                subject_id TEXT NOT NULL DEFAULT '',
                checklist_item_id INTEGER NOT NULL,
                is_checked INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(checklist_type, subject_type, subject_id, checklist_item_id),
                FOREIGN KEY(checklist_item_id) REFERENCES checklist_items(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS social_profiles (
                id INTEGER PRIMARY KEY,
                brand_name TEXT NOT NULL DEFAULT '',
                social_type TEXT NOT NULL DEFAULT '',
                posts_per_day INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS generation_history (
                id INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                content_type TEXT NOT NULL DEFAULT '',
                brand_id INTEGER,
                title TEXT NOT NULL DEFAULT '',
                primary_keyword TEXT NOT NULL DEFAULT '',
                medium_name TEXT NOT NULL DEFAULT '',
                word_count INTEGER NOT NULL DEFAULT 0,
                meta_description TEXT NOT NULL DEFAULT '',
                post_link TEXT NOT NULL DEFAULT '',
                saved_at TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                prompt_inputs TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                quality_report TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(brand_id) REFERENCES brands(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS website_index_urls (
                id INTEGER PRIMARY KEY,
                url TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                check_status TEXT NOT NULL DEFAULT '',
                last_checked_at TEXT NOT NULL DEFAULT '',
                google_status TEXT NOT NULL DEFAULT '',
                google_verdict TEXT NOT NULL DEFAULT '',
                google_coverage_state TEXT NOT NULL DEFAULT '',
                google_robots_txt_state TEXT NOT NULL DEFAULT '',
                google_indexing_state TEXT NOT NULL DEFAULT '',
                google_last_crawl_time TEXT NOT NULL DEFAULT '',
                bing_status TEXT NOT NULL DEFAULT '',
                bing_last_checked_at TEXT NOT NULL DEFAULT '',
                bing_detail TEXT NOT NULL DEFAULT '',
                yahoo_status TEXT NOT NULL DEFAULT '',
                yahoo_last_checked_at TEXT NOT NULL DEFAULT '',
                yahoo_detail TEXT NOT NULL DEFAULT '',
                last_error TEXT NOT NULL DEFAULT ''
            );
            """
        )
        _ensure_column(connection, "backlinks", "account_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "backlinks", "blog_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "backlinks", "writer_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "backlinks", "website_type", "TEXT NOT NULL DEFAULT 'blog'")
        _ensure_column(connection, "backlinks", "post_type", "TEXT NOT NULL DEFAULT 'html'")
        _ensure_column(connection, "backlinks", "title_max_characters", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "backlinks", "min_words", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "backlinks", "max_characters", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "backlinks", "include_in_tier1", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(connection, "backlinks", "brand_topic_mode", "TEXT NOT NULL DEFAULT 'example'")
        _ensure_column(connection, "backlinks", "posts_per_day", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "backlinks", "include_in_website_checklist", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "backlinks", "content_guidelines", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "social_profiles", "brand_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "social_profiles", "social_type", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "social_profiles", "posts_per_day", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "brands", "brand_color", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "brands", "include_in_posting_planner", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "brands", "include_in_backlink_follow_up", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "brands", "include_in_website_checklist", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "brands", "planner_notes", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "pages", "brand_id", "INTEGER")
        _ensure_column(connection, "blogs", "brand_id", "INTEGER")
        _ensure_column(connection, "legacy_used_keywords", "brand_id", "INTEGER")
        _ensure_column(connection, "generation_history", "brand_id", "INTEGER")
        _migrate_brand_ids(connection, "pages")
        _migrate_brand_ids(connection, "blogs")
        _migrate_brand_ids(connection, "legacy_used_keywords")
        _migrate_brand_ids(connection, "generation_history")
        _ensure_column(connection, "generation_history", "medium_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "generation_history", "post_link", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "generation_history", "saved_at", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "generation_history", "quality_report", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "website_index_urls", "last_checked_at", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "website_index_urls", "check_status", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "website_index_urls", "google_status", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "website_index_urls", "google_verdict", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "website_index_urls", "google_coverage_state", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "website_index_urls", "google_robots_txt_state", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "website_index_urls", "google_indexing_state", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "website_index_urls", "google_last_crawl_time", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "website_index_urls", "bing_status", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "website_index_urls", "bing_last_checked_at", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "website_index_urls", "bing_detail", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "website_index_urls", "yahoo_status", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "website_index_urls", "yahoo_last_checked_at", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "website_index_urls", "yahoo_detail", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "website_index_urls", "last_error", "TEXT NOT NULL DEFAULT ''")
        connection.execute(
            """
            UPDATE generation_history
            SET saved_at = created_at
            WHERE TRIM(COALESCE(post_link, '')) <> ''
              AND TRIM(COALESCE(saved_at, '')) = ''
            """
        )
        connection.execute(
            """
            UPDATE backlinks
            SET blog_name = account_name
            WHERE TRIM(COALESCE(blog_name, '')) = ''
              AND TRIM(COALESCE(account_name, '')) <> ''
            """
        )


def _migrate_brand_ids(connection, table_name: str):
    existing_columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if "brand_id" not in existing_columns:
        return

    has_brand_name = "brand_name" in existing_columns
    has_brand_normalized_name = "brand_normalized_name" in existing_columns
    if not has_brand_name and not has_brand_normalized_name:
        return

    select_columns = ["id"]
    if has_brand_name:
        select_columns.append("brand_name")
    if has_brand_normalized_name:
        select_columns.append("brand_normalized_name")

    rows = connection.execute(
        f"SELECT {', '.join(select_columns)} FROM {table_name} WHERE brand_id IS NULL"
    ).fetchall()

    for row in rows:
        brand_id = None
        normalized = ""

        if has_brand_normalized_name:
            normalized = (row["brand_normalized_name"] or "").strip()

        if not normalized and has_brand_name:
            normalized = normalize_brand_name(row["brand_name"])

        if normalized:
            existing_brand = connection.execute(
                "SELECT id FROM brands WHERE normalized_name = ?",
                (normalized,),
            ).fetchone()
            if existing_brand:
                brand_id = existing_brand["id"]
            elif has_brand_name:
                brand_name = (row["brand_name"] or "").strip()
                brand_id = connection.execute(
                    "INSERT INTO brands (name, normalized_name) VALUES (?, ?)",
                    (brand_name, normalized),
                ).lastrowid

        if brand_id:
            connection.execute(
                f"UPDATE {table_name} SET brand_id = ? WHERE id = ?",
                (brand_id, row["id"]),
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
