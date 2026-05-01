import re
from typing import Optional

from database.common import (
    get_connection,
    normalize_brand_name,
    normalize_keyword,
    row_to_dict,
    rows_to_dicts,
)


def upsert_brand(
    brand: str,
    website: str = "",
    tone: str = "",
    notes: str = "",
    niche: str = "",
    main_keywords: str = "",
    logo_path: str = "",
    brand_color: str = "",
) -> Optional[dict]:
    brand_name = (brand or "").strip()
    if not brand_name:
        return None

    normalized = normalize_brand_name(brand_name)
    payload = {
        "name": brand_name,
        "normalized_name": normalized,
        "website": (website or "").strip(),
        "tone": (tone or "").strip(),
        "notes": (notes or "").strip(),
        "niche": (niche or "").strip(),
        "main_keywords": (main_keywords or "").strip(),
        "logo_path": (logo_path or "").strip(),
        "brand_color": normalize_brand_color(brand_color),
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
                "tone": payload["tone"] or existing_dict.get("tone", ""),
                "notes": payload["notes"] or existing_dict.get("notes", ""),
                "niche": payload["niche"] or existing_dict.get("niche", ""),
                "main_keywords": payload["main_keywords"] or existing_dict.get("main_keywords", ""),
                "logo_path": payload["logo_path"] or existing_dict.get("logo_path", ""),
                "brand_color": payload["brand_color"] or existing_dict.get("brand_color", ""),
            }
            connection.execute(
                """
                UPDATE brands
                SET name = ?, normalized_name = ?, website = ?, tone = ?, notes = ?, niche = ?, main_keywords = ?, logo_path = ?, brand_color = ?
                WHERE id = ?
                """,
                (
                    merged["name"],
                    merged["normalized_name"],
                    merged["website"],
                    merged["tone"],
                    merged["notes"],
                    merged["niche"],
                    merged["main_keywords"],
                    merged["logo_path"],
                    merged["brand_color"],
                    existing_dict["id"],
                ),
            )
            return row_to_dict(
                connection.execute("SELECT * FROM brands WHERE id = ?", (existing_dict["id"],)).fetchone()
            )

        cursor = connection.execute(
            """
            INSERT INTO brands (name, normalized_name, website, tone, notes, niche, main_keywords, logo_path, brand_color)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["name"],
                payload["normalized_name"],
                payload["website"],
                payload["tone"],
                payload["notes"],
                payload["niche"],
                payload["main_keywords"],
                payload["logo_path"],
                payload["brand_color"],
            ),
        )
        return row_to_dict(
            connection.execute("SELECT * FROM brands WHERE id = ?", (cursor.lastrowid,)).fetchone()
        )


def list_brand_names() -> list[str]:
    with get_connection() as connection:
        rows = connection.execute("SELECT name FROM brands WHERE TRIM(name) <> '' ORDER BY LOWER(name)").fetchall()
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
    from database.pages import get_blog_keywords, get_brand_blogs, get_brand_pages, get_brand_related_keywords, get_page_keywords

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
    tone = brand_record.get("tone", "").strip()
    notes = brand_record.get("notes", "").strip()
    niche = brand_record.get("niche", "").strip()
    main_keywords = brand_record.get("main_keywords", "").strip()
    if website:
        sections.append(f"Brand website: {website}")
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


def normalize_brand_color(color: str) -> str:
    cleaned = (color or "").strip()
    if not cleaned:
        return ""
    if re.fullmatch(r"#[0-9a-fA-F]{6}", cleaned):
        return cleaned.lower()
    return ""
