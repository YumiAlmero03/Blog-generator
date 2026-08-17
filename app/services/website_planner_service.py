import csv
import io
import json
import random
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from database import get_setting
from logger import logger
from utils import extract_json_string


WEBSITE_PLANNER_MAIN_PAGES_KEY = "website_planner_main_pages"
WEBSITE_PLANNER_TRUST_PAGES_KEY = "website_planner_trust_pages"

DEFAULT_MAIN_PAGES = [
    "Home",
    "About Us",
    "Services",
    "Contact Us",
    "Blog",
]
DEFAULT_TRUST_PAGES = [
    "Privacy Policy",
    "Terms and Conditions",
    "Disclaimer",
    "Cookie Policy",
    "Responsible Gaming",
]
DEFAULT_KEYWORD_CATEGORIES = [
    "Slots",
    "Sports",
    "Casino Games",
    "Live Casino",
    "Table Games",
    "Bonuses",
    "Responsible Gaming",
]
KEYWORD_PATTERNS = [
    "best {category}",
    "{category} guide",
    "how to play {category}",
    "{category} tips",
    "{category} strategy",
    "{category} for beginners",
    "mobile {category}",
    "{category} bonuses",
    "safe {category}",
    "{category} rules",
]
GOOGLE_TRENDS_RSS_URL = "https://trends.google.com/trending/rss"
GOOGLE_TRENDS_EXPLORE_URL = "https://trends.google.com/trends/explore"
GOOGLE_TRENDS_GEO = "PH"
GOOGLE_TRENDS_TIMEOUT = 4
V2_MIN_CORE_PAGES = 9
V2_MIN_SUPPORT_PAGES = 4
V2_MIN_BLOGS = 6
V2_MIN_CATEGORIES = 6

V2_CLUSTER_RULES = (
    ("login", "Login Page", ("login", "log in", "sign in")),
    ("registration", "Registration Page", ("register", "registration", "sign up", "signup", "create account")),
    ("app", "App Download Page", ("app", "apk", "download", "ios", "android")),
    ("casino", "Casino Page", ("casino", "online casino", "casino games")),
    ("sports-betting", "Sports Betting Page", ("sports betting", "sport betting", "sportsbook", "betting")),
    ("slots", "Slots Page", ("slots", "slot", "slot games")),
    ("live-casino", "Live Casino Page", ("live casino", "live dealer")),
    ("promotions", "Promotions Page", ("bonus", "promo", "promotion", "free spins", "voucher", "code")),
    ("payments", "Payment Methods Page", ("gcash", "maya", "deposit", "withdraw", "payment", "cash in", "cash out")),
    ("legitimacy", "Legit Review Page", ("legit", "review", "safe", "scam", "trusted")),
    ("support", "Support Page", ("support", "contact", "customer service", "help")),
    ("guides", "How-To Guide Page", ("how to", "guide", "tutorial", "rules")),
)


def default_main_pages_text() -> str:
    return "\n".join(DEFAULT_MAIN_PAGES)


def default_trust_pages_text() -> str:
    return "\n".join(DEFAULT_TRUST_PAGES)


def default_keyword_categories_text() -> str:
    return "\n".join(DEFAULT_KEYWORD_CATEGORIES)


def get_main_pages_setting() -> str:
    return get_setting(WEBSITE_PLANNER_MAIN_PAGES_KEY, default_main_pages_text())


def get_trust_pages_setting() -> str:
    return get_setting(WEBSITE_PLANNER_TRUST_PAGES_KEY, default_trust_pages_text())


def parse_page_list(value: str) -> list[str]:
    pages = []
    seen = set()
    for line in str(value or "").splitlines():
        for part in line.split(","):
            cleaned = " ".join(part.strip().split())
            normalized = cleaned.casefold()
            if cleaned and normalized not in seen:
                seen.add(normalized)
                pages.append(cleaned)
    return pages


def parse_keyword_categories(value: str | list[str]) -> list[str]:
    if isinstance(value, (list, tuple)):
        return parse_page_list("\n".join(str(item) for item in value))
    return parse_page_list(value)


