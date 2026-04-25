import json
import sqlite3
from pathlib import Path
from typing import Optional


DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "app.db"
LEGACY_DB_PATH = DATA_DIR / "app_db.json"


def normalize_brand_name(brand: str) -> str:
    return " ".join((brand or "").strip().lower().split())


def normalize_keyword(keyword: str) -> str:
    return " ".join((keyword or "").strip().lower().split())


def split_keywords(*keyword_groups: str) -> list[str]:
    items = []
    for group in keyword_groups:
        if not group:
            continue
        for part in group.split(","):
            cleaned = part.strip()
            if cleaned:
                items.append(cleaned)

    unique = []
    seen = set()
    for item in items:
        normalized = normalize_keyword(item)
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(item)
    return unique


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def row_to_dict(row: sqlite3.Row | None) -> Optional[dict]:
    if row is None:
        return None
    return dict(row)


def rows_to_dicts(rows) -> list[dict]:
    return [dict(row) for row in rows]


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
            """
        )


def migrate_from_tinydb_json_if_needed():
    if not LEGACY_DB_PATH.exists():
        return

    with get_connection() as connection:
        existing_brand = connection.execute("SELECT COUNT(*) FROM brands").fetchone()[0]
        existing_page = connection.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        existing_blog = connection.execute("SELECT COUNT(*) FROM blogs").fetchone()[0]
        existing_keyword = connection.execute("SELECT COUNT(*) FROM keywords").fetchone()[0]
        if any((existing_brand, existing_page, existing_blog, existing_keyword)):
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


def _migrate_table(connection: sqlite3.Connection, table_name: str, records: dict, columns: list[str]):
    if not records:
        return

    placeholders = ", ".join("?" for _ in columns)
    column_list = ", ".join(["id", *columns])
    sql = f"INSERT INTO {table_name} ({column_list}) VALUES ({', '.join(['?'] * (len(columns) + 1))})"

    for record_id, payload in sorted(records.items(), key=lambda item: int(item[0])):
        values = [int(record_id)]
        for column in columns:
            value = payload.get(column, "")
            if column == "is_primary":
                value = int(bool(value))
            values.append(value)
        connection.execute(sql, values)


def get_or_create_keyword(keyword: str) -> Optional[dict]:
    keyword_value = (keyword or "").strip()
    normalized = normalize_keyword(keyword_value)
    if not normalized:
        return None

    with get_connection() as connection:
        existing = connection.execute(
            "SELECT * FROM keywords WHERE normalized_keyword = ?",
            (normalized,),
        ).fetchone()
        if existing:
            return row_to_dict(existing)

        cursor = connection.execute(
            "INSERT INTO keywords (keyword, normalized_keyword) VALUES (?, ?)",
            (keyword_value, normalized),
        )
        return row_to_dict(
            connection.execute("SELECT * FROM keywords WHERE id = ?", (cursor.lastrowid,)).fetchone()
        )


def get_brand_pages(brand_normalized_name: str) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM pages WHERE brand_normalized_name = ? ORDER BY id",
            (brand_normalized_name,),
        ).fetchall()
        return rows_to_dicts(rows)


def get_brand_blogs(brand_normalized_name: str) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM blogs WHERE brand_normalized_name = ? ORDER BY id",
            (brand_normalized_name,),
        ).fetchall()
        return rows_to_dicts(rows)


def get_page_keywords(page_id: int) -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT k.keyword
            FROM page_keywords pk
            JOIN keywords k ON k.id = pk.keyword_id
            WHERE pk.page_id = ?
            ORDER BY pk.id
            """,
            (page_id,),
        ).fetchall()
        return [row["keyword"] for row in rows if row["keyword"]]


