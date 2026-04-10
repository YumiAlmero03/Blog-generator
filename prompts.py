# Pro
def build_brand_context_section(brand_context: str = "") -> str:
    cleaned = (brand_context or "").strip()
    if not cleaned:
        return ""
    return f"""
Known brand database context:
{cleaned}
"""


def build_title_prompt(
    keyword: str,
    supporting_keyword: str = "",
    tone: str = "natural",
    count: int = 10,
    brand: str = "",
    brand_context: str = "",
) -> str:
    context_section = build_brand_context_section(brand_context)
    return f"""
You are an SEO blog title generator.

Generate exactly {count} blog title variants for this keyword/topic:
{keyword}

Supporting ideas: {supporting_keyword}
Brand: {brand}
{context_section}

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
    return f"""
You are an SEO meta description writer.

Generate exactly {count} compelling meta description variants for this blog post title:
"{title}"

Keyword: {keyword}
Brand: {brand}
{context_section}

Rules:
- Each meta description must be 110-145 characters exactly
- Include the main keyword naturally
- Be compelling and encourage clicks
- Avoid keyword stuffing
- Use active voice
- Include a call-to-action or value proposition
- Make it human and natural sounding
- If a brand is provided, align the wording to the brand and include the brand only when it fits naturally
- Vary the approach for each variant
- Do not add any extra text before or after the JSON
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

