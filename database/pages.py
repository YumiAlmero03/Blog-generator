from database.brands import get_brand_record, upsert_brand
from database.common import get_connection, normalize_brand_name, normalize_keyword, rows_to_dicts, split_keywords
from database.keywords import get_or_create_keyword


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