def get_blog_keywords(blog_id: int) -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT k.keyword
            FROM blog_keywords bk
            JOIN keywords k ON k.id = bk.keyword_id
            WHERE bk.blog_id = ?
            ORDER BY bk.id
            """,
            (blog_id,),
        ).fetchall()
        return [row["keyword"] for row in rows if row["keyword"]]


def get_brand_related_keywords(brand_normalized_name: str) -> list[str]:
    keywords = []
    seen = set()

    for page in get_brand_pages(brand_normalized_name):
        for keyword in get_page_keywords(page["id"]):
            normalized = normalize_keyword(keyword)
            if normalized and normalized not in seen:
                seen.add(normalized)
                keywords.append(keyword)

    for blog in get_brand_blogs(brand_normalized_name):
        for keyword in get_blog_keywords(blog["id"]):
            normalized = normalize_keyword(keyword)
            if normalized and normalized not in seen:
                seen.add(normalized)
                keywords.append(keyword)

    return keywords


def upsert_brand(
    brand: str,
    website: str = "",
    money_site: str = "",
    tone: str = "",
    notes: str = "",
    niche: str = "",
    main_keywords: str = "",
    logo_path: str = "",
) -> Optional[dict]:
    brand_name = (brand or "").strip()
    if not brand_name:
        return None

    normalized = normalize_brand_name(brand_name)
    payload = {
        "name": brand_name,
        "normalized_name": normalized,
        "website": (website or "").strip(),
        "money_site": (money_site or "").strip(),
        "tone": (tone or "").strip(),
        "notes": (notes or "").strip(),
        "niche": (niche or "").strip(),
        "main_keywords": (main_keywords or "").strip(),
        "logo_path": (logo_path or "").strip(),
    }

    with get_connection() as connection:
        existing = connection.execute(
            "SELECT * FROM brands WHERE normalized_name = ?",
            (normalized,),
        ).fetchone()

        if existing:
            existing_dict = dict(existing)
            merged = {
                "name": brand_name,
                "normalized_name": normalized,
                "website": payload["website"] or existing_dict.get("website", ""),
                "money_site": payload["money_site"] or existing_dict.get("money_site", ""),
                "tone": payload["tone"] or existing_dict.get("tone", ""),
                "notes": payload["notes"] or existing_dict.get("notes", ""),
                "niche": payload["niche"] or existing_dict.get("niche", ""),
                "main_keywords": payload["main_keywords"] or existing_dict.get("main_keywords", ""),
                "logo_path": payload["logo_path"] or existing_dict.get("logo_path", ""),
            }
            connection.execute(
                """
                UPDATE brands
                SET name = ?, normalized_name = ?, website = ?, money_site = ?, tone = ?, notes = ?, niche = ?, main_keywords = ?, logo_path = ?
                WHERE id = ?
                """,
                (
                    merged["name"],
                    merged["normalized_name"],
                    merged["website"],
                    merged["money_site"],
                    merged["tone"],
                    merged["notes"],
                    merged["niche"],
                    merged["main_keywords"],
                    merged["logo_path"],
                    existing_dict["id"],
                ),
            )
            return row_to_dict(
                connection.execute("SELECT * FROM brands WHERE id = ?", (existing_dict["id"],)).fetchone()
            )

        cursor = connection.execute(
            """
            INSERT INTO brands (name, normalized_name, website, money_site, tone, notes, niche, main_keywords, logo_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["name"],
                payload["normalized_name"],
                payload["website"],
                payload["money_site"],
                payload["tone"],
                payload["notes"],
                payload["niche"],
                payload["main_keywords"],
                payload["logo_path"],
            ),
        )
        return row_to_dict(
            connection.execute("SELECT * FROM brands WHERE id = ?", (cursor.lastrowid,)).fetchone()
        )


def list_brand_names() -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT name FROM brands WHERE TRIM(name) <> '' ORDER BY LOWER(name)",
        ).fetchall()
        return sorted({row["name"].strip() for row in rows if row["name"].strip()}, key=str.lower)


def list_brand_records() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM brands ORDER BY LOWER(name)").fetchall()
        return rows_to_dicts(rows)


def get_brand_record(brand: str) -> Optional[dict]:
    normalized = normalize_brand_name(brand)
    if not normalized:
        return None
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM brands WHERE normalized_name = ?",
            (normalized,),
        ).fetchone()
        return row_to_dict(row)


def get_brand_context(brand: str) -> str:
    brand_record = get_brand_record(brand)
    if not brand_record:
        return ""

    normalized = brand_record.get("normalized_name", "")
    brand_pages = get_brand_pages(normalized)
    brand_blogs = get_brand_blogs(normalized)
    related_keywords = get_brand_related_keywords(normalized)

    page_lines = []
    for page in brand_pages[-10:]:
        page_type = page.get("page_type", "").strip() or "page"
        page_title = page.get("page_title", "").strip() or "Untitled"
        keywords = get_page_keywords(page["id"])
        if keywords:
            page_lines.append(f"- {page_type}: {page_title} | keywords: {', '.join(keywords)}")
        else:
            page_lines.append(f"- {page_type}: {page_title}")

    blog_lines = []
    for blog in brand_blogs[-10:]:
        title = blog.get("title", "").strip() or "Untitled"
        keywords = get_blog_keywords(blog["id"])
        if keywords:
            blog_lines.append(f"- blog: {title} | keywords: {', '.join(keywords)}")
        else:
            blog_lines.append(f"- blog: {title}")

    sections = [f"Known brand: {brand_record.get('name', '').strip()}"]
    website = brand_record.get("website", "").strip()
    money_site = brand_record.get("money_site", "").strip()
    tone = brand_record.get("tone", "").strip()
    notes = brand_record.get("notes", "").strip()
    niche = brand_record.get("niche", "").strip()
    main_keywords = brand_record.get("main_keywords", "").strip()
    if website:
        sections.append(f"Brand website: {website}")
    if money_site:
        sections.append(f"Brand money site: {money_site}")
    if niche:
        sections.append(f"Brand niche: {niche}")
    if main_keywords:
        sections.append(f"Brand main keywords: {main_keywords}")
    if tone:
        sections.append(f"Preferred brand tone: {tone}")
    if notes:
        sections.append(f"Brand notes: {notes}")
    if page_lines:
        sections.append("Existing pages for this brand:\n" + "\n".join(page_lines))
    if blog_lines:
        sections.append("Existing blogs for this brand:\n" + "\n".join(blog_lines))
    if related_keywords:
        sections.append("Brand-related keywords from saved pages and blogs:\n" + "\n".join(f"- {item}" for item in related_keywords[:25]))

    return "\n\n".join(sections)


