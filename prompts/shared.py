from word_bank import build_banned_words_prompt_section

MIN_BLOG_WORDS = "1300"
MAX_BLOG_WORDS = "1400"


def _is_brazilian_portuguese(language: str) -> bool:
    cleaned = " ".join(str(language or "English").split()).strip().lower()
    return cleaned in {
        "brazilian portuguese",
        "brazil portugues",
        "brazil portuguese",
        "brazilian portugues",
        "portuguese (brazil)",
        "portugues (brasil)",
        "português (brasil)",
        "pt-br",
        "pt_br",
    }


def build_language_instruction(language: str = "English") -> str:
    cleaned = " ".join(str(language or "English").split()).strip() or "English"
    extra_rules = ""
    if _is_brazilian_portuguese(cleaned):
        extra_rules = "\n- Use natural Brazilian Portuguese (pt-BR) vocabulary, spelling, grammar, and phrasing (not European Portuguese)."
    return f"""
Required language:
{cleaned}

Language rules:
- Write the content in {cleaned}.{extra_rules}
- Keep brand names, URLs, required anchor text, product names, and proper nouns unchanged unless the user-provided language naturally requires a common localized form.
- Preserve the requested JSON keys exactly in English.
"""


def build_visual_language_instruction(language: str = "English") -> str:
    cleaned = " ".join(str(language or "English").split()).strip() or "English"
    quoted_language_note = ""
    if _is_brazilian_portuguese(cleaned):
        quoted_language_note = " (using natural Brazilian Portuguese / pt-BR vocabulary and spelling)"
    return f"""
Selected language for any visible text inside the image:
{cleaned}

Visual language rules:
- Write the Visual / Image Descriptions strictly in English (subject, scene, setting, action, colors, lighting, composition, and style), even when the selected article language is {cleaned}.
- Only if visible text is needed inside the image itself (such as a sign, headline, button, label, badge, or callout), put that exact in-image text in double quotes ("...") and write only the text inside those quotes in {cleaned}{quoted_language_note}.
- Keep everything outside double quotes strictly in English.
- Escape any double quotes around in-image text inside JSON strings (for example \\"Text\\") so the JSON stays valid.
- Preserve the requested JSON keys strictly in English.
"""


def build_brand_context_section(brand_context: str = "") -> str:
    cleaned = (brand_context or "").strip()
    if not cleaned:
        return ""
#     return f"""
# Known brand database context:
# {cleaned}
# """