def build_website_plan(
    main_pages_text: str,
    trust_pages_text: str,
    page_count: int,
    trust_page_count: int,
    blog_count: int,
    keyword_categories_text: str | list[str] = "",
    brand_names: list[str] | None = None,
    use_google_trends: bool = True,
    google_trends_geo: str = GOOGLE_TRENDS_GEO,
    rng=None,
) -> dict:
    randomizer = rng or random.SystemRandom()
    main_pages = parse_page_list(main_pages_text) or DEFAULT_MAIN_PAGES
    trust_pages = parse_page_list(trust_pages_text) or DEFAULT_TRUST_PAGES
    keyword_categories = _keyword_categories(keyword_categories_text, brand_names or [])
    cleaned_page_count = _count(page_count)
    cleaned_trust_page_count = _count(trust_page_count)
    cleaned_blog_count = _count(blog_count)

    planned_main_pages = _random_pick(main_pages, cleaned_page_count, randomizer)
    planned_trust_pages = _random_pick(trust_pages, cleaned_trust_page_count, randomizer)
    planned_blogs = _blog_keywords(
        keyword_categories,
        cleaned_blog_count,
        brand_names or [],
        randomizer,
        use_google_trends=use_google_trends,
        google_trends_geo=google_trends_geo,
    )

    return {
        "main_pages": _items("page", planned_main_pages),
        "trust_pages": _items("trust_page", planned_trust_pages),
        "blogs": _items("blog", planned_blogs),
        "summary": {
            "main_pages": len(planned_main_pages),
            "trust_pages": len(planned_trust_pages),
            "blogs": len(planned_blogs),
            "total": len(planned_main_pages) + len(planned_trust_pages) + len(planned_blogs),
            "blog_keyword_source": "Google Trends + category fallback" if use_google_trends else "Category fallback",
        },
    }


def parse_ahrefs_keyword_csv(file_bytes: bytes | str) -> list[dict]:
    text = _decode_keyword_csv_text(file_bytes)
    reader = csv.DictReader(io.StringIO(text), dialect=_sniff_keyword_csv_dialect(text))
    field_map = {_normalize_csv_header(field): field for field in (reader.fieldnames or [])}
    keyword_field = field_map.get("keyword")
    if not keyword_field:
        raise ValueError("Upload an Ahrefs CSV with a Keyword column.")

    rows = []
    seen = set()
    for index, row in enumerate(reader, start=1):
        keyword = _clean_text(row.get(keyword_field, ""))
        normalized = keyword.casefold()
        if not keyword or normalized in seen:
            continue
        seen.add(normalized)
        rows.append(
            {
                "index": index,
                "keyword": keyword,
                "volume": _int_value(_csv_value(row, field_map, "volume")),
                "difficulty": _csv_first_value(row, field_map, "keyword difficulty", "difficulty"),
                "global_volume": _int_value(_csv_value(row, field_map, "global volume")),
                "traffic_potential": _int_value(_csv_value(row, field_map, "traffic potential")),
                "parent_keyword": _clean_text(_csv_value(row, field_map, "parent keyword")),
                "intents": _clean_text(_csv_value(row, field_map, "intents")),
                "category": _clean_text(_csv_value(row, field_map, "category")),
            }
        )
    return rows


def _decode_keyword_csv_text(file_bytes: bytes | str) -> str:
    if not isinstance(file_bytes, bytes):
        return str(file_bytes or "")
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            text = file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "\x00" not in text[:1000]:
            return text
    return file_bytes.decode("utf-8-sig", errors="replace").replace("\x00", "")


