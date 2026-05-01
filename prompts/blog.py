from word_bank import build_banned_words_prompt_section

from prompts.shared import MAX_BLOG_WORDS, MIN_BLOG_WORDS, build_brand_context_section

def build_title_prompt(
    keyword: str,
    supporting_keyword: str = "",
    tone: str = "natural",
    count: int = 10,
    brand: str = "",
    brand_context: str = "",
) -> str:
    context_section = build_brand_context_section(brand_context)
    banned_words_section = build_banned_words_prompt_section()
    return f"""
You are an SEO blog title generator.

Generate exactly {count} blog title variants for this keyword/topic:
{keyword}

Supporting ideas: {supporting_keyword}
Brand: {brand}
{context_section}
{banned_words_section}

Rules:
- Return exactly {count} titles
- Dont seperate keyword with punctuation, use it naturally in the title
- Make them natural and human sounding
- Make them SEO-friendly
- Clear and clickable
- If a brand is provided, let the titles fit the brand naturally without forcing the brand name into every title
- Avoid repeating titles or keyword angles that were already used for this brand when the context shows previous usage
- Avoid robotic wording
- Avoid duplicates
- Mix styles:
  - how-to
  - guide
  - beginner-friendly
  - problem/solution
  - benefits
  - list style if appropriate
- Keep titles around 45 to 55 characters when possible
- Use the keyword naturally
- No explanations
- Do not add any extra text before or after the JSON
- Start your response with '{' and end with '}'

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


def build_meta_description_prompt(
    title: str,
    keyword: str = "",
    count: int = 3,
    brand: str = "",
    brand_context: str = "",
) -> str:
    context_section = build_brand_context_section(brand_context)
    banned_words_section = build_banned_words_prompt_section()
    return f"""
You are an SEO meta description writer.

Generate exactly {count} compelling meta description variants for this blog post title:
"{title}"

Keyword: {keyword}
Brand: {brand}
{context_section}
{banned_words_section}

Rules:
- Each meta description must be between 160 and 170 characters long.
- Count characters carefully before finishing.
- Include the main keyword naturally.
- Make it compelling and encourage clicks.
- Avoid keyword stuffing.
- Use active voice.
- Include a call-to-action or value proposition when it fits naturally.
- Make it sound human and natural.
- If a brand is provided, align the wording with the brand and mention the brand only if it fits naturally.
- Vary the approach for each variant.
- Do not add any extra text before or after the JSON.
- Ensure each meta description is complete, natural, and within the 160–170 character limit.
- Start your response with '{' and end with '}'

Return valid JSON only in this format:
{{
  "meta_descriptions": [
    {{
      "text": "Your first meta description here",
      "character_count": 155
    }},
    {{
      "text": "Your second meta description here",
      "character_count": 158
    }}
  ]
}}
"""


def build_content_prompt(
    title: str,
    keyword: str = "",
    supporting_keyword: str = "",
    tone: str = "natural",
    links: list = None,
    money_site_url: str = "",
    brand: str = "",
    brand_context: str = "",
    change_request: str = "",
) -> str:
    links_section = ""
    context_section = build_brand_context_section(brand_context)
    banned_words_section = build_banned_words_prompt_section()
    change_request_section = ""
    cleaned_change_request = (change_request or "").strip()
    if cleaned_change_request:
        change_request_section = f"""
Minor change request from the user:
{cleaned_change_request}

Apply this request while keeping the article complete, SEO-friendly, and aligned with all rules below.
"""
    if links and len(links) > 0:
        links_list = "\n".join([
            f"- Type: {link.get('type', 'internal').strip()} | Text: '{link.get('text', '').strip()}' -> URL: {link.get('url', '').strip()}"
            for link in links
            if link and link.get('text') and link.get('url')
        ])
        if links_list:
            links_section = f"""
Reference Links to Include:
{links_list}

Instructions for including links:
- Include every provided link at least once using the exact anchor text
- Use the provided text as anchor text for the link
- For internal links, format links as <a href='URL'>anchor text</a>
- For external links, format links as <a href='URL' rel='nofollow noopener noreferrer' target='_blank'>anchor text</a>
- Use single quotes in href attributes so the JSON stays valid
- Add links naturally; do not force them if they do not fit
- if they dont fit naturally, add them at the end of the article in a 'References:' with proper formatting or check this link or this one (link) for more info. make it natural and human sounding
- For external links, brand-name anchor text is allowed when natural.
- For internal and money site links, do not use the brand name, website name, or domain as anchor text.
- For internal and money site links, use natural descriptive anchor text that fits the sentence and page topic.
"""

    money_site_section = ""
    cleaned_money_site_url = (money_site_url or "").strip()
    if cleaned_money_site_url:
        money_site_section = f"""
