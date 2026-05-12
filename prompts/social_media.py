from prompts.shared import build_brand_context_section
from word_bank import build_banned_words_prompt_section


def build_social_media_post_prompt(
    focus_word: str,
    brand_name: str,
    social_type: str,
    brand_context: str = "",
    reference_link: str = "",
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
    return f"""
You are a social media content assistant.

Create one short random social media post for this profile.

Focus word: {focus_word}
Brand: {brand_name}
Social media type: {social_type}
{context_section}
{reference_link_section}
{banned_words_section}

Rules:
- Return valid JSON only.
- The post_content must be 220 characters or fewer.
- Do not create slot, casino, gambling, betting, jackpot, wager, poker, roulette, sportsbook, or lottery related content.
- Do not use gambling-related hashtags or image ideas.
- If the focus word or brand context suggests gambling, rewrite the post toward a neutral lifestyle, entertainment, product, or community angle without gambling terms.
- Make the post natural, concise, and platform-appropriate.
- Use the focus word naturally.
- Do not add URLs unless the user provided a reference link or brand context URL.
- If a reference link is provided, use it as context and include it only when it improves the post and fits the 220-character limit.
- Image description should describe one useful visual for the post.
- Tags/hashtags should be 3-8 short items.
- Hashtags should include # when appropriate.
- No explanations before or after the JSON.
- Start with "{{" and end with "}}".

Return valid JSON only in this format:
{{
  "post_content": "Short social post under 220 characters.",
  "image_description": "A clear image idea.",
  "tags": ["#tag1", "#tag2", "#tag3"]
}}
"""