def _sniff_keyword_csv_dialect(text: str):
    sample = (text or "")[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        return csv.excel_tab if "\t" in sample and sample.count("\t") >= sample.count(",") else csv.excel


def _normalize_csv_header(value: str) -> str:
    return " ".join(str(value or "").replace("\ufeff", "").strip().casefold().split())


def _csv_value(row: dict, field_map: dict[str, str], normalized_field: str) -> str:
    return row.get(field_map.get(normalized_field, ""), "")


def _csv_first_value(row: dict, field_map: dict[str, str], *normalized_fields: str) -> str:
    for field in normalized_fields:
        value = _clean_text(_csv_value(row, field_map, field))
        if value:
            return value
    return ""


def build_keyword_website_plan_v2(
    keyword_rows: list[dict],
    source_filename: str = "",
    blog_count: int = 10,
    use_google_trends: bool = False,
    google_trends_geo: str = GOOGLE_TRENDS_GEO,
    brand_names: list[str] | None = None,
    category_suggestions: str | list[str] = "",
) -> dict:
    rows = _sorted_keyword_rows(keyword_rows)
    if not rows:
        raise ValueError("No usable keywords were found in the CSV Keyword column.")

    preferred_blog_categories = _v2_preferred_blog_categories(category_suggestions)
    categories = _v2_categories(rows, category_suggestions=category_suggestions)
    clusters = _v2_keyword_clusters(rows)
    core_pages = _v2_core_pages(categories, clusters, rows)
    _v2_apply_homepage_sections(core_pages)
    support_pages = _v2_support_pages(rows)
    cleaned_blog_count = max(V2_MIN_BLOGS, min(100, _int_value(blog_count) or 10))
    blogs = _v2_blog_topics(
        rows,
        categories,
        core_pages,
        blog_count=cleaned_blog_count,
        use_google_trends=use_google_trends,
        google_trends_geo=google_trends_geo,
        brand_names=brand_names or [],
        preferred_categories=preferred_blog_categories,
    )
    blog_category_plans = _v2_blog_category_plans(preferred_blog_categories or categories, blogs)

    return {
        "source_filename": source_filename,
        "keywords": rows,
        "categories": categories,
        "core_pages": core_pages,
        "support_pages": support_pages,
        "blogs": blogs,
        "blog_category_plans": blog_category_plans,
        "wrap_up": _v2_wrap_up(rows, categories, core_pages, support_pages, blogs),
        "summary": {
            "keyword_count": len(rows),
            "category_count": len(categories),
            "core_page_count": len(core_pages),
            "support_page_count": len(support_pages),
            "blog_count": len(blogs),
            "blog_category_count": len(blog_category_plans),
            "total_volume": sum(int(item.get("volume", 0) or 0) for item in rows),
            "blog_keyword_source": "Google Trends + category fallback" if use_google_trends else "Category fallback",
        },
    }


def enrich_keyword_website_plan_v2_with_ai(provider, plan: dict, metadata: dict | None = None) -> dict:
    if not provider or not plan:
        return plan
    pages = plan.get("core_pages", [])
    if not pages:
        return plan

    prompt = _v2_ai_heading_prompt(pages, plan.get("blog_category_plans", []), metadata or {})
    raw = provider.generate_json(prompt)
    try:
        data = json.loads(extract_json_string(raw))
    except Exception as exc:
        logger.exception("website planner v2 heading AI parse failed. Raw response: %s", raw)
        raise ValueError("Could not parse Website Planner V2 AI headings.") from exc

    heading_items = data.get("pages", []) if isinstance(data, dict) else []
    by_index = {}
    for item in heading_items:
        try:
            index = int(item.get("index", 0))
        except (TypeError, ValueError):
            continue
        by_index[index] = item

    for page in pages:
        item = by_index.get(page.get("index"))
        if not item:
            continue
        h1 = _clean_text(item.get("h1", ""))
        h2s = [_clean_text(value) for value in item.get("suggested_h2s", []) if _clean_text(value)]
        if h1:
            page["h1"] = h1[:120]
        if h2s:
            page["suggested_h2s"] = h2s[:5]
        page["heading_source"] = "AI"

    category_items = data.get("blog_categories", []) if isinstance(data, dict) else []
    category_by_index = {}
    for item in category_items:
        try:
            index = int(item.get("index", 0))
        except (TypeError, ValueError):
            continue
        category_by_index[index] = item

    for category in plan.get("blog_category_plans", []):
        item = category_by_index.get(category.get("index"))
        if not item:
            continue
        title = _clean_text(item.get("title", ""))
        description = _clean_text(item.get("meta_description", ""))
        if title:
            title = _strict_length(title, 50, 60)
            category["title"] = title
            category["title_characters"] = len(title)
        if description:
            description = _strict_length(description, 130, 150)
            category["meta_description"] = description
            category["meta_description_characters"] = len(description)
        category["seo_copy_source"] = "AI"
    return plan


def _random_pick(items: list[str], count: int, randomizer) -> list[str]:
    if count <= 0 or not items:
        return []

    selected = []
    while len(selected) < count:
        shuffled = list(items)
        randomizer.shuffle(shuffled)
        for item in shuffled:
            selected.append(item)
            if len(selected) >= count:
                break
    return selected


def _sorted_keyword_rows(rows: list[dict]) -> list[dict]:
    return sorted(
        rows or [],
        key=lambda item: (-int(item.get("volume", 0) or 0), str(item.get("keyword", "")).casefold()),
    )


def _v2_categories(rows: list[dict], category_suggestions: str | list[str] = "") -> list[dict]:
    category_map = {}
    for row in rows:
        category = _clean_text(row.get("category", "")) or _derive_keyword_category(row.get("keyword", ""))
        key = category.casefold()
        item = category_map.setdefault(key, {"name": category, "keywords": [], "total_volume": 0})
        item["keywords"].append(row)
        item["total_volume"] += int(row.get("volume", 0) or 0)

    derived_candidates = [
        "Brand Navigation",
        "Login and Account Access",
        "App Download",
        "Casino Games",
        "Sports Betting",
        "Payments",
        "Promotions",
        "Trust and Reviews",
    ]
    for category in derived_candidates:
        if len(category_map) >= V2_MIN_CATEGORIES:
            break
        key = category.casefold()
        category_map.setdefault(key, {"name": category, "keywords": [], "total_volume": 0})
    for category in parse_keyword_categories(category_suggestions):
        key = category.casefold()
        category_map.setdefault(key, {"name": category, "keywords": [], "total_volume": 0})

    categories = sorted(category_map.values(), key=lambda item: (-item["total_volume"], item["name"].casefold()))
    return [
        {
            "index": index,
            "name": item["name"],
            "keyword_count": len(item["keywords"]),
            "total_volume": item["total_volume"],
            "top_keywords": [keyword["keyword"] for keyword in _sorted_keyword_rows(item["keywords"])[:6]],
            "keyword_rows": _sorted_keyword_rows(item["keywords"])[:12],
        }
        for index, item in enumerate(categories[: max(V2_MIN_CATEGORIES, len(categories))], start=1)
    ]


def _v2_keyword_clusters(rows: list[dict]) -> dict[str, dict]:
    clusters = {}
    for row in rows:
        cluster_key, cluster_name = _cluster_for_keyword(row.get("keyword", ""))
        cluster = clusters.setdefault(
            cluster_key,
            {
                "key": cluster_key,
                "name": cluster_name,
                "keywords": [],
                "total_volume": 0,
            },
        )
        cluster["keywords"].append(row)
        cluster["total_volume"] += int(row.get("volume", 0) or 0)
    return clusters


def _v2_core_pages(categories: list[dict], clusters: dict[str, dict], rows: list[dict]) -> list[dict]:
    cluster_items = sorted(clusters.values(), key=lambda item: (-item["total_volume"], item["name"].casefold()))
    used_names = set()
    used_keywords = set()
    used_slugs = set()
    pages = []

    for cluster in cluster_items:
        if len(pages) >= V2_MIN_CORE_PAGES and cluster["total_volume"] <= 0:
            break
        top_keywords = _sorted_keyword_rows(cluster["keywords"])
        primary_keyword = top_keywords[0]["keyword"] if top_keywords else cluster["name"]
        page_name = cluster["name"]
        key = page_name.casefold()
        keyword_key = primary_keyword.casefold()
        slug_key = _v2_page_slug(page_name, primary_keyword)
        if key in used_names or keyword_key in used_keywords or slug_key in used_slugs:
            continue
        used_names.add(key)
        used_keywords.add(keyword_key)
        used_slugs.add(slug_key)
        pages.append(_v2_page_item(len(pages) + 1, page_name, primary_keyword, top_keywords, cluster["total_volume"]))

    fallback_pages = [
        ("Homepage", _home_keyword(rows)),
        ("Casino Games Hub", _fallback_topic_keyword("casino games", rows)),
        ("Sports Betting Hub", _fallback_topic_keyword("sports betting", rows)),
        ("Mobile App Hub", _fallback_topic_keyword("app download", rows)),
        ("Login Help Hub", _fallback_topic_keyword("login", rows)),
        ("Payment Methods Hub", _fallback_topic_keyword("payment methods", rows)),
        ("Promotions Hub", _fallback_topic_keyword("promotions", rows)),
        ("Player Guides Hub", _fallback_topic_keyword("how to play", rows)),
        ("Reviews Hub", _fallback_topic_keyword("legit review", rows)),
    ]
    for page_name, keyword in fallback_pages:
        if len(pages) >= V2_MIN_CORE_PAGES:
            break
        key = page_name.casefold()
        keyword_key = keyword.casefold()
        slug_key = _v2_page_slug(page_name, keyword)
        if key not in used_names and keyword_key not in used_keywords and slug_key not in used_slugs:
            used_names.add(key)
            used_keywords.add(keyword_key)
            used_slugs.add(slug_key)
            pages.append(_v2_page_item(len(pages) + 1, page_name, keyword, [], 0))

    for row in rows:
        if len(pages) >= V2_MIN_CORE_PAGES:
            break
        page_name = _title_case_keyword(row["keyword"])
        key = page_name.casefold()
        keyword_key = row["keyword"].casefold()
        slug_key = _v2_page_slug(page_name, row["keyword"])
        if key in used_names or keyword_key in used_keywords or slug_key in used_slugs:
            continue
        used_names.add(key)
        used_keywords.add(keyword_key)
        used_slugs.add(slug_key)
        pages.append(_v2_page_item(len(pages) + 1, page_name, row["keyword"], [row], int(row.get("volume", 0) or 0)))

    return _v2_reindex_pages(_v2_homepage_first(pages))


def _v2_page_item(index: int, page_name: str, primary_keyword: str, keywords: list[dict], total_volume: int) -> dict:
    related = [item["keyword"] for item in keywords if item.get("keyword") != primary_keyword][:8]
    return {
        "index": index,
        "name": page_name,
        "slug": _v2_page_slug(page_name, primary_keyword or page_name),
        "primary_keyword": primary_keyword,
        "related_keywords": related,
        "keyword_rows": _sorted_keyword_rows(keywords)[:12],
        "keyword_count": len(keywords),
        "total_volume": total_volume,
        "intent": _intent_from_keywords(keywords),
        "h1": _title_case_keyword(primary_keyword or page_name),
        "suggested_h2s": _suggested_h2s(page_name, primary_keyword, related),
    }


def _v2_page_slug(page_name: str, primary_keyword: str) -> str:
    return "/" if str(page_name or "").casefold() in {"home", "homepage", "home page"} else _slug(primary_keyword or page_name)


def _v2_support_pages(rows: list[dict]) -> list[dict]:
    support_items = [
        ("About Us", "about us", "Trust"),
        ("Contact Us", "contact us", "Support"),
        ("Privacy Policy", "privacy policy", "Compliance"),
        ("Terms and Conditions", "terms and conditions", "Compliance"),
    ]
    return [
        {
            "index": index,
            "name": name,
            "slug": _slug(keyword),
            "primary_keyword": keyword,
            "intent": intent,
            "h1": name,
        }
        for index, (name, keyword, intent) in enumerate(support_items[:V2_MIN_SUPPORT_PAGES], start=1)
    ]


def _v2_blog_topics(
    rows: list[dict],
    categories: list[dict],
    core_pages: list[dict],
    blog_count: int = V2_MIN_BLOGS,
    use_google_trends: bool = True,
    google_trends_geo: str = GOOGLE_TRENDS_GEO,
    brand_names: list[str] | None = None,
    preferred_categories: list[dict] | None = None,
) -> list[dict]:
    candidates = []
    blog_categories = preferred_categories or categories
    if use_google_trends:
        candidates.extend(_v2_google_trends_blog_rows(blog_categories, brand_names or [], google_trends_geo))

    blogs = []
    used = set()
    for row in candidates:
        if len(blogs) >= blog_count:
            break
        keyword = row["keyword"]
        key = keyword.casefold()
        if key in used:
            continue
        used.add(key)
        category = _best_blog_category(keyword, blog_categories) or row.get("category") or _derive_keyword_category(keyword)
        target_page = _best_target_page(keyword, core_pages)
        blogs.append(
            {
                "index": len(blogs) + 1,
                "name": _blog_title(keyword),
                "primary_keyword": keyword,
                "category": category,
                "target_page": target_page.get("name", ""),
                "target_slug": target_page.get("slug", ""),
                "volume": int(row.get("volume", 0) or 0),
                "intent": row.get("intents", "") or _intent_from_keywords([row]),
                "source": row.get("source", "Ahrefs CSV"),
                "trend_url": row.get("trend_url", ""),
            }
        )

    for category in blog_categories:
        if len(blogs) >= blog_count:
            break
        for keyword in _v2_category_blog_keywords(category["name"]):
            if len(blogs) >= blog_count:
                break
            if keyword.casefold() in used:
                continue
            used.add(keyword.casefold())
            target_page = _best_target_page(keyword, core_pages)
            blogs.append(
                {
                    "index": len(blogs) + 1,
                    "name": _blog_title(keyword),
                    "primary_keyword": keyword.lower(),
                    "category": category["name"],
                    "target_page": target_page.get("name", ""),
                    "target_slug": target_page.get("slug", ""),
                    "volume": 0,
                    "intent": "Informational",
                    "source": "Category fallback",
                }
            )
    return blogs


def _v2_wrap_up(rows: list[dict], categories: list[dict], core_pages: list[dict], support_pages: list[dict], blogs: list[dict]) -> list[str]:
    top_keyword = rows[0]["keyword"] if rows else "the uploaded keyword set"
    return [
        f"Build {len(core_pages)} core SEO pages from the strongest keyword clusters, led by '{top_keyword}'.",
        f"Use {len(categories)} keyword categories to keep page hubs and blog topics separated.",
        f"Launch {len(support_pages)} trust/support pages to cover basic brand, compliance, and contact needs.",
        f"Create {len(blogs)} blog articles mapped back to matching core pages for internal linking.",
        "Prioritize high-volume navigational and transactional keywords first, then support them with informational blog content.",
    ]


def _cluster_for_keyword(keyword: str) -> tuple[str, str]:
    normalized = _normalize_keyword(keyword)
    for key, name, patterns in V2_CLUSTER_RULES:
        if any(pattern in normalized for pattern in patterns):
            return key, name
    return "home", "Homepage"


def _category_page_name(category: str) -> str:
    cleaned = _clean_text(category)
    normalized = cleaned.casefold()
    if normalized in {"general keywords", "brand", "brand navigation", "homepage", "home"}:
        return "Homepage"
    if normalized.endswith("page"):
        return _title_case_keyword(cleaned)
    if normalized.endswith(("hub", "category")):
        return _title_case_keyword(cleaned)
    return f"{_title_case_keyword(cleaned)} Page"


def _v2_homepage_first(pages: list[dict]) -> list[dict]:
    homepage = [page for page in pages if str(page.get("name", "")).casefold() in {"home", "homepage", "home page"}]
    others = [page for page in pages if page not in homepage]
    return homepage[:1] + others + homepage[1:]


def _v2_reindex_pages(pages: list[dict]) -> list[dict]:
    for index, page in enumerate(pages, start=1):
        page["index"] = index
    return pages


def _v2_apply_homepage_sections(pages: list[dict]) -> None:
    homepage = next((page for page in pages if str(page.get("name", "")).casefold() in {"home", "homepage", "home page"}), None)
    if not homepage:
        return
    sections = []
    for page in pages:
        if page is homepage:
            continue
        page_name = page.get("name", "")
        keyword = page.get("primary_keyword", page_name)
        sections.append(
            {
                "page_name": page_name,
                "target_slug": page.get("slug", ""),
                "primary_keyword": keyword,
                "h2": f"Explore {_title_case_keyword(page_name)}",
                "summary": f"Introduce {page_name} and guide visitors toward {page.get('slug', '') or 'the related page'}.",
                "cta": f"View {_title_case_keyword(page_name)}",
            }
        )
    homepage["homepage_sections"] = sections


def _v2_category_blog_keywords(category: str) -> list[str]:
    cleaned = _clean_text(category)
    if not cleaned:
        return []
    normalized = cleaned.casefold()
    if normalized in {"brand", "brand navigation", "general keywords"}:
        return [
            "brand overview",
            "homepage features",
            "new user tips",
            "platform updates",
        ]
    return [
        f"best {cleaned}",
        f"{cleaned} tips",
        f"how to choose {cleaned}",
        f"{cleaned} for beginners",
        f"{cleaned} features",
        f"{cleaned} mistakes to avoid",
    ]


def _v2_preferred_blog_categories(category_suggestions: str | list[str]) -> list[dict]:
    categories = parse_keyword_categories(category_suggestions)
    return [
        {
            "index": index,
            "name": category,
            "keyword_count": 0,
            "total_volume": 0,
            "top_keywords": [],
            "keyword_rows": [],
        }
        for index, category in enumerate(categories, start=1)
    ]


def _best_blog_category(keyword: str, categories: list[dict]) -> str:
    keyword_tokens = set(re.findall(r"[a-z0-9]+", str(keyword or "").casefold()))
    best_name = ""
    best_score = 0
    for category in categories:
        name = category.get("name", "")
        category_tokens = set(re.findall(r"[a-z0-9]+", name.casefold()))
        score = len(keyword_tokens & category_tokens)
        if score > best_score:
            best_name = name
            best_score = score
    return best_name or (categories[0].get("name", "") if categories else "")


def _v2_blog_category_plans(categories: list[dict], blogs: list[dict]) -> list[dict]:
    plans = []
    for index, category in enumerate(categories, start=1):
        name = category.get("name", "")
        category_blogs = [blog for blog in blogs if blog.get("category") == name]
        title = _strict_length(f"{_title_case_keyword(name)} Blog Ideas And Updates", 50, 60)
        description = _strict_length(
            f"Explore {name} articles with practical tips, comparisons, updates, and beginner-friendly answers for readers planning their next step.",
            130,
            150,
        )
        plans.append(
            {
                "index": index,
                "name": name,
                "title": title,
                "title_characters": len(title),
                "title_min_characters": 50,
                "title_max_characters": 60,
                "meta_description": description,
                "meta_description_characters": len(description),
                "meta_description_min_characters": 130,
                "meta_description_max_characters": 150,
                "blog_count": len(category_blogs),
                "topics": [blog.get("name", "") for blog in category_blogs[:6]],
            }
        )
    return plans


def _strict_length(value: str, min_chars: int, max_chars: int) -> str:
    cleaned = _clean_text(value)
    filler = " useful reader guide"
    while len(cleaned) < min_chars:
        cleaned = _clean_text(f"{cleaned}{filler}")
    if len(cleaned) <= max_chars:
        return cleaned
    trimmed = cleaned[:max_chars].rstrip()
    trimmed = re.sub(r"\s+\S*$", "", trimmed).strip()
    if len(trimmed) < min_chars:
        trimmed = cleaned[:max_chars].rstrip()
    return trimmed


def _derive_keyword_category(keyword: str) -> str:
    normalized = _normalize_keyword(keyword)
    for _, name, patterns in V2_CLUSTER_RULES:
        if any(pattern in normalized for pattern in patterns):
            return name.replace(" Page", "")
    return "General Keywords"


def _main_keyword_phrase(keyword: str) -> str:
    words = [word for word in re.findall(r"[a-z0-9]+", str(keyword or "").casefold()) if word not in {"com", "www"}]
    return " ".join(words[:3]) or "general keywords"


def _normalize_keyword(keyword: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(keyword or "").casefold()))


