from pathlib import Path
from typing import Optional

from tinydb import Query, TinyDB


DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "app_db.json"

db = TinyDB(DB_PATH)
brands_table = db.table("brands")
pages_table = db.table("pages")
blogs_table = db.table("blogs")
keywords_table = db.table("keywords")
page_keywords_table = db.table("page_keywords")
blog_keywords_table = db.table("blog_keywords")


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


def get_or_create_keyword(keyword: str) -> Optional[dict]:
    keyword_value = (keyword or "").strip()
    normalized = normalize_keyword(keyword_value)
    if not normalized:
        return None

    Keyword = Query()
    existing = keywords_table.get(Keyword.normalized_keyword == normalized)
    if existing:
        return existing

    doc_id = keywords_table.insert(
        {
            "keyword": keyword_value,
            "normalized_keyword": normalized,
        }
    )
    return keywords_table.get(doc_id=doc_id)


def get_brand_pages(brand_normalized_name: str) -> list[dict]:
    Page = Query()
    return pages_table.search(Page.brand_normalized_name == brand_normalized_name)


def get_brand_blogs(brand_normalized_name: str) -> list[dict]:
    Blog = Query()
    return blogs_table.search(Blog.brand_normalized_name == brand_normalized_name)


def get_page_keywords(page_id: int) -> list[str]:
    Relation = Query()
    relations = page_keywords_table.search(Relation.page_id == page_id)
    keywords = []
    for relation in relations:
        keyword_record = keywords_table.get(doc_id=relation.get("keyword_id"))
        if keyword_record and keyword_record.get("keyword"):
            keywords.append(keyword_record["keyword"])
    return keywords


def get_blog_keywords(blog_id: int) -> list[str]:
    Relation = Query()
    relations = blog_keywords_table.search(Relation.blog_id == blog_id)
    keywords = []
    for relation in relations:
        keyword_record = keywords_table.get(doc_id=relation.get("keyword_id"))
        if keyword_record and keyword_record.get("keyword"):
            keywords.append(keyword_record["keyword"])
    return keywords


def get_brand_related_keywords(brand_normalized_name: str) -> list[str]:
    keywords = []
    seen = set()

    for page in get_brand_pages(brand_normalized_name):
        for keyword in get_page_keywords(page.doc_id):
            normalized = normalize_keyword(keyword)
            if normalized and normalized not in seen:
                seen.add(normalized)
                keywords.append(keyword)

    for blog in get_brand_blogs(brand_normalized_name):
        for keyword in get_blog_keywords(blog.doc_id):
            normalized = normalize_keyword(keyword)
            if normalized and normalized not in seen:
                seen.add(normalized)
                keywords.append(keyword)

    return keywords


def upsert_brand(
    brand: str,
    website: str = "",
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
    Brand = Query()
    existing = brands_table.get(Brand.normalized_name == normalized)
    payload = {
        "name": brand_name,
        "normalized_name": normalized,
        "website": (website or "").strip(),
        "tone": (tone or "").strip(),
        "notes": (notes or "").strip(),
        "niche": (niche or "").strip(),
        "main_keywords": (main_keywords or "").strip(),
        "logo_path": (logo_path or "").strip(),
    }

    if existing:
        merged = {
            "name": brand_name,
            "normalized_name": normalized,
            "website": payload["website"] or existing.get("website", ""),
            "tone": payload["tone"] or existing.get("tone", ""),
            "notes": payload["notes"] or existing.get("notes", ""),
            "niche": payload["niche"] or existing.get("niche", ""),
            "main_keywords": payload["main_keywords"] or existing.get("main_keywords", ""),
            "logo_path": payload["logo_path"] or existing.get("logo_path", ""),
        }
        brands_table.update(merged, doc_ids=[existing.doc_id])
        existing.update(merged)
        return existing

    doc_id = brands_table.insert(payload)
    created = brands_table.get(doc_id=doc_id)
    return created


def list_brand_names() -> list[str]:
    names = [
        record.get("name", "").strip()
        for record in brands_table.all()
        if record.get("name", "").strip()
    ]
    return sorted(set(names), key=str.lower)


def list_brand_records() -> list[dict]:
    records = brands_table.all()
    return sorted(records, key=lambda item: item.get("name", "").lower())


def get_brand_record(brand: str) -> Optional[dict]:
    normalized = normalize_brand_name(brand)
    if not normalized:
        return None
    Brand = Query()
    return brands_table.get(Brand.normalized_name == normalized)


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
        keywords = get_page_keywords(page.doc_id)
        if keywords:
            page_lines.append(f"- {page_type}: {page_title} | keywords: {', '.join(keywords)}")
        else:
            page_lines.append(f"- {page_type}: {page_title}")

    blog_lines = []
    for blog in brand_blogs[-10:]:
        title = blog.get("title", "").strip() or "Untitled"
        keywords = get_blog_keywords(blog.doc_id)
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
    doc_id = blogs_table.insert(
        {
            "brand_name": brand_record.get("name", brand_name),
            "brand_normalized_name": brand_record.get("normalized_name", normalize_brand_name(brand_name)),
            "title": (title or "").strip(),
            "primary_keyword": (keyword or "").strip(),
            "supporting_keyword": (supporting_keyword or "").strip(),
        }
    )
    blog_record = blogs_table.get(doc_id=doc_id)

    for index, keyword_value in enumerate(split_keywords(keyword, supporting_keyword)):
        keyword_record = get_or_create_keyword(keyword_value)
        if keyword_record:
            blog_keywords_table.insert(
                {
                    "blog_id": blog_record.doc_id,
                    "keyword_id": keyword_record.doc_id,
                    "is_primary": index == 0,
                }
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
    doc_id = pages_table.insert(
        {
            "brand_name": brand_record.get("name", brand_name),
            "brand_normalized_name": brand_record.get("normalized_name", normalize_brand_name(brand_name)),
            "page_title": (page_title or "").strip(),
            "page_type": (page_type or "").strip(),
            "primary_keyword": (keyword or "").strip(),
            "supporting_keywords": (supporting_keywords or "").strip(),
            "expectations": (expectations or "").strip(),
        }
    )
    page_record = pages_table.get(doc_id=doc_id)

    for index, keyword_value in enumerate(split_keywords(keyword, supporting_keywords)):
        keyword_record = get_or_create_keyword(keyword_value)
        if keyword_record:
            page_keywords_table.insert(
                {
                    "page_id": page_record.doc_id,
                    "keyword_id": keyword_record.doc_id,
                    "is_primary": index == 0,
                }
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
        if normalized_keyword in {normalize_keyword(item) for item in get_page_keywords(page.doc_id)}:
            page_matches.append(page)

    blog_matches = []
    for blog in get_brand_blogs(brand_normalized):
        if normalized_keyword in {normalize_keyword(item) for item in get_blog_keywords(blog.doc_id)}:
            blog_matches.append(blog)

    return {
        "brand_found": True,
        "keyword": keyword_value,
        "used": bool(page_matches or blog_matches),
        "page_matches": page_matches,
        "blog_matches": blog_matches,
    }
