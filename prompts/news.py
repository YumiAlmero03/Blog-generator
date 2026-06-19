from datetime import date

from word_bank import build_banned_words_prompt_section

from prompts.shared import MAX_BLOG_WORDS, MIN_BLOG_WORDS, build_brand_context_section, build_language_instruction


def current_news_date() -> str:
    return date.today().isoformat()


def build_news_title_prompt(
    keyword: str,
    target_audience: str = "",
    target_country: str = "Worldwide",
    reference_context: str = "",
    tone: str = "news",
    count: int = 10,
    brand: str = "",
    brand_context: str = "",
    current_date: str = "",
    language: str = "English",
) -> str:
    context_section = build_brand_context_section(brand_context)
    language_section = build_language_instruction(language)
    banned_words_section = build_banned_words_prompt_section()
    reference_section = _reference_context_section(reference_context)
    current_date_text = current_date or current_news_date()
    return f"""
You are a current-events news title generator.

Today's date is {current_date_text}. Generate exactly {count} title variants for current 2026 news coverage about:
{keyword}

Target audience: {target_audience}
Target country/region: {target_country or "Worldwide"}
Brand/publication: {brand}
{context_section}
{reference_section}
{language_section}
{banned_words_section}

Rules:
- Focus on today's event or the most current 2026 development connected to the keyword.
- If reference source content is provided, use only that source content for the news angle.
- Shape the title angles for the target audience and target country/region.
- If the target country/region is Worldwide, use a global angle and avoid assuming one local audience.
- Do not create old-news angles from 2020, 2021, 2022, 2023, 2024, or 2025.
- Mention 2026 only when it helps make the title current and natural.
- Do not invent exact facts, dates, quotes, casualties, prices, scores, or official claims.
- Make each title clear, timely, human sounding, and publication-ready.
- Keep titles around 45 to 65 characters when possible.
- Vary the angles: breaking update, explainer, impact, timeline, reaction, what changed.
- Avoid duplicates and robotic wording.
- No explanations.
- Do not add any extra text before or after the JSON.
- Start your response with '{{' and end with '}}'.

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


def build_news_meta_description_prompt(
    title: str,
    keyword: str = "",
    target_audience: str = "",
    target_country: str = "Worldwide",
    reference_context: str = "",
    count: int = 5,
    brand: str = "",
    brand_context: str = "",
    current_date: str = "",
    language: str = "English",
) -> str:
    context_section = build_brand_context_section(brand_context)
    language_section = build_language_instruction(language)
    banned_words_section = build_banned_words_prompt_section()
    reference_section = _reference_context_section(reference_context)
    current_date_text = current_date or current_news_date()
    return f"""
You are an SEO meta description writer for current news articles.

Today's date is {current_date_text}. Generate exactly {count} meta description variants for this news title:
"{title}"

Keyword/event: {keyword}
Target audience: {target_audience}
Target country/region: {target_country or "Worldwide"}
Brand/publication: {brand}
{context_section}
{reference_section}
{language_section}
{banned_words_section}

Rules:
- Each meta description must be between 120 and 140 characters long.
- Count characters carefully before finishing.
- Keep the wording current to 2026 and relevant to today's event.
- If a focus keyphrase and supporting keyphrases are provided, use the focus keyphrase naturally when it fits and do not force every supporting keyphrase.
- If reference source content is provided, use only that source content for factual context.
- Write for the target audience and target country/region.
- If the target country/region is Worldwide, use globally relevant wording.
- Do not frame the story as old news from 2020, 2021, 2022, 2023, 2024, or 2025.
- Do not invent unverified figures, quotes, or named sources.
- Include the keyword naturally when it fits.
- Use active voice and a clear news value proposition.
- Vary the approach for each variant.
- Do not add any extra text before or after the JSON.
- Start your response with '{{' and end with '}}'.