def _title_case_keyword(keyword: str) -> str:
    return " ".join(str(keyword or "").replace("-", " ").split()).title()


def _slug(keyword: str) -> str:
    slug = "-".join(re.findall(r"[a-z0-9]+", str(keyword or "").casefold()))
    return f"/{slug or 'page'}/"


def _intent_from_keywords(keywords: list[dict]) -> str:
    for item in keywords:
        intents = _clean_text(item.get("intents", ""))
        if intents:
            return intents
    text = " ".join(item.get("keyword", "") for item in keywords).casefold()
    if any(token in text for token in ("login", "register", "download", "casino", "betting", "bonus")):
        return "Transactional"
    if any(token in text for token in ("how", "guide", "what", "review", "legit")):
        return "Informational"
    return "Navigational"


def _suggested_h2s(page_name: str, primary_keyword: str, related_keywords: list[str]) -> list[str]:
    topic = _title_case_keyword(primary_keyword or page_name)
    page_topic = _title_case_keyword(page_name)
    base = [
        f"Why Players Search For {topic}",
        f"{page_topic} Features To Cover",
        "Search Intent And Conversion Path",
        "Content Blocks To Add Above The Fold",
    ]
    if related_keywords:
        base.append(f"Related Keyword Angle: {_title_case_keyword(related_keywords[0])}")
    return base[:5]


