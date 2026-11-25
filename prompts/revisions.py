from app.services.sportsbook_odds_extractor import is_sportsbook_odds_context
from prompts.shared import BLOG_LIST_INSTRUCTIONS, BLOG_TABLE_INSTRUCTIONS, build_language_instruction, link_target_label


def build_scoped_content_revision_prompt(
    title: str,
    existing_content: str,
    change_request: str,
    scope: str = "full",
    output_format: str = "html",
    keyword: str = "",
    brand: str = "",
    links: list | None = None,
    required_url: str = "",
    required_anchor_text: str = "",
    language: str = "English",
    reference_context: str = "",
) -> str:
    language_section = build_language_instruction(language)
    cleaned_scope = (scope or "full").strip().lower()
    scope_instructions = {
        "intro": (
            "Change only the introduction or first paragraph. Keep every body section, ending, "
            "heading, link, and factual point outside the introduction as close to the original as possible."
        ),
        "section": (
            "Change only the weakest or most relevant body section needed for the request. Keep the title, "
            "introduction, ending, existing links, and unrelated sections as close to the original as possible."
        ),
        "conclusion": (
            "Change only the ending, conclusion, or final paragraph. Do not rewrite the introduction or body. "
            "Do not move, add, or repeat required links unless the requested ending change absolutely requires it."
        ),
        "tags": (
            "Make only small wording adjustments that improve the article's tag angle. Keep the structure, "
            "main points, ending, and existing links as close to the original as possible."
        ),
        "meta": (
            "Make only small wording adjustments that better support the selected meta angle. Keep the structure, "
            "main points, ending, and existing links as close to the original as possible."
        ),
    }
    selected_instruction = scope_instructions.get(
        cleaned_scope,
        "Apply the user's requested change directly while preserving the overall article topic, headings, and intent.",
    )

    links_section = ""
    if links:
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
                f"Anchor text: '{link.get('text', '').strip()}' -> URL: {link.get('url', '').strip()}"
            )
            for idx, link in enumerate(valid_links)
        )
        if links_list:
            links_section = f"""
Provided anchor links for this article:
{links_list}
"""

    required_url_rule = ""
    if (required_url or "").strip():
        required_url_rule = f"""
- Ensure this required URL appears exactly once in the article: {required_url}
"""

    required_anchor_rule = ""
    if (required_anchor_text or "").strip():
        required_anchor_rule = f"""
- Preserve this required anchor text exactly as provided: {required_anchor_text}
"""

    reference_section = ""
    cleaned_reference = (reference_context or "").strip()
    if cleaned_reference:
        odds_revision_note = ""
        if is_sportsbook_odds_context(cleaned_reference):
            odds_revision_note = (
                "\n- Keep all displayed odds, handicap/goal lines, betting percentages, and market-based predictions "
                "strictly accurate to the supplied sportsbook markets above (present odds in clean tables when requested or helpful)."
            )
        reference_section = f"""
Reference source context (use only verified facts from here if adding requested details):
{cleaned_reference[:16000]}{odds_revision_note}
"""

    return f"""
You are editing an existing generated article. This is a targeted revision based on the user's instructions.

Return valid JSON only:
{{
  "content": "the complete updated article"
}}

Article title:
{title}

Primary keyword/context:
{keyword}

Brand/context:
{brand}

{language_section}
{reference_section}
{links_section}
{BLOG_LIST_INSTRUCTIONS}
{BLOG_TABLE_INSTRUCTIONS}
Selected output format:
{output_format}

Selected edit target:
{cleaned_scope}

Strict edit instruction:
{selected_instruction}

User's requested change (HIGHEST PRIORITY - you must fulfill this request):
{change_request}

Link placement & preservation rules:
- The "User's requested change" above overrides default preservation rules whenever they conflict.
- If the user asks to distribute, spread out, or move anchor links (for example across the top, middle, and end of the content), you MUST remove the clustered links from the last paragraph/ending and weave them naturally across early (introduction or first H2 section), middle (body H2 sections), and late sections of the article, with at most one link per paragraph.
- Even when not explicitly asked, never leave multiple anchor links bunched together in the final paragraph if they can be distributed across top, middle, and end sections.
- Return the complete article in {output_format} format, not only the changed section.
- Keep paragraphs, headings, formatting, and examples that are unrelated to the user's requested change intact.
- Do not remove provided or existing reference links; keep each link's exact URL and anchor text intact when relocating it.
- Do not use placeholder links such as https://example.com/ or made-up URLs.
{required_url_rule}{required_anchor_rule}
Existing article content:
{existing_content}

FINAL REMINDER BEFORE RETURNING JSON:
- Apply this requested change now: {change_request}
- If the request asks to distribute or spread out anchor links across top, middle, and end sections, move the links out of the final paragraph so they appear in separate TOP, MIDDLE, and END paragraphs across the article.
""".strip()
