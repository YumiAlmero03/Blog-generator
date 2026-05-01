from word_bank import build_banned_words_prompt_section

from prompts.shared import MAX_BLOG_WORDS, MIN_BLOG_WORDS, build_backlink_context_section, build_brand_context_section

def build_backlink_title_prompt(
    keyword: str,
    supporting_keyword: str = "",
    tone: str = "natural",
    count: int = 10,
    brand: str = "",
    brand_context: str = "",
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
    context_section = build_brand_context_section(brand_context)
    backlink_section = build_backlink_context_section(
        backlink_website_name=backlink_website_name,
        backlink_blog_url=backlink_blog_url,
        backlink_website_type=backlink_website_type,
        backlink_title_max_characters=backlink_title_max_characters,
        backlink_max_characters=backlink_max_characters,
        backlink_tier_level=backlink_tier_level,
        backlink_blog_name=backlink_blog_name,
        backlink_writer_name=backlink_writer_name,
        backlink_content_guidelines=backlink_content_guidelines,
    )
    banned_words_section = build_banned_words_prompt_section()
    return f"""
You are an SEO blog title generator for medium and guest-post content.

Generate exactly {count} blog title variants for this keyword/topic:
{keyword}

Brand: {brand}
{context_section}
{backlink_section}
{banned_words_section}

Rules:
- Return exactly {count} titles
- Dont seperate keyword with punctuation, use it naturally in the title
- Make them natural and human sounding
- Make them SEO-friendly
- Clear and clickable
- Make the title feel appropriate for an external publisher or guest-post style article
- Let the title style match the website type when one is provided, such as more discussion-oriented for forums or more editorial for review sites
- If a brand is provided, let the titles fit the brand naturally without forcing the brand name into every title
- If a medium publication name is provided, let some title options reflect that publisher context naturally when it improves fit
- If the medium tier is Tier 1 and a publication name is provided, make some title options feel like they belong on that blog or publication
- When both brand and blog name are provided, use them naturally and sparingly; do not stuff both into every title
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
- Keep titles around 45 to 55 characters when possible, unless the selected medium needs a shorter title
- Respect any title max character limit from the selected medium
- Use the keyword naturally
- No explanations
- Do not add any extra text before or after the JSON
- Start your response with '{{' and end with '}}'

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


def build_backlink_meta_description_prompt(
    title: str,
    keyword: str = "",
    count: int = 3,
    brand: str = "",
    brand_context: str = "",
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
    context_section = build_brand_context_section(brand_context)
    backlink_section = build_backlink_context_section(
        backlink_website_name=backlink_website_name,
        backlink_blog_url=backlink_blog_url,
        backlink_website_type=backlink_website_type,
        backlink_title_max_characters=backlink_title_max_characters,
        backlink_max_characters=backlink_max_characters,
        backlink_tier_level=backlink_tier_level,
        backlink_blog_name=backlink_blog_name,
        backlink_writer_name=backlink_writer_name,
        backlink_content_guidelines=backlink_content_guidelines,
    )
    banned_words_section = build_banned_words_prompt_section()
    return f"""
You are an SEO meta description writer for medium and guest-post content.

Generate exactly {count} compelling meta description variants for this blog post title:
"{title}"

Keyword: {keyword}
Brand: {brand}
{context_section}
{backlink_section}
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
- Let the wording match the website type naturally.
- If a brand is provided, align the wording with the brand and mention the brand only if it fits naturally.
- If a medium publication name is provided, you may reflect that publishing context naturally, but do not force it.
- If the medium tier is Tier 1 and a publication name is provided, the description may sound like it belongs on that blog or publication, but keep it natural.
- Vary the approach for each variant.
- Do not add any extra text before or after the JSON.
- Ensure each meta description is complete, natural, and within the 160–170 character limit.
- Start your response with '{{' and end with '}}'

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


def build_backlink_content_prompt(
    title: str,
    keyword: str = "",
    supporting_keyword: str = "",
    tone: str = "natural",
    money_site_url: str = "",
    brand: str = "",
    brand_context: str = "",
    backlink_website_name: str = "",
    backlink_blog_url: str = "",
    backlink_website_type: str = "",
    backlink_title_max_characters: int | str = 0,
    backlink_max_characters: int | str = 0,
    backlink_tier_level: str = "",
    backlink_blog_name: str = "",
    backlink_writer_name: str = "",
    backlink_content_guidelines: str = "",
    change_request: str = "",
) -> str:
    context_section = build_brand_context_section(brand_context)
    backlink_section = build_backlink_context_section(
        backlink_website_name=backlink_website_name,
        backlink_blog_url=backlink_blog_url,
        backlink_website_type=backlink_website_type,
        backlink_title_max_characters=backlink_title_max_characters,
        backlink_max_characters=backlink_max_characters,
        backlink_tier_level=backlink_tier_level,
        backlink_blog_name=backlink_blog_name,
        backlink_writer_name=backlink_writer_name,
        backlink_content_guidelines=backlink_content_guidelines,
    )
    banned_words_section = build_banned_words_prompt_section()
    change_request_section = ""
    cleaned_change_request = (change_request or "").strip()
    if cleaned_change_request:
        change_request_section = f"""
Minor change request from the user:
{cleaned_change_request}

Apply this request while keeping the medium content natural, complete, and aligned with all rules below.
"""
    try:
        max_characters = max(0, int(backlink_max_characters or 0))
    except (TypeError, ValueError):
        max_characters = 0

    money_site_section = ""
    cleaned_money_site_url = (money_site_url or "").strip()
    if cleaned_money_site_url:
        money_site_section = f"""
Required Brand Link:
- Use this exact HTML format once: <a href='{cleaned_money_site_url}' rel='nofollow noopener noreferrer' target='_blank'>anchor text</a>

Instructions for the required brand link:
- Include this URL exactly once in the article
- Insert the required brand link in the first paragraph only.
- The first <p> paragraph must contain the one and only link to this URL.
- Do not include this URL in any other anchor tag, plain text, citation, source list, CTA, FAQ, conclusion, or reference section
- Before returning, verify the exact URL appears one time only in the HTML
- Use natural descriptive anchor text that fits the sentence and topic
- Do not use generic anchor text like 'click here'
- Do not use the brand name, website name, or domain as anchor text
- This is the only required link in the article
- This saved brand URL is the only URL allowed in the HTML output
"""

    return f"""
You are a professional blogger and reviewer who creates SEO-friendly, human-sounding medium and guest-post content.

Write a complete blog article for this title:
"{title}"

Keyword: {keyword}
Brand: {brand}
{context_section}
{backlink_section}
{banned_words_section}

{money_site_section}
{change_request_section}

Rules:
- Write a blog article between "{MIN_BLOG_WORDS}" and "{MAX_BLOG_WORDS}" words unless a smaller max character limit is provided for the selected medium.
- Start with an engaging introduction of 60–80 words that explains the reader's problem or need.
- Make the article feel appropriate for an external publisher or guest-post style placement.
- Adapt the structure, tone, and delivery to the selected website type instead of forcing the same format for every medium.
- For Tier 1 placements, write like a blogger or publication reviewing, exploring, or discussing the selected brand in a natural editorial voice.
- Write in third person. Do not write as the brand or from the brand's point of view.
- Avoid brand-name stuffing. After the first natural mention, use varied third-person references like "this website", "this platform", "this site", "the platform", "the service", or "the website" when the meaning stays clear.
- Mention the brand name only when it is truly needed for clarity, usually no more than 2-3 times in a full article.
- Do not repeat the exact article title in the body unless absolutely necessary. However, keep the content closely aligned with the title and main topic.
- Sentences must be less than 21 words.
- Use the primary keyword naturally 2–4 times throughout the article. Include it in the introduction, and include it again in the conclusion only if it fits naturally.
- Avoid keyword stuffing and never force keywords into awkward sentences.
- Use the main keyword no more than once per paragraph.
- Do not repeat the same keyword multiple times in a single paragraph.
- Use <b> only for emphasis on important non-keyword words or phrases.
- Do not use <strong>.
- Never bold the primary keyword.
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
- If a brand is provided, reflect the brand positioning and audience naturally without sounding promotional.
- If a brand is provided, mention the brand sparingly and use third-person substitutes to avoid repetition.
- If a medium publication name is provided, treat it as the blog or publication name and mention it naturally when relevant, but do not force it repeatedly.
- If a writer name is provided, use it naturally as the article byline or writer identity when it fits.
- If the medium tier is Tier 1 and a blog name is provided, include that blog name naturally in the article at least once.
- Do not stuff the brand name, blog name, or writer name into every heading or paragraph.
- When brand, blog name, and writer name are provided, make them feel intentional and editorially natural.
- Match the writing style to the website type:
  - forum: discussion-oriented, practical, community-style
  - social_media: punchy, skimmable, conversational
  - review: editorial, evaluative, experience-driven
  - news: informative, publication-style, neutral
  - directory: concise, utility-focused
  - community: helpful, shared-insight tone
- If brand database context is provided, avoid repeating existing keyword angles and keep the content aligned with current brand pages.
- Include the required brand link once in a natural way with relevant anchor text.
- Place the required brand link inside the first paragraph, not later in the article.
- The required brand URL must appear exactly once total in the HTML output.
- Do not include the medium URL or any other URL in the output.
- If a max character limit is provided for the medium, keep the entire output within that limit and shorten the structure accordingly.
- Return only valid JSON with this format: {{"content":"<p>...</p>"}}.
- The value of "content" must contain complete, valid HTML.
- Do not add any explanation, notes, or text before or after the JSON object.
- Start the response with "{{" and end it with "}}".
- Close every HTML tag and every quotation mark properly.
- Do not truncate, abbreviate, or cut off the article.
- Check the internet when needed to verify brand, product, platform, or topic details before writing.
- Do not guess what a brand, game, or platform is.
- External links and the required brand link must use rel='nofollow noopener noreferrer' and target='_blank'.
- Use exactly one ending section only: CTA, FAQs, Conclusion, or Final Thoughts.
- Do not use these sections together in the same page.
- Choose the ending section that best matches the page type and search intent.
- If no max character limit is provided, ensure the final article is complete and within the "{MIN_BLOG_WORDS}"-"{MAX_BLOG_WORDS}" word range before finishing.
- If a max character limit is provided, prioritize staying within that character limit over the normal long-form word target.

Return valid JSON only in this format:
{{
  "content": "<h2>Your HTML content here</h2><p>...</p>",
  "word_count": 850
}}
"""
