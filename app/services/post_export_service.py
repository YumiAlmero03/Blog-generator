"""Shared post fields and portable JSON / WordPress WXR exports."""
import json
import re
from datetime import datetime, timezone
from html import unescape
from xml.etree import ElementTree as ET

CATEGORIES = ("Auto", "General", "Casino", "Slots", "Navigational", "Transactional", "Informational", "Commercial", "News")
GENERATORS = {"blog": "Blog", "rework": "Blog Rework", "news": "Blog"}


def normalize_category(value):
    return next((item for item in CATEGORIES if item.lower() == str(value or "").strip().lower()), "")


def suggest_category(data):
    """Prefer explicit search intent, then topic; never call an AI provider."""
    text = " ".join(str(data.get(key) or "") for key in (
        "selected_title", "keyword", "supporting_keyword", "supporting_keywords",
    )).lower()
    rules = (
        ("Navigational", r"\b(log[ -]?in|sign[ -]?in|official (site|website)|contact|customer support)\b"),
        ("Transactional", r"\b(sign[ -]?up|register|registration|deposit|withdraw(?:al)?|buy|purchase|subscribe|claim)\b"),
        ("Slots", r"\b(slots?|slot machines?|free spins?|jackpots?)\b"),
        ("Casino", r"\b(casinos?|blackjack|roulette|baccarat|poker)\b"),
        ("Commercial", r"\b(reviews?|compare|comparison|versus|best|top \d+)\b"),
        ("Informational", r"\b(how to|what is|what are|guides?|tutorials?|tips|learn)\b"),
    )
    for category, pattern in rules:
        if re.search(pattern, text):
            return category
    return "News" if data.get("generator") == "news" else "General"


def resolved_category(data):
    category = normalize_category(data.get("category"))
    return suggest_category(data) if category == "Auto" else category


def slugify(value):
    return re.sub(r"[^\w-]+", "-", value.lower(), flags=re.UNICODE).strip("-_") or "post"


def normalize_post(data, *, draft=False):
    def field(name):
        value = data.get(name, "")
        if not isinstance(value, str):
            raise ValueError(f"Invalid {name}.")
        return value.strip()

    generator = field("generator")
    if generator not in GENERATORS:
        raise ValueError("Invalid generator.")
    post = {
        "schema_version": 1, "generator": generator, "status": "draft",
        "title": field("selected_title"), "content_html": field("content_html"),
        "meta_description": field("meta_description_choice"),
        "category": resolved_category({**data, "category": field("category")}),
        "primary_keyword": field("keyword"), "brand": field("brand"),
        "language": field("language"),
    }
    for key in ("title", "meta_description", "category"):
        if not post[key]:
            raise ValueError(f"Please enter or select a {key.replace('_', ' ')} before saving or downloading.")
    if not draft and not unescape(re.sub(r"<[^>]*>", "", post["content_html"])).strip():
        raise ValueError("Please generate article content before saving or downloading.")
    post["slug"] = slugify(post["title"])
    try:
        tags = json.loads(field("tags_json") or "[]")
    except ValueError:
        raise ValueError("Invalid tags.") from None
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise ValueError("Invalid tags.")
    post["tags"] = list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
    # XML 1.0 cannot represent these control characters.
    if any(re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", value)
           for value in [*post.values(), *post["tags"]] if isinstance(value, str)):
        raise ValueError("Remove invalid control characters from the post.")
    return post


def export_post(post, format):
    if format == "json":
        return json.dumps(post, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), "application/json"
    if format != "wordpress":
        raise ValueError("Choose JSON or WordPress XML.")
    namespaces = {
        "wp": "http://wordpress.org/export/1.2/",
        "content": "http://purl.org/rss/1.0/modules/content/",
        "excerpt": "http://wordpress.org/export/1.2/excerpt/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }
    for prefix, uri in namespaces.items():
        ET.register_namespace(prefix, uri)

    def add(parent, name, value):
        if ":" in name:
            prefix, local = name.split(":", 1)
            name = "{" + namespaces[prefix] + "}" + local
        ET.SubElement(parent, name).text = str(value)

    root = ET.Element("rss", version="2.0")
    channel = ET.SubElement(root, "channel")
    for key, value in {"title": "Generated Posts", "link": "https://example.invalid", "description": "Generated post export", "wp:wxr_version": "1.2", "wp:base_site_url": "https://example.invalid", "wp:base_blog_url": "https://example.invalid"}.items():
        add(channel, key, value)
    item = ET.SubElement(channel, "item")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for key, value in {"title": post["title"], "content:encoded": post["content_html"], "excerpt:encoded": post["meta_description"], "dc:creator": "admin", "wp:post_id": "1", "wp:post_date": now, "wp:post_date_gmt": now, "wp:post_name": post["slug"], "wp:status": "draft", "wp:post_type": "post", "wp:post_parent": "0", "wp:menu_order": "0", "wp:comment_status": "closed", "wp:ping_status": "closed", "wp:is_sticky": "0"}.items():
        add(item, key, value)
    for domain, values in (("category", [post["category"]]), ("post_tag", post["tags"])):
        for value in values:
            ET.SubElement(item, "category", domain=domain, nicename=slugify(value)).text = value
    metadata = {"_yoast_wpseo_metadesc": post["meta_description"], "rank_math_description": post["meta_description"], "meta_description": post["meta_description"], "_yoast_wpseo_focuskw": post["primary_keyword"], "rank_math_focus_keyword": post["primary_keyword"], "_blog_generator": post["generator"], "_blog_brand": post["brand"], "_blog_language": post["language"]}
    for key, value in metadata.items():
        meta = ET.SubElement(item, "{" + namespaces["wp"] + "}postmeta")
        add(meta, "wp:meta_key", key)
        add(meta, "wp:meta_value", value)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), "application/xml"
