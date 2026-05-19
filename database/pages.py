from database.brands import get_brand_record, upsert_brand
from database.common import get_connection, normalize_brand_name, normalize_keyword, rows_to_dicts, split_keywords
from database.keywords import get_or_create_keyword


def get_brand_pages(brand_id: int) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                p.id,
                p.brand_id,
                p.brand_normalized_name,
                p.page_title,
                p.page_type,
                p.primary_keyword,
                p.supporting_keywords,
                p.expectations,
                b.name AS brand_name
            FROM pages p
            JOIN brands b ON b.id = p.brand_id
            WHERE p.brand_id = ?
            ORDER BY p.id
            """,
            (brand_id,),
        ).fetchall()
        return rows_to_dicts(rows)


def get_brand_blogs(brand_id: int) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                b.id,
                b.brand_id,
                b.brand_normalized_name,
                b.title,
                b.primary_keyword,
                b.supporting_keyword,
                br.name AS brand_name
            FROM blogs b
            JOIN brands br ON br.id = b.brand_id
            WHERE b.brand_id = ?
            ORDER BY b.id
            """,
            (brand_id,),
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


def get_brand_related_keywords(brand_id: int) -> list[str]:
    keywords = []
    seen = set()

    for page in get_brand_pages(brand_id):
        for keyword in get_page_keywords(page["id"]):
            normalized = normalize_keyword(keyword)
            if normalized and normalized not in seen:
                seen.add(normalized)
                keywords.append(keyword)

    for blog in get_brand_blogs(brand_id):
        for keyword in get_blog_keywords(blog["id"]):
            normalized = normalize_keyword(keyword)
            if normalized and normalized not in seen:
                seen.add(normalized)
                keywords.append(keyword)

    return keywords


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
        columns = _table_columns(connection, "blogs")
        insert_columns = ["brand_id", "brand_normalized_name", "title", "primary_keyword", "supporting_keyword"]
        values = [
            brand_record["id"],
            brand_record.get("normalized_name", normalize_brand_name(brand_name)),
            (title or "").strip(),
            (keyword or "").strip(),
            (supporting_keyword or "").strip(),
        ]
        if "brand_name" in columns:
            insert_columns.insert(1, "brand_name")
            values.insert(1, brand_name)

        placeholders = ", ".join("?" for _ in insert_columns)
        cursor = connection.execute(
            f"INSERT INTO blogs ({', '.join(insert_columns)}) VALUES ({placeholders})",
            values,
        )
        blog_id = cursor.lastrowid

        for index, keyword_value in enumerate(split_keywords(keyword, supporting_keyword)):
            keyword_record = get_or_create_keyword(keyword_value, connection=connection)
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
        columns = _table_columns(connection, "pages")
        insert_columns = [
            "brand_id",
            "brand_normalized_name",
            "page_title",
            "page_type",
            "primary_keyword",
            "supporting_keywords",
            "expectations",
        ]
        values = [
            brand_record["id"],
            brand_record.get("normalized_name", normalize_brand_name(brand_name)),
            (page_title or "").strip(),
            (page_type or "").strip(),
            (keyword or "").strip(),
            (supporting_keywords or "").strip(),
            (expectations or "").strip(),
        ]
        if "brand_name" in columns:
            insert_columns.insert(1, "brand_name")
            values.insert(1, brand_name)

        placeholders = ", ".join("?" for _ in insert_columns)
        cursor = connection.execute(
            f"INSERT INTO pages ({', '.join(insert_columns)}) VALUES ({placeholders})",
            values,
        )
        page_id = cursor.lastrowid

        for index, keyword_value in enumerate(split_keywords(keyword, supporting_keywords)):
            keyword_record = get_or_create_keyword(keyword_value, connection=connection)
            if keyword_record:
                connection.execute(
                    "INSERT INTO page_keywords (page_id, keyword_id, is_primary) VALUES (?, ?, ?)",
                    (page_id, keyword_record["id"], int(index == 0)),
                )


def update_brand_page(
    page_id: int,
    page_title: str,
    page_type: str = "",
    primary_keyword: str = "",
    supporting_keywords: str = "",
    expectations: str = "",
) -> bool:
    with get_connection() as connection:
        existing = connection.execute("SELECT id FROM pages WHERE id = ?", (page_id,)).fetchone()
        if not existing:
            return False

        connection.execute(
            """
            UPDATE pages
            SET page_title = ?, page_type = ?, primary_keyword = ?, supporting_keywords = ?, expectations = ?
            WHERE id = ?
            """,
            (
                (page_title or "").strip(),
                (page_type or "").strip(),
                (primary_keyword or "").strip(),
                (supporting_keywords or "").strip(),
                (expectations or "").strip(),
                page_id,
            ),
        )
        connection.execute("DELETE FROM page_keywords WHERE page_id = ?", (page_id,))
        for index, keyword_value in enumerate(split_keywords(primary_keyword, supporting_keywords)):
            keyword_record = get_or_create_keyword(keyword_value, connection=connection)
            if keyword_record:
                connection.execute(
                    "INSERT INTO page_keywords (page_id, keyword_id, is_primary) VALUES (?, ?, ?)",
                    (page_id, keyword_record["id"], int(index == 0)),
                )
        return True


def _table_columns(connection, table_name: str) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def delete_brand_page(page_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM pages WHERE id = ?", (page_id,))
        return cursor.rowcount > 0


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

    brand_id = brand_record["id"]
    page_matches = []
    for page in get_brand_pages(brand_id):
        if normalized_keyword in {normalize_keyword(item) for item in get_page_keywords(page["id"])}:
            page_matches.append(page)

    blog_matches = []
    for blog in get_brand_blogs(brand_id):
        if normalized_keyword in {normalize_keyword(item) for item in get_blog_keywords(blog["id"])}:
            blog_matches.append(blog)

    return {
        "brand_found": True,
        "keyword": keyword_value,
        "used": bool(page_matches or blog_matches),
        "page_matches": page_matches,
        "blog_matches": blog_matches,
    }
