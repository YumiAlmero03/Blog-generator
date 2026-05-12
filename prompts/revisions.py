def build_scoped_content_revision_prompt(
    title: str,
    existing_content: str,
    change_request: str,
    scope: str = "full",
    output_format: str = "html",
    keyword: str = "",
    brand: str = "",
    required_url: str = "",
    required_anchor_text: str = "",
) -> str:
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
        "Apply the requested minor change while preserving the existing article structure, links, headings, and intent.",
    )

    required_url_rule = ""
    if (required_url or "").strip():
        required_url_rule = f"""
- Preserve this required URL exactly once if it already exists: {required_url}
- If the required URL is missing, insert it naturally in the edited scope only.
"""

    required_anchor_rule = ""
    if (required_anchor_text or "").strip():
        required_anchor_rule = f"""
- Preserve this required anchor text exactly as provided: {required_anchor_text}
- If the anchor text is already linked to the required URL, keep that placement unless the selected scope contains it.
"""

    return f"""
You are editing an existing generated article. This is a minor revision, not a fresh generation.

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

Selected output format:
{output_format}

Selected edit target:
{cleaned_scope}

Strict edit instruction:
{selected_instruction}

User's requested change:
{change_request}

Preservation rules:
- Return the complete article, not only the changed section.
- Keep all unaffected paragraphs, headings, formatting, links, references, and examples as close to the original as possible.
- Do not create a new article outline unless the selected edit target is full.
- Do not remove useful reference links that are already present.
- Do not use placeholder links such as https://example.com/ or made-up URLs.
{required_url_rule}{required_anchor_rule}
Existing article content:
{existing_content}
""".strip()