# Prompts for content generation with optional links section
def build_content_prompt(
    title: str,
    keyword: str = "",
    supporting_keyword: str = "",
    tone: str = "natural",
    links: list = None,
    brand: str = "",
    brand_context: str = "",
) -> str:
    links_section = ""
    context_section = build_brand_context_section(brand_context)
    if links and len(links) > 0:
        links_list = "\n".join([
            f"- Text: '{link.get('text', '').strip()}' -> URL: {link.get('url', '').strip()}"
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
- Format links as <a href='URL'>anchor text</a>
- Use single quotes in href attributes so the JSON stays valid
- Add links naturally; do not force them if they do not fit
- if they dont fit naturally, add them at the end of the article in a 'References:' with proper formatting or check this link or this one (link) for more info. make it natural and human sounding
"""

    return f"""
You are a professional blog writer who creates SEO-friendly, human-sounding content.

Write a complete blog article for this title:
"{title}"

Keyword: {keyword}
Supporting keyword: {supporting_keyword}
Brand: {brand}
{context_section}

{links_section}

Rules:
- Write a blog article between 1000 and 1200 words.
- Start with an engaging introduction of 60–80 words that explains the reader’s problem or need.
- Do not repeat the exact article title in the body unless absolutely necessary. However, keep the content closely aligned with the title and main topic.
- Use the primary keyword naturally 2–4 times throughout the article. Include it in the introduction, and include it again in the conclusion only if it fits naturally.
- Include the supporting keyword naturally where appropriate.
- Avoid keyword stuffing and never force keywords into awkward sentences.
- Use a natural, human, conversational tone.
- Write in active voice with short, clear sentences.
- Write for readability using short paragraphs.
- Add detailed explanations, useful examples, and practical context in each section to support the word count naturally.
- Structure the article in this order: introduction, 3–4 main sections with subheadings, conclusion, short call-to-action.
- Use HTML only, not Markdown.
- Use <h2> for main sections and <h3> for subsections.
- Use <p> for paragraphs.
- Use <ul><li> for bullet lists where helpful.
- Use <b> only for emphasis on important non-keyword words or phrases.
- Do not use <strong>.
- Do not bold the primary keyword or supporting keyword.
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
- Ensure the final article is complete and within the 1000–1200 word range before finishing.

Return valid JSON only in this format:
{{
  "content": "<h2>Your HTML content here</h2><p>...</p>",
  "word_count": 850
}}
"""


def build_page_prompt(
    keyword: str,
    supporting_keywords: str = "",
    page_type: str = "",
    expectations: str = "",
    brand: str = "",
    brand_context: str = "",
) -> str:
    context_section = build_brand_context_section(brand_context)
    return f"""
You are an expert SEO landing page writer for WordPress.

Create a complete WordPress page for this primary keyword:
{keyword}

Supporting keywords:
{supporting_keywords}

Brand:
{brand}
{context_section}

Page type:
{page_type}

What to expect in the page:
{expectations}

Rules:
- Keep the main keyword exactly as provided. Do not split, rearrange, or alter it. Use it naturally in the title and content.
- Write for real users, not just search engines.
- Use the main keyword naturally 3–5 times in total: once in the title, once in the introduction, once in a subheading, and once in the conclusion.
- Include supporting keywords naturally where they fit.
- Avoid keyword stuffing and unnatural phrasing.

- Title should be catchy, include the main keyword naturally, and be 45–55 characters when possible.
- Introduction should be 60–80 words, engaging, and include the main keyword naturally once.
- Content should be between 900 and 1000 words, structured with clear sections and subheadings.
- Paragraphs should be short and easy to read.

- If a brand is provided, match the brand’s voice, positioning, and audience naturally.
- When brand database context is provided, avoid duplicating existing pages too closely.

- Return clean HTML that can be copy-pasted into the WordPress Gutenberg editor.
- Use only simple HTML tags: <h1>, <h2>, <h3>, <p>, <ul>, <li>, <strong>, <em>, <blockquote>.
- Do not use <b> tags.
- Use <strong> only for emphasis on non-keyword phrases.
- Never apply <strong> or <em> to the main or supporting keywords.

- Include exactly one <h1> at the top.
- Structure the page clearly for readability and conversions.
- Adapt the structure based on the page type naturally.
- Keep paragraphs short and easy to read.
- Use bullet points and subheadings to break up content.

- Include at least 5 sections after the introduction with relevant subheadings.
- Follow Yoast SEO guidelines for keyword usage and structure.
- Use the "What to expect in the page" notes as guidance for sections, tone, and key details.

- If helpful, insert image placeholders using:
  [IMAGE: alt text describing the image here]
- Add no more than 3 image placeholders.

- Do not use markdown.
- Do not add explanations before or after the JSON.
- Ensure the content is complete and exceeds 900 words.
- Start your response with '{{' and end with '}}'

Return valid JSON only in this format:
{{
  "title": "Page Title",
  "meta_description": "SEO meta description here",
  "content": "<h1>Page Title</h1><p>...</p>",
  "image_count": 2
}}
"""


def build_simple_page_prompt(
    page_title: str,
    page_type: str = "",
    brand: str = "",
    expectations: str = "",
    brand_context: str = "",
) -> str:
    context_section = build_brand_context_section(brand_context)
    return f"""
You are an expert WordPress page writer for simple website pages.

Create a complete simple WordPress page for:
{page_title}

Page type:
{page_type}

Brand:
{brand}
{context_section}

What to include:
{expectations}

Rules:
- This generator is for simple pages such as Privacy Policy, Terms and Conditions, Disclaimer, About Us, Contact Us, Refund Policy, Shipping Policy, Cookie Policy, or similar low-complexity pages
- Write clear, structured HTML that can be pasted directly into the WordPress Gutenberg editor
- Use only simple HTML tags: <h1>, <h2>, <h3>, <p>, <ul>, <li>, <strong>, <em>, <blockquote>
- Include exactly one <h1>
- Keep the tone clear, professional, and easy to understand
- If a brand is provided, use the brand name naturally where relevant
- If brand context is provided, align the page with that brand only when it fits naturally
- Adapt the structure to the page type
- Do not add image placeholders
- Do not use markdown
- Ensure the content is complete and exceeds 900 words.
- Do not add explanations before or after the JSON
- Start your response with '{{' and end with '}}'

Return valid JSON only in this format:
{{
  "title": "Page Title",
  "content": "<h1>Page Title</h1><p>...</p>"
}}
"""
