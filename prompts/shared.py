from word_bank import build_banned_words_prompt_section

MIN_BLOG_WORDS = "1300"
MAX_BLOG_WORDS = "1400"

def build_brand_context_section(brand_context: str = "") -> str:
    cleaned = (brand_context or "").strip()
    if not cleaned:
        return ""
    return f"""
Known brand database context:
{cleaned}
"""


def build_backlink_context_section(
    backlink_website_name: str = "",
    backlink_blog_url: str = "",
    backlink_website_type: str = "",
    backlink_title_max_characters: int | str = 0,
    backlink_max_characters: int | str = 0,
    backlink_tier_level: str = "",
    backlink_blog_name: str = "",
    backlink_writer_name: str = "",
    backlink_content_guidelines: str = "",
) -> str:
    website_name = (backlink_website_name or "").strip()
    website_type = (backlink_website_type or "").strip().lower()
    try:
        title_max_characters = max(0, int(backlink_title_max_characters or 0))
    except (TypeError, ValueError):
        title_max_characters = 0
    try:
        max_characters = max(0, int(backlink_max_characters or 0))
    except (TypeError, ValueError):
        max_characters = 0
    tier_level = (backlink_tier_level or "").strip()
    blog_name = (backlink_blog_name or "").strip()
    writer_name = (backlink_writer_name or "").strip()
    content_guidelines = (backlink_content_guidelines or "").strip()

    if not any((website_name, website_type, title_max_characters, max_characters, tier_level, blog_name, writer_name, content_guidelines)):
        return ""

    lines = ["Publishing medium target:"]
    if website_name:
        lines.append(f"- Medium name: {website_name}")
    if blog_name:
        lines.append(f"- Publication/account name: {blog_name}")
    if writer_name:
        lines.append(f"- Writer name: {writer_name}")
    if website_type:
        lines.append(f"- Medium type: {website_type.replace('_', ' ')}")
    if title_max_characters:
        lines.append(f"- Title max characters: {title_max_characters}")
    if max_characters:
        lines.append(f"- Content max characters: {max_characters}")
    if tier_level:
        lines.append(f"- Tier level: {tier_level}")
    if content_guidelines:
        lines.append(f"- Medium content rules: {content_guidelines}")

    lines.extend(
        [
            "- The article should feel appropriate for this publishing target.",
            "- Keep the tone and examples broad enough to fit the selected medium or guest-post style placement.",
            "- Do not over-promote the brand. Keep it informative and natural first.",
            "- If the tier level is Tier 1, write as a blogger or publisher reviewing or discussing the selected brand in a natural editorial way.",
            "- If a publication/account name is provided, treat it as the blog, publication, account, or medium identity.",
            "- If a writer name is provided, treat it as the byline or author name.",
            "- If no publication/account name or writer name is provided, do not invent them.",
            "- Do not include the medium URL in the generated article. The only URL in the output should be the saved brand website URL when provided.",
        ]
    )
    lowered_target = f"{website_name} {blog_name} {website_type}".lower()
    if not title_max_characters and ("google sites" in lowered_target or "google_sites" in lowered_target):
        lines.extend(
            [
                "- Google Sites-style placements work better with compact titles. Keep titles under about 60 characters.",
                "- Favor straightforward page-like wording over long editorial headlines.",
            ]
        )
    if title_max_characters:
        lines.append(f"- Keep every generated title at or below {title_max_characters} characters.")
    if max_characters:
        lines.extend(
            [
                f"- Keep the full output within about {max_characters} characters.",
                "- Prioritize a tighter format, shorter sections, and concise delivery when a max character limit is provided.",
            ]
        )
    if website_type == "forum":
        lines.extend(
            [
                "- Write in a discussion-friendly, community-style voice.",
                "- Make the content feel like a helpful forum contribution or post, not a polished corporate article.",
            ]
        )
    elif website_type in {"social_media", "twitter"}:
        lines.extend(
            [
                "- Keep the content punchier, more conversational, and easier to skim.",
                "- Make the structure feel suitable for a social post, thread, or social-first article format.",
            ]
        )
        if website_type == "twitter" or "twitter" in lowered_target or "x.com" in lowered_target:
            lines.append("- For Twitter/X, write one very short post or a compact thread-style post. Avoid long article structure.")
        elif not max_characters:
            lines.append("- For Twitter/X-style mediums, write very short post-style content instead of a long article.")
    elif website_type == "google_sites":
        lines.extend(
            [
                "- Make the content suitable for Google Sites: clear, page-like, compact, and easy to scan.",
                "- Avoid long editorial titles and oversized article structure.",
            ]
        )
    elif website_type == "review":
        lines.extend(
            [
                "- Lean into an editorial review style with balanced observations, pros, use cases, or experience-driven commentary.",
            ]
        )
    elif website_type == "news":
        lines.extend(
            [
                "- Use a more publication-style tone with clear, informative framing and neutral presentation.",
            ]
        )
    elif website_type == "directory":
        lines.extend(
            [
                "- Keep the content concise, clear, and utility-focused, like a listing or short profile with useful context.",
            ]
        )
    elif website_type == "community":
        lines.extend(
            [
                "- Make the writing feel approachable and community-oriented, with helpful shared insights.",
            ]
        )

    return "\n" + "\n".join(lines) + "\n"