def _v2_ai_heading_prompt(pages: list[dict], blog_category_plans: list[dict], metadata: dict) -> str:
    page_payload = [
        {
            "index": page.get("index"),
            "page_name": page.get("name"),
            "primary_keyword": page.get("primary_keyword"),
            "related_keywords": page.get("related_keywords", [])[:6],
            "intent": page.get("intent"),
        }
        for page in pages[:20]
    ]
    category_payload = [
        {
            "index": category.get("index"),
            "category_name": category.get("name"),
            "blog_count": category.get("blog_count"),
            "topics": category.get("topics", [])[:6],
        }
        for category in blog_category_plans[:20]
    ]
    return f"""
You are an SEO content strategist.

Create stronger H1 and suggested H2 headings for these website planner pages.
Also create distinct blog category meta titles and meta descriptions.

Site metadata:
- Client/brand: {metadata.get("client") or "Not specified"}
- Domain: {metadata.get("domain") or "Not specified"}
- Target market: {metadata.get("target_market") or "Not specified"}
- Language: {metadata.get("language") or "English"}
- Site type: {metadata.get("site_type") or "Not specified"}

Rules:
- Return valid JSON only.
- Keep every H1 natural, engaging, and aligned with search intent.
- Use the primary keyword naturally in the H1 when it reads well.
- Avoid making every H2 use the same structure.
- Give each page 4-5 suggested H2s.
- H2s should sound like real page sections, not generic labels.
- Do not mention "SEO", "search intent", "above the fold", or "conversion path" in the headings.
- Make blog category titles varied. Do not repeat the same phrase pattern across categories.
- Every blog category title must be 50-60 characters.
- Every blog category meta description must be 130-150 characters.
- Count characters before returning JSON.
- Use the category topic and listed blog topics naturally.

Pages:
{json.dumps(page_payload, ensure_ascii=True)}

Blog categories:
{json.dumps(category_payload, ensure_ascii=True)}

Return this exact JSON shape:
{{
  "pages": [
    {{
      "index": 1,
      "h1": "Natural page H1",
      "suggested_h2s": ["H2 one", "H2 two", "H2 three", "H2 four"]
    }}
  ],
  "blog_categories": [
    {{
      "index": 1,
      "title": "Unique meta title between 50 and 60 characters",
      "meta_description": "Unique meta description between 130 and 150 characters that fits the category and blog topics."
    }}
  ]
}}
"""


