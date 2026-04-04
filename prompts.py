def build_title_prompt(keyword: str, tone: str = "natural", count: int = 10) -> str:
    return f"""
You are an SEO blog title generator.

Generate exactly {count} blog title variants for this keyword/topic:
{keyword}

Rules:
- Return exactly {count} titles
- Make them natural and human sounding
- Make them SEO-friendly
- Clear and clickable
- Avoid robotic wording
- Avoid duplicates
- Mix styles:
  - how-to
  - guide
  - beginner-friendly
  - problem/solution
  - benefits
  - list style if appropriate
- Keep titles around 45 to 65 characters when possible
- Use the keyword naturally
- No explanations

Return valid JSON only in this format:
{{
  "titles": [
    "Title 1",
    "Title 2",
    "Title 3"
  ]
}}

Tone: {tone}
"""