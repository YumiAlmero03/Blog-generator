import random
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from database import get_setting


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