def build_backlink_context_section(
    backlink_website_name: str = "",
    backlink_blog_url: str = "",
    backlink_website_type: str = "",
    backlink_post_type: str = "html",
    backlink_title_max_characters: int | str = 0,
    backlink_min_words: int | str = 0,
    backlink_max_characters: int | str = 0,
    backlink_tier_level: str = "",
    backlink_blog_name: str = "",
    backlink_writer_name: str = "",
    backlink_content_guidelines: str = "",
) -> str:
    website_name = (backlink_website_name or "").strip()
    website_type = (backlink_website_type or "").strip().lower()
    post_type = (backlink_post_type or "html").strip().lower()
    if post_type not in {"html", "markdown", "gutenberg", "text"}:
        post_type = "html"
    try:
        title_max_characters = max(0, int(backlink_title_max_characters or 0))
    except (TypeError, ValueError):
        title_max_characters = 0
    try:
        min_words = max(0, int(backlink_min_words or 0))
    except (TypeError, ValueError):
        min_words = 0
    try:
        max_words = max(0, int(backlink_max_characters or 0))
    except (TypeError, ValueError):
        max_words = 0
    tier_level = (backlink_tier_level or "").strip()
    blog_name = (backlink_blog_name or "").strip()
    writer_name = (backlink_writer_name or "").strip()
    content_guidelines = (backlink_content_guidelines or "").strip()

    if not any((website_name, website_type, post_type != "html", title_max_characters, min_words, max_words, tier_level, blog_name, writer_name, content_guidelines)):
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
    if post_type:
        lines.append(f"- Post type: {post_type}")
    if title_max_characters:
        lines.append(f"- Title max characters: {title_max_characters}")
    if min_words:
        lines.append(f"- Content min words: {min_words}")
    if max_words:
        lines.append(f"- Content max words: {max_words}")
    if tier_level:
        lines.append(f"- Tier level: {tier_level}")
    if content_guidelines:
        lines.append(f"- Medium content rules: {content_guidelines}")

    lines.extend(
        [
            "- The article should feel appropriate for this publishing target.",
            "- Keep the tone and examples broad enough to fit the selected medium or guest-post style placement.",
            "- Do not over-promote the brand. Keep it informative and natural first.",
            "- If the tier level is Tier 1, write like a neutral publisher explaining a broader topic. Do not center the article on the brand.",
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
    if max_words:
        if min_words:
            lines.extend(
                [
                    f"- Write at least {min_words} words for this medium.",
                    f"- Treat {max_words} words as a soft guide for concision, but prioritize staying over the minimum.",
                ]
            )
        else:
            lines.extend(
                [
                    f"- Keep the full output near {max_words} words when possible.",
                    "- Use a tighter format, shorter sections, and concise delivery when a max word count is provided.",
                ]
            )
    elif min_words:
        lines.append(f"- Write at least {min_words} words for this medium.")
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
        elif not max_words:
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
                "- Use a balanced editorial style with criteria, examples, and useful context instead of promotional review language.",
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


def link_target_label(index: int, total: int) -> str:
    if total <= 1:
        return "TOP or MIDDLE body section (not the last paragraph)"
    if index == 0:
        return "TOP section (introduction or 1st H2 section)"
    if index == total - 1:
        return "END section (final H2 section)"
    return "MIDDLE section (2nd or 3rd H2 section)"


def build_links_prompt_section(
    links: list | None = None,
    *,
    heading: str = "Reference Links to Include:",
) -> str:
    if not links:
        return ""
    valid_links = [
        link
        for link in links
        if isinstance(link, dict) and link.get("text") and link.get("url")
    ]
    total_links = len(valid_links)
    links_list = "\n".join(
        (
            f"- Link {idx + 1} [Target placement: {link_target_label(idx, total_links)}] | "
            f"Type: {(link.get('type') or 'internal').strip()} | "
            f"Text: '{link.get('text', '').strip()}' -> URL: {link.get('url', '').strip()}"
        )
        for idx, link in enumerate(valid_links)
    )
    if not links_list:
        return ""
    return f"""
{heading}
{links_list}

Instructions for including links:
- Include every provided link at least once using the exact anchor text
- Use the provided text as anchor text for the link
- Format links in Markdown as [anchor text](URL)
- Follow each link's [Target placement] above so links are spread evenly across the TOP, MIDDLE, and END sections of the article
- Never cluster, group, or dump multiple anchor links together in the final paragraph or conclusion
- Place at most one link in any single paragraph so links feel natural and evenly spaced from top to bottom
- For external links, brand-name anchor text is allowed when natural.
- For internal and money site links, do not use the brand name, website name, or domain as anchor text.
- For internal and money site links, use natural descriptive anchor text that fits the sentence and page topic.
"""


def build_money_site_prompt_section(money_site_url: str = "") -> str:
    cleaned_money_site_url = (money_site_url or "").strip()
    if not cleaned_money_site_url:
        return ""
    return f"""
Money Site URL:
- {cleaned_money_site_url}

Instructions for the money site:
- Include the money site URL exactly once using a natural internal-style anchor text that fits the brand and article topic
- Format it in Markdown as [anchor text]({cleaned_money_site_url})
- Do not use generic anchor text like 'click here'
- Place it naturally where it helps the reader and matches the surrounding content
- For external links, brand-name anchor text is allowed when natural.
- For internal and money site links, do not use the brand name, website name, or domain as anchor text.
- For internal and money site links, use natural descriptive anchor text that fits the sentence and page topic.
"""


BLOG_LIST_INSTRUCTIONS = """
Article list formatting:
- You may use an ordered list for a sequence, steps, rankings, or points introduced as first, second, third, and so on. Do not force these into prose paragraphs.
- You may use an unordered bullet list for related points when their order does not matter.
- In HTML output, use <ol><li>...</li></ol> for ordered lists and <ul><li>...</li></ul> for bullet lists.
- In Markdown output, use numbered items (1., 2., 3.) for ordered lists and hyphen-prefixed items (-) for bullet lists; Python converts them to <ol> and <ul>.
- Follow the requested output format. Use lists only when they improve readability; keep ordinary explanations as paragraphs.
"""

BLOG_TABLE_INSTRUCTIONS = """
Article table formatting:
- Create a concise table whenever schedules, fixtures, dates, scores, standings, odds, comparisons, specifications, timelines, pricing, statistics, or structured multi-item facts are clearer in a table.
- Otherwise keep ordinary explanations as short paragraphs or lists.
- In Markdown output, use Markdown pipe tables with a header and separator row (`| Column | Column |` and `| --- | --- |`); the app converts them to HTML tables for viewing, editing, and exporting.
- In HTML output, use clean semantic `<table><thead><tr><th scope="col">...</th></tr></thead><tbody><tr><td>...</td></tr></tbody></table>` markup (or Markdown pipe tables, which the app converts to HTML).
- Keep cells short and factual, and use only supported facts; never invent data to fill a table.
"""
