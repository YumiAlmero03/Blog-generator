from prompts.shared import build_brand_context_section
from word_bank import build_banned_words_prompt_section


def build_social_media_post_prompt(
    focus_word: str,
    brand_name: str,
    social_type: str,
    brand_context: str = "",
    reference_link: str = "",
    research_context: str = "",
    max_characters: int = 1000,
) -> str:
    context_section = build_brand_context_section(brand_context)
    banned_words_section = build_banned_words_prompt_section()
    cleaned_reference_link = (reference_link or "").strip()
    reference_link_section = ""
    if cleaned_reference_link:
        reference_link_section = f"""
Reference link:
{cleaned_reference_link}

Use this reference link as source context for the post. Include the URL in post_content only if it fits naturally for the platform and stays within the character limit.
"""
    research_section = ""
    if (research_context or "").strip():
        research_section = f"""
Web research context:
{research_context}

Use this as supporting context. Do not claim details that are not supported by the web research, reference link, or brand context.
"""
    focus_section = f"Optional focus word or angle: {focus_word}" if (focus_word or "").strip() else "Optional focus word or angle: auto-generate a random topic."
    return f"""
You are a neutral content assistant.

Create one neutral random blog-style or platform-appropriate post for this medium.

{focus_section}
Brand: {brand_name or "None"}
Medium: {social_type}
{context_section}
{reference_link_section}
{research_section}
{banned_words_section}

Rules:
- Return valid JSON only.
- The post_content must be {max_characters} characters or fewer.
- Choose one random topic category: technical, sports, video games, or online games.
- Online games must mean non-gambling games only.
- Do not create slot, casino, gambling, betting, jackpot, wager, poker, roulette, sportsbook, or lottery related content.
- Do not use gambling-related hashtags or image ideas.
- If the focus word or brand context suggests gambling, rewrite the post toward a neutral lifestyle, entertainment, product, or community angle without gambling terms.
- If no brand is provided, do not invent one.
- Make the post natural, concise, neutral, and platform-appropriate for the selected medium.
- If a focus word is provided, use it naturally. If it is blank, invent a random angle from the allowed topic categories.
- Do not add URLs unless the user provided a reference link or brand context URL.
- If a reference link is provided, use it as context and include it only when it improves the post and fits the {max_characters}-character limit.
- Image description should describe one useful visual for the post.
- Tags/hashtags should be 3-8 short items.
- Hashtags should include # when appropriate.
- No explanations before or after the JSON.
- Start with "{{" and end with "}}".

Return valid JSON only in this format:
{{
  "post_content": "Short social post under the selected medium character limit.",
  "image_description": "A clear image idea.",
  "tags": ["#tag1", "#tag2", "#tag3"]
}}
"""