def _brand_seed(rows: list[dict]) -> str:
    for row in rows:
        words = [word for word in re.findall(r"[a-z0-9]+", row.get("keyword", "").casefold()) if word not in {"com", "www"}]
        if words:
            return " ".join(words[:2])
    return ""


def _home_keyword(rows: list[dict]) -> str:
    general_rows = [row for row in rows if _derive_keyword_category(row.get("keyword", "")) == "General Keywords"]
    return (_sorted_keyword_rows(general_rows or rows)[0].get("keyword", "") if rows else "home").strip() or "home"


def _fallback_topic_keyword(topic: str, rows: list[dict]) -> str:
    topic_tokens = set(re.findall(r"[a-z0-9]+", topic.casefold()))
    for row in rows:
        row_tokens = set(re.findall(r"[a-z0-9]+", row.get("keyword", "").casefold()))
        if topic_tokens & row_tokens:
            return row.get("keyword", "")
    return _clean_text(topic)


def _v2_google_trends_blog_rows(categories: list[dict], brand_names: list[str], google_trends_geo: str) -> list[dict]:
    category_names = [category["name"] for category in categories if category.get("name")]
    trend_items = fetch_google_trends_blog_keywords(category_names, brand_names, geo=google_trends_geo)
    rows = []
    for index, item in enumerate(trend_items, start=1):
        keyword = _clean_text(item.get("name", ""))
        if not keyword:
            continue
        rows.append(
            {
                "index": index,
                "keyword": keyword,
                "volume": 0,
                "difficulty": "",
                "parent_keyword": "",
                "intents": "Informational",
                "category": _derive_keyword_category(keyword),
                "source": item.get("source", "Google Trends"),
                "trend_url": item.get("trend_url", ""),
            }
        )
    return rows