Money Site URL:
- {cleaned_money_site_url}

Instructions for the money site:
- Include the money site URL exactly once using a natural internal-style anchor text that fits the brand and article topic
- Format it as <a href='{cleaned_money_site_url}' rel='nofollow noopener noreferrer' target='_blank'>anchor text</a>
- Do not use generic anchor text like 'click here'
- Place it naturally where it helps the reader and matches the surrounding content
- For external links, brand-name anchor text is allowed when natural.
- For internal and money site links, do not use the brand name, website name, or domain as anchor text.
- For internal and money site links, use natural descriptive anchor text that fits the sentence and page topic.
"""

    return f"""
You are a professional blog writer who creates SEO-friendly, human-sounding content.

Write a complete blog article for this title:
"{title}"

Keyword: {keyword}
Supporting keyword: {supporting_keyword}
Brand: {brand}
{context_section}
{banned_words_section}

{links_section}
{money_site_section}
{change_request_section}

Rules:
- Write a blog article between "{MIN_BLOG_WORDS}" and "{MAX_BLOG_WORDS}" words.
- Start with an engaging introduction of 60–80 words that explains the reader’s problem or need.
- Do not repeat the exact article title in the body unless absolutely necessary. However, keep the content closely aligned with the title and main topic.
- Sentences must be less than 21 words.
- Use the primary keyword naturally 2–4 times throughout the article. Include it in the introduction, and include it again in the conclusion only if it fits naturally.
- Include the supporting keyword naturally where appropriate.
- Avoid keyword stuffing and never force keywords into awkward sentences.
- Use the main keyword no more than once per paragraph.
- Do not repeat the same keyword multiple times in a single paragraph.
- Use <b> only for emphasis on important non-keyword words or phrases.
- Do not use <strong>.
- Never bold the primary keyword or supporting keywords.
- Do not wrap keywords in <b> or <strong> tags.
- Use a natural, human, conversational tone.
- Write in active voice with short, clear sentences.
- Write for readability using short paragraphs.
- Add detailed explanations, useful examples, and practical context in each section to support the word count naturally.
- Structure the article in this order: introduction, 3–4 main sections with subheadings, then exactly one ending section that best fits the page intent.
- Use HTML only, not Markdown.
- Use <h2> for main sections and <h3> for subsections.
- Use <p> for paragraphs.
- Use <ul><li> for bullet lists where helpful.
- If a brand is provided, reflect the brand voice, positioning, and audience naturally throughout the article.
- If brand database context is provided, avoid repeating existing keyword angles and keep the content aligned with current brand pages.
- You may include relevant reference links only if they fit naturally in the article.
- When adding links, use HTML anchor tags with single quotes, like <a href='URL'>anchor text</a>.
- Return only valid JSON with this format: {{"content":"<p>...</p>"}}.
- The value of "content" must contain complete, valid HTML.
- Do not add any explanation, notes, or text before or after the JSON object.
- Start the response with "{" and end it with "}".
- Close every HTML tag and every quotation mark properly.
- Do not truncate, abbreviate, or cut off the article.
- Check the internet when needed to verify brand, product, platform, or topic details before writing.
- If reference links are provided, review them first and use them as the primary context source when they are relevant.
- Do not guess what a brand, game, or platform is. If the provided links clarify the topic, use that context to keep descriptions accurate.
- Only include a link if it fits naturally in the article and is relevant to the section.
- If a provided link refers to a specific brand or page, make sure the surrounding content matches that page correctly.
- If a money site URL is provided, include it once in a natural way with relevant anchor text.
- External links and the money site URL must use rel='nofollow noopener noreferrer' and target='_blank'.
- Internal links must not use nofollow unless explicitly requested.
- Use exactly one ending section only: CTA, FAQs, Conclusion, or Final Thoughts.
- Do not use these sections together in the same page.
- Choose the ending section that best matches the page type and search intent.
- Ensure the final article is complete and within the "{MIN_BLOG_WORDS}"-"{MAX_BLOG_WORDS}" word range before finishing.

Return valid JSON only in this format:
{{
  "content": "<h2>Your HTML content here</h2><p>...</p>",
  "word_count": 850
}}
"""