Return valid JSON only in this format:
{{
  "meta_descriptions": [
    {{
      "text": "Your first meta description here",
      "character_count": 132
    }}
  ]
}}
"""


def build_news_visual_prompt(
    title: str,
    keyword: str = "",
    target_audience: str = "",
    target_country: str = "Worldwide",
    reference_context: str = "",
    count: int = 3,
    brand: str = "",
    brand_context: str = "",
    current_date: str = "",
    language: str = "English",
) -> str:
    context_section = build_brand_context_section(brand_context)
    language_section = build_language_instruction(language)
    reference_section = _reference_context_section(reference_context)
    current_date_text = current_date or current_news_date()
    return f"""
You are creating editorial image directions for a current news article.

Today's date is {current_date_text}. Generate exactly {count} visual or image description choices for:
"{title}"

Keyword/event: {keyword}
Target audience: {target_audience}
Target country/region: {target_country or "Worldwide"}
Brand/publication: {brand}
{context_section}
{reference_section}
{language_section}

Rules:
- Make each image direction feel current to 2026 and suitable for today's event coverage.
- If reference source content is provided, base image directions only on details supported by that content.
- Reflect the target country/region when relevant without stereotyping people or places.
- If the target country/region is Worldwide, suggest images that work for a global audience.
- Do not describe outdated 2020-2025 scenes.
- Keep every description factual, neutral, and editorial.
- Do not include text overlays, logos, watermarks, UI screenshots, or fabricated official documents.
- Avoid showing graphic harm, exploitative tragedy, or misleading staged evidence.
- Keep each visual idea to 1-2 sentences.
- No explanations before or after the JSON.
- Start your response with '{{' and end with '}}'.

Return valid JSON only in this format:
{{
  "visuals": ["First visual idea.", "Second visual idea.", "Third visual idea."]
}}
"""


def build_news_content_prompt(
    title: str,
    keyword: str = "",
    target_audience: str = "",
    target_country: str = "Worldwide",
    reference_context: str = "",
    tone: str = "news",
    brand: str = "",
    brand_context: str = "",
    min_words: int | str = MIN_BLOG_WORDS,
    max_words: int | str = MAX_BLOG_WORDS,
    current_date: str = "",
    language: str = "English",
) -> str:
    context_section = build_brand_context_section(brand_context)
    language_section = build_language_instruction(language)
    banned_words_section = build_banned_words_prompt_section()
    reference_section = _reference_context_section(reference_context)
    current_date_text = current_date or current_news_date()
    min_word_count = _positive_int(min_words, MIN_BLOG_WORDS)
    max_word_count = _positive_int(max_words, MAX_BLOG_WORDS)
    if max_word_count < min_word_count:
        max_word_count = min_word_count

    return f"""
You are a professional news writer creating current-events coverage.

Today's date is {current_date_text}. Write a complete current news article for this title:
"{title}"

Keyword/event: {keyword}
Target audience: {target_audience}
Target country/region: {target_country or "Worldwide"}
Brand/publication: {brand}
{context_section}
{reference_section}
{language_section}
{banned_words_section}