def _best_target_page(keyword: str, core_pages: list[dict]) -> dict:
    keyword_tokens = set(re.findall(r"[a-z0-9]+", str(keyword or "").casefold()))
    best = None
    best_score = -1
    for page in core_pages:
        page_tokens = set(re.findall(r"[a-z0-9]+", " ".join([page.get("name", ""), page.get("primary_keyword", "")]).casefold()))
        score = len(keyword_tokens & page_tokens)
        if score > best_score:
            best = page
            best_score = score
    return best or (core_pages[0] if core_pages else {})


def _blog_title(keyword: str) -> str:
    cleaned = _title_case_keyword(keyword)
    if any(cleaned.casefold().startswith(prefix) for prefix in ("how ", "what ", "why ", "is ")):
        return cleaned
    return f"{cleaned} Guide"


def _int_value(value) -> int:
    try:
        return max(0, int(float(str(value or "").replace(",", "").strip() or 0)))
    except (TypeError, ValueError):
        return 0


def _keyword_categories(value: str | list[str], brand_names: list[str]) -> list[str]:
    categories = parse_keyword_categories(value) or DEFAULT_KEYWORD_CATEGORIES
    filtered = [category for category in categories if not _contains_brand(category, brand_names)]
    return filtered or [category for category in DEFAULT_KEYWORD_CATEGORIES if not _contains_brand(category, brand_names)] or DEFAULT_KEYWORD_CATEGORIES