def record_blog(
    brand: str,
    title: str,
    keyword: str = "",
    supporting_keyword: str = "",
) -> None:
    brand_name = (brand or "").strip()
    if not brand_name:
        return

    brand_record = upsert_brand(brand_name)
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO blogs (brand_name, brand_normalized_name, title, primary_keyword, supporting_keyword)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                brand_record.get("name", brand_name),
                brand_record.get("normalized_name", normalize_brand_name(brand_name)),
                (title or "").strip(),
                (keyword or "").strip(),
                (supporting_keyword or "").strip(),
            ),
        )
        blog_id = cursor.lastrowid

        for index, keyword_value in enumerate(split_keywords(keyword, supporting_keyword)):
            keyword_record = get_or_create_keyword(keyword_value)
            if keyword_record:
                connection.execute(
                    "INSERT INTO blog_keywords (blog_id, keyword_id, is_primary) VALUES (?, ?, ?)",
                    (blog_id, keyword_record["id"], int(index == 0)),
                )


def record_used_keyword(brand: str, keyword: str, content_type: str, title: str = "") -> None:
    if (content_type or "").strip().lower() == "blog":
        record_blog(brand=brand, title=title, keyword=keyword)


def record_page(
    brand: str,
    keyword: str,
    page_title: str,
    page_type: str = "",
    supporting_keywords: str = "",
    expectations: str = "",
) -> None:
    brand_name = (brand or "").strip()
    if not brand_name:
        return

    brand_record = upsert_brand(brand_name)
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO pages (brand_name, brand_normalized_name, page_title, page_type, primary_keyword, supporting_keywords, expectations)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                brand_record.get("name", brand_name),
                brand_record.get("normalized_name", normalize_brand_name(brand_name)),
                (page_title or "").strip(),
                (page_type or "").strip(),
                (keyword or "").strip(),
                (supporting_keywords or "").strip(),
                (expectations or "").strip(),
            ),
        )
        page_id = cursor.lastrowid

        for index, keyword_value in enumerate(split_keywords(keyword, supporting_keywords)):
            keyword_record = get_or_create_keyword(keyword_value)
            if keyword_record:
                connection.execute(
                    "INSERT INTO page_keywords (page_id, keyword_id, is_primary) VALUES (?, ?, ?)",
                    (page_id, keyword_record["id"], int(index == 0)),
                )


def check_keyword_usage(brand: str, keyword: str) -> dict:
    brand_record = get_brand_record(brand)
    keyword_value = (keyword or "").strip()
    normalized_keyword = normalize_keyword(keyword_value)

    if not brand_record or not normalized_keyword:
        return {
            "brand_found": bool(brand_record),
            "keyword": keyword_value,
            "used": False,
            "page_matches": [],
            "blog_matches": [],
        }

    brand_normalized = brand_record.get("normalized_name", "")
    page_matches = []
    for page in get_brand_pages(brand_normalized):
        if normalized_keyword in {normalize_keyword(item) for item in get_page_keywords(page["id"])}:
            page_matches.append(page)

    blog_matches = []
    for blog in get_brand_blogs(brand_normalized):
        if normalized_keyword in {normalize_keyword(item) for item in get_blog_keywords(blog["id"])}:
            blog_matches.append(blog)

    return {
        "brand_found": True,
        "keyword": keyword_value,
        "used": bool(page_matches or blog_matches),
        "page_matches": page_matches,
        "blog_matches": blog_matches,
    }


init_db()
migrate_from_tinydb_json_if_needed()