Rules:
- Focus on today's event or the newest 2026 development connected to the keyword.
- Treat the focus keyphrase as the main SEO keyphrase. Use it naturally in the introduction and at least one heading when it reads well.
- Use supporting keyphrases as related phrases, synonyms, or reader-intent terms. Do not repeat them mechanically or stuff keywords.
- If reference source content is provided, use only that source content for facts, names, dates, figures, claims, and timeline.
- If reference source content is provided, do not add outside facts, background, examples, or assumptions that are not supported by the supplied sources.
- If reference source content is provided but a detail is missing, say that the supplied source does not state it or omit the detail.
- Write for the target audience and target country/region.
- If the target country/region is Worldwide, explain the global relevance and avoid assuming a single country's laws, politics, currency, or institutions.
- If a specific country is selected, include the local relevance, reader impact, and country-specific context only when it is safe and natural.
- Do not make the main angle an old-news article, but older years may be used as background, timeline, or comparison when the supplied source supports them.
- Older references must clearly support the current story instead of replacing the current update.
- Do not fabricate facts, named sources, quotes, exact figures, legal outcomes, casualty counts, market prices, scores, or official statements.
- If a fact is uncertain from the keyword alone, use careful wording such as "reports indicate", "officials have not yet confirmed", or "details remain limited".
- Write at least "{min_word_count}" words. Treat "{max_word_count}" words as a soft guide, but prioritize staying over the minimum.
- Start with a concise news-style lead that explains what is happening now and why it matters.
- Use short paragraphs and active voice.
- Sentences must be less than 24 words.
- Do not include the selected title as the article title, H1, H2, H3, or opening line. The CMS already has the title separately.
- Do not use H1 headings.
- Structure the article with well-distributed Markdown H2 and H3 headings.
- Use H2 headings for main sections and H3 headings for useful subsections under those sections.
- Include sections for latest update, context, why it matters, and what to watch next, but vary the wording naturally.
- Use the focus keyphrase naturally 2-4 times when possible, and vary wording with supporting keyphrases.
- Keep the tone neutral, timely, and informative.
- If a brand is provided, align with that publication voice without forcing the brand name.
- Write the content value in Markdown source, not HTML.
- Return only valid JSON with this format: {{"content":"## Heading\\n\\nParagraph..."}}.
- Do not add any explanation, notes, or text before or after the JSON object.
- Start the response with "{{" and end it with "}}".
- Ensure the final article is complete and over "{min_word_count}" words before finishing.

Return valid JSON only in this format:
{{
  "content": "Lead paragraph without repeating the selected title.\\n\\n## Main Section\\n\\nParagraph...\\n\\n### Supporting Subsection\\n\\nParagraph...",
  "word_count": 850
}}

Tone: {tone}
"""


def build_news_tags_prompt(
    title: str,
    keyword: str = "",
    target_audience: str = "",
    target_country: str = "Worldwide",
    reference_context: str = "",
    brand: str = "",
    content: str = "",
    minimum: int = 10,
    current_date: str = "",
    language: str = "English",
) -> str:
    current_date_text = current_date or current_news_date()
    reference_section = _reference_context_section(reference_context)
    language_section = build_language_instruction(language)
    return f"""
Create clean publishing tags for this current news article.

Today's date is {current_date_text}.

Title: {title}
Keyword/event: {keyword}
Target audience: {target_audience}
Target country/region: {target_country or "Worldwide"}
Brand/publication: {brand}
{reference_section}
{language_section}

Content:
{(content or '')[:6000]}

Rules:
- Return {minimum} to 12 short tags.
- Make the tags useful for current 2026 news publishing.
- Prefer the focus keyphrase and useful supporting keyphrases when they are tag-like and natural.
- If reference source content is provided, create tags only from that source content and the generated article.
- Include audience and country/region tags when they are specific, useful, and natural.
- Use worldwide or global tags when the target country/region is Worldwide.
- Include topical, event, geography, industry, and explainer-style tags when relevant.
- Avoid duplicate tags, promotional hype, old year tags from 2020-2025, and generic filler.
- Keep tags lower case when possible.
- Do not include explanations before or after the JSON.
- Start your response with '{{' and end with '}}'.

Return JSON only in this format:
{{
  "tags": ["tag one", "tag two"]
}}
"""


def _positive_int(value: int | str, default: int | str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(1, parsed)


def _reference_context_section(reference_context: str) -> str:
    cleaned = (reference_context or "").strip()
    if not cleaned:
        return ""
    return f"""
Reference source content:
{cleaned}

Reference rules:
- Treat the reference source content above as the only factual source for this news item.
- Do not use outside knowledge or unstated assumptions.
- Do not claim that you visited or verified a link beyond the supplied extracted text.
"""
