from datetime import date


def build_keyword_suggestions_prompt(
    topic: str,
    autocomplete_keywords: list[str],
    target_country: str = "Worldwide",
    count: int = 30,
) -> str:
    autocomplete_section = "\n".join(f"- {item}" for item in autocomplete_keywords[:80]) or "- No live autocomplete suggestions were available."
    return f"""
You are an SEO keyword research assistant.

Today's date is {date.today().isoformat()}.

Seed topic:
{topic}

Target country or region: {target_country or "Worldwide"}

Live autocomplete/query suggestions gathered by the app:
{autocomplete_section}

Rules:
- Return exactly {count} useful keyword ideas when possible.
- Include a mix of short-tail, long-tail, question, comparison, informational, commercial, and news-style keywords.
- Use the live autocomplete suggestions as primary inspiration when they are available.
- Estimate monthly searches as a range, not an exact claim.
- Estimate keyword difficulty using both a label and a 0-100 score.
- Difficulty labels must be "easy", "medium", or "hard".
- Search intent must be one of "informational", "commercial", "transactional", "navigational", or "news".
- Do not include prohibited or unsafe instructions.
- Do not invent that you used Google Keyword Planner, Ahrefs, Semrush, or Search Console.
- Make clear through the data that search volume and difficulty are estimates.
- Return valid JSON only. No text before or after the JSON.

Return this JSON shape:
{{
  "keywords": [
    {{
      "keyword": "example keyword",
      "intent": "informational",
      "difficulty": "easy",
      "difficulty_score": 22,
      "estimated_monthly_searches": "100-1K",
      "content_angle": "Short article angle or page idea",
      "notes": "Why this keyword is useful"
    }}
  ]
}}
"""