def _blog_keywords(
    categories: list[str],
    count: int,
    brand_names: list[str],
    randomizer,
    use_google_trends: bool = True,
    google_trends_geo: str = GOOGLE_TRENDS_GEO,
) -> list[dict]:
    if count <= 0:
        return []

    candidates = []
    if use_google_trends:
        candidates.extend(fetch_google_trends_blog_keywords(categories, brand_names, geo=google_trends_geo))

    for category in categories:
        cleaned_category = _keyword_category_text(category)
        if not cleaned_category:
            continue
        for pattern in KEYWORD_PATTERNS:
            keyword = pattern.format(category=cleaned_category)
            if not _contains_brand(keyword, brand_names):
                candidates.append(_keyword_item(keyword, source="Category fallback", geo=google_trends_geo))

    deduped = []
    seen = set()
    for item in candidates:
        keyword = item.get("name", "")
        normalized = keyword.casefold()
        if normalized not in seen:
            seen.add(normalized)
            deduped.append(item)

    return _random_pick(deduped or [_keyword_item("website blog keyword", source="Category fallback", geo=google_trends_geo)], count, randomizer)


def fetch_google_trends_blog_keywords(
    categories: list[str],
    brand_names: list[str] | None = None,
    geo: str = GOOGLE_TRENDS_GEO,
    timeout: int = GOOGLE_TRENDS_TIMEOUT,
) -> list[dict]:
    category_tokens = _category_tokens(categories)
    request = Request(
        f"{GOOGLE_TRENDS_RSS_URL}?geo={quote_plus(_google_trends_geo(geo))}",
        headers={"User-Agent": "Mozilla/5.0 (compatible; WebsitePlanner/1.0)"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return []

    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return []

    keywords = []
    for item in root.findall(".//item"):
        title_node = item.find("title")
        title = _clean_text(title_node.text if title_node is not None else "")
        if not title or _contains_brand(title, brand_names or []):
            continue
        if category_tokens and not _matches_category_tokens(title, category_tokens):
            continue
        keywords.append(_keyword_item(title.lower(), source="Google Trends", geo=geo))
    return keywords


def _keyword_category_text(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _contains_brand(value: str, brand_names: list[str]) -> bool:
    normalized_value = f" {str(value or '').casefold()} "
    for brand in brand_names:
        normalized_brand = " ".join(str(brand or "").casefold().split())
        if normalized_brand and f" {normalized_brand} " in normalized_value:
            return True
    return False


def _category_tokens(categories: list[str]) -> list[str]:
    tokens = []
    seen = set()
    for category in categories:
        for token in _keyword_category_text(category).split():
            if len(token) < 3:
                continue
            if token not in seen:
                seen.add(token)
                tokens.append(token)
    return tokens


def _matches_category_tokens(value: str, tokens: list[str]) -> bool:
    normalized = _keyword_category_text(value)
    return any(token in normalized for token in tokens)


def _keyword_item(keyword: str, source: str, geo: str = GOOGLE_TRENDS_GEO) -> dict:
    cleaned = _clean_text(keyword).lower()
    return {
        "name": cleaned,
        "source": source,
        "trend_url": _google_trends_url(cleaned, geo),
    }


def _google_trends_url(keyword: str, geo: str = GOOGLE_TRENDS_GEO) -> str:
    return f"{GOOGLE_TRENDS_EXPLORE_URL}?date=today%203-m&geo={quote_plus(_google_trends_geo(geo))}&q={quote_plus(keyword)}"


def _google_trends_geo(value: str) -> str:
    cleaned = "".join(character for character in str(value or "").upper() if character.isalpha())
    return cleaned[:2] or GOOGLE_TRENDS_GEO


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _items(kind: str, names: list[str]) -> list[dict]:
    items = []
    for index, item in enumerate(names, start=1):
        if isinstance(item, dict):
            payload = dict(item)
            payload.update(
                {
                    "index": index,
                    "kind": kind,
                    "name": item.get("name", ""),
                }
            )
            items.append(payload)
        else:
            items.append(
                {
                    "index": index,
                    "kind": kind,
                    "name": item,
                }
            )
    return items


def _count(value) -> int:
    try:
        return max(0, min(500, int(value or 0)))
    except (TypeError, ValueError):
        return 0
