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
    backlink_post_type: str = "html",
    backlink_title_max_characters: int | str = 0,
    backlink_min_words: int | str = 0,
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
        backlink_post_type=backlink_post_type,
        backlink_title_max_characters=backlink_title_max_characters,
        backlink_min_words=backlink_min_words,
        backlink_max_characters=backlink_max_characters,
        backlink_tier_level=backlink_tier_level,
        backlink_blog_name=backlink_blog_name,
        backlink_writer_name=backlink_writer_name,
        backlink_content_guidelines=backlink_content_guidelines,
    )
    banned_words_section = build_banned_words_prompt_section()
    return f"""
You are an informational blog title generator for medium and guest-post content.

Generate exactly {count} blog title variants for this keyword/topic:
{keyword}

Brand: {brand}
{context_section}
{backlink_section}
{banned_words_section}

Rules:
- Return exactly {count} titles
- Create informational titles only.
- Never mention the brand name in any title.
- Do not make titles promotional, sales-focused, or casino-focused.
- Prefer topics about gaming platforms, games, player experience, software, apps, digital tools, online safety, or technology.
- If the keyword is casino-related, reframe the title toward broader gaming platforms, games, entertainment technology, UX, security, or responsible digital play.
- Dont separate keyword with punctuation; use it naturally only when it fits an informational title.
- Make them natural and human sounding
- Make them SEO-friendly
- Clear and clickable
- Make the title feel appropriate for an external publisher or guest-post style article
- Let the title style match the website type when one is provided, such as more discussion-oriented for forums or more editorial for review sites
- Use the brand context only to understand the audience. Do not include the brand name in titles.
- If a medium publication name is provided, let some title options reflect that publisher context naturally when it improves fit
- If the medium tier is Tier 1 and a publication name is provided, make some title options feel like they belong on that blog or publication
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
- Use the keyword naturally when it fits, but do not force exact-match phrasing.
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
    backlink_post_type: str = "html",
    backlink_title_max_characters: int | str = 0,
    backlink_min_words: int | str = 0,
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
        backlink_post_type=backlink_post_type,
        backlink_title_max_characters=backlink_title_max_characters,
        backlink_min_words=backlink_min_words,
        backlink_max_characters=backlink_max_characters,
        backlink_tier_level=backlink_tier_level,
        backlink_blog_name=backlink_blog_name,
        backlink_writer_name=backlink_writer_name,
        backlink_content_guidelines=backlink_content_guidelines,
    )
    banned_words_section = build_banned_words_prompt_section()
    return f"""
You are an informational SEO meta description writer for medium and guest-post content.

Generate exactly {count} compelling meta description variants for this blog post title:
"{title}"

Keyword: {keyword}
Brand: {brand}
{context_section}
{backlink_section}
{banned_words_section}

Rules:
- Each meta description must be between 120 and 140 characters long.
- Count characters carefully before finishing.
- Keep the description informational, neutral, and helpful.
- Include the main keyword only if it fits naturally.
- Do not mention the brand name unless the title itself makes that unavoidable.
- Do not make it promotional, sales-focused, or casino-focused.
- Prefer a gaming platform, games, digital tools, online safety, user experience, or technology angle.
- If the keyword is casino-related, reframe the wording toward broader gaming platforms, games, entertainment technology, UX, security, or responsible digital play.
- Avoid keyword stuffing.
- Use active voice.
- Make it sound human and natural.
- Let the wording match the website type naturally.
- If a brand is provided, use it only as audience context.
- If a medium publication name is provided, you may reflect that publishing context naturally, but do not force it.
- If the medium tier is Tier 1 and a publication name is provided, the description may sound like it belongs on that blog or publication, but keep it natural.
- Vary the approach for each variant.
- Do not add any extra text before or after the JSON.
- Ensure each meta description is complete, natural, and within the 120-140 character limit.
- Start your response with '{{' and end with '}}'

Return valid JSON only in this format:
{{
  "meta_descriptions": [
    {{
      "text": "Your first meta description here",
      "character_count": 132
    }},
    {{
      "text": "Your second meta description here",
      "character_count": 136
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
    backlink_post_type: str = "html",
    backlink_title_max_characters: int | str = 0,
    backlink_min_words: int | str = 0,
    backlink_max_characters: int | str = 0,
    backlink_tier_level: str = "",
    backlink_blog_name: str = "",
    backlink_writer_name: str = "",
    backlink_content_guidelines: str = "",
    suggested_content: str = "",
    change_request: str = "",
) -> str:
    context_section = build_brand_context_section(brand_context)
    backlink_section = build_backlink_context_section(
        backlink_website_name=backlink_website_name,
        backlink_blog_url=backlink_blog_url,
        backlink_website_type=backlink_website_type,
        backlink_post_type=backlink_post_type,
        backlink_title_max_characters=backlink_title_max_characters,
        backlink_min_words=backlink_min_words,
        backlink_max_characters=backlink_max_characters,
        backlink_tier_level=backlink_tier_level,
        backlink_blog_name=backlink_blog_name,
        backlink_writer_name=backlink_writer_name,
        backlink_content_guidelines=backlink_content_guidelines,
    )
    banned_words_section = build_banned_words_prompt_section()
    suggested_content_section = ""
    cleaned_suggested_content = (suggested_content or "").strip()
    if cleaned_suggested_content:
        suggested_content_section = f"""
Suggested content, angles, facts, or talking points from the user:
{cleaned_suggested_content}

Use these suggestions as helpful source direction when they fit the title, medium, brand context, and rules. Keep the final writing original, natural, and not copied verbatim unless the user clearly supplied exact wording to preserve.
"""
    change_request_section = ""
    cleaned_change_request = (change_request or "").strip()
    if cleaned_change_request:
        change_request_section = f"""
Minor change request from the user:
{cleaned_change_request}

Apply this request while keeping the medium content natural, complete, and aligned with all rules below.
"""
    try:
        min_words = max(0, int(backlink_min_words or 0))
    except (TypeError, ValueError):
        min_words = 0
    try:
        max_words = max(0, int(backlink_max_characters or 0))
    except (TypeError, ValueError):
        max_words = 0
    if min_words and not max_words:
        min_word_rule = f'- Write at least "{min_words}" words for this medium.'
        completion_word_rule = f'- If no max word count is provided, ensure the final article is complete and at least "{min_words}" words before finishing.'
    elif min_words and max_words:
        min_word_rule = f'- Write at least "{min_words}" words for this medium. Treat "{max_words}" words as a soft guide, but prioritize staying over the minimum.'
        completion_word_rule = f'- Ensure the final article is complete and at least "{min_words}" words before finishing.'
    elif max_words:
        min_word_rule = f'- Keep the article concise for this medium. If possible, stay near "{max_words}" words without cutting useful context.'
        completion_word_rule = f'- Ensure the final article is complete before finishing.'
    else:
        min_word_rule = f'- Write a blog article of at least "{MIN_BLOG_WORDS}" words. Treat "{MAX_BLOG_WORDS}" words as a soft guide, but prioritize staying over the minimum.'
        completion_word_rule = f'- Ensure the final article is complete and at least "{MIN_BLOG_WORDS}" words before finishing.'
    medium_name_target = f"{backlink_website_name or ''} {backlink_blog_name or ''} {backlink_website_type or ''}".lower()
    platform_rules = ""
    if "twitter" in medium_name_target or "x.com" in medium_name_target or " twitter" in f" {medium_name_target}":
        platform_rules = """
Twitter/X-specific rules:
- Use plain text.
- Keep the post punchy and short.
- Do not write a long article structure.
- Use no more than 2 hashtags if hashtags fit naturally.
"""
    elif "google_sites" in medium_name_target or "google sites" in medium_name_target:
        platform_rules = """
Google Sites-specific rules:
- Use a shorter title than a normal blog title.
- Use simple sections and compact paragraphs.
- Avoid overly long headings or dense HTML.
"""
    elif "pinterest" in medium_name_target:
        platform_rules = """
Pinterest-specific rules:
- Write visually descriptive, concise copy.
- Make it useful as a pin description.
- Keep tags concise and topical.
"""
    elif "forum" in medium_name_target:
        platform_rules = """
Forum-specific rules:
- Sound like a helpful community post, not a polished advertisement.
- Keep the structure practical and discussion-friendly.
- Avoid corporate phrasing.
"""
    cleaned_money_site_url = (money_site_url or "").strip()
    required_url = cleaned_money_site_url or "REQUIRED_URL"
    money_site_section = ""
    if cleaned_money_site_url:
        money_site_section = f"""

Required brand URL:
{cleaned_money_site_url}

Required brand link rules:
- Insert this exact URL once anywhere in the article.
- Use natural descriptive anchor text that fits the article topic.
- Do not use the brand name, website name, or domain as anchor text.
- Do not include any other URL in the generated content.
- Before returning, verify this URL appears exactly one time in the content value.
"""
    post_type = (backlink_post_type or "html").strip().lower()
    if post_type not in {"html", "markdown", "gutenberg", "text"}:
        post_type = "html"
    if post_type == "markdown":
        format_rules = f"""
- Write the content value in Markdown, not HTML.
- Use Markdown headings like ## and ###, Markdown lists, and compact paragraphs.
- Do not put every sentence on its own line. Keep related sentences together in the same paragraph.
- Use only one blank line between Markdown blocks.
- Use this Markdown link format once anywhere in the article when a brand URL is provided: [anchor text]({required_url}).
- Do not use HTML tags in the content value.
- Use Markdown bold only for important non-keyword words when emphasis helps.
- Never bold the primary keyword.
"""
        return_example = '"content": "Intro paragraph with [anchor text](https://example.com).\\n\\n## Heading\\n\\nBody text..."'
    elif post_type == "gutenberg":
        format_rules = f"""
- Write the content value as WordPress Gutenberg block HTML.
- Wrap paragraphs and headings with Gutenberg comments, such as <!-- wp:paragraph --><p>...</p><!-- /wp:paragraph --> and <!-- wp:heading --><h2>...</h2><!-- /wp:heading -->.
- Use normal paragraph blocks with 2-4 sentences each. Do not create many tiny paragraph blocks.
- Use this HTML link format once anywhere in the article inside a Gutenberg paragraph block when a brand URL is provided: <a href='{required_url}' rel='nofollow noopener noreferrer' target='_blank'>anchor text</a>.
- Use <b> only for emphasis on important non-keyword words or phrases.
- Do not use <strong>.
- Never bold the primary keyword.
- Do not wrap keywords in <b> or <strong> tags.
"""
        return_example = '"content": "<!-- wp:paragraph --><p>Intro with <a href=\'https://example.com\'>anchor text</a>.</p><!-- /wp:paragraph -->"'
    elif post_type == "text":
        format_rules = f"""
- Write the content value as plain text only.
- Do not use HTML tags or Markdown syntax.
- Use clear section labels on their own lines when needed.
- Keep related sentences together in compact paragraphs. Do not put every sentence on its own line.
- Use only one blank line between sections.
- Insert the brand URL exactly once anywhere in the article as plain text when a brand URL is provided: {required_url}.
- Do not use HTML or Markdown emphasis.
"""
        return_example = '"content": "Intro paragraph with https://example.com included once.\\n\\nSection heading\\nBody text..."'
    else:
        format_rules = f"""
- Write the content value in HTML.
- Use <h2> for main sections and <h3> for subsections.
- Use <p> for compact paragraphs with 2-4 related sentences each.
- Use <ul><li> for bullet lists where helpful.
- Do not create a separate <p> tag for every sentence.
- Do not add unnecessary newline characters between HTML tags.
- Use this HTML link format once anywhere in the article inside a paragraph when a brand URL is provided: <a href='{required_url}' rel='nofollow noopener noreferrer' target='_blank'>anchor text</a>.
- Use <b> only for emphasis on important non-keyword words or phrases.
- Do not use <strong>.
- Never bold the primary keyword.
- Do not wrap keywords in <b> or <strong> tags.
"""
        return_example = '"content": "<p>Intro with <a href=\'https://example.com\'>anchor text</a>.</p><h2>Heading</h2><p>Body text...</p>"'

    compact_medium = bool(max_words and max_words <= 300)
    short_medium = bool(max_words and max_words <= 700)
    if compact_medium:
        structure_rules = """
- Write a compact informational post, not a full long-form article.
- Do not use a 60-80 word introduction.
- Do not force 3-4 sections.
- Use one short opening paragraph, then 1-2 brief points only if the word limit allows.
- Avoid CTA sections. End with a useful informational closing sentence.
- Keep every part necessary, complete, and within the selected word limit.
"""
    elif short_medium:
        structure_rules = """
- Write a concise informational article, not a full long-form article.
- Start with a brief introduction of 35-55 words.
- Use 2-3 short sections at most.
- Keep each section compact and useful.
- End with one short Conclusion or Final Thoughts section.
- Keep every part necessary, complete, and within the selected word limit.
"""
    else:
        structure_rules = """
- Start with an engaging introduction of 60-80 words that explains the reader's problem or need.
- Add detailed explanations, useful examples, and practical context in each section to support the word count naturally.
- Structure the article in this order: introduction, 3-4 main sections with subheadings, then exactly one ending section that best fits the page intent.
- Use exactly one ending section only: FAQs, Conclusion, or Final Thoughts.
- Do not use these sections together in the same page.
- Choose the ending section that best matches the page type and search intent.
"""

    return f"""
You are a professional informational writer who creates SEO-friendly, human-sounding blog articles and guest-post content.

Write a complete blog article for this title:
"{title}"

Topic keyword: {keyword}
Supporting keyword: {supporting_keyword}
Brand: {brand}
{context_section}
{backlink_section}

{banned_words_section}
{suggested_content_section}

{change_request_section}

{platform_rules}

Rules:
{min_word_rule}
{structure_rules}

- Make the article feel appropriate for an external publisher or guest-post style placement.
- Adapt the structure, tone, and delivery to the selected website type instead of forcing the same format for every medium.
- Write an informational article, not a promotional article.
- If the title, keyword, or brand context includes casino or betting terms, handle them as neutral examples of app design, interface quality, user experience, account safety, payment security, product design, mobile performance, or responsible digital play.
- Do not write promotional casino copy, bonus-focused copy, or betting advice.
- Keep the article centered on the informational angle promised by the title. For example, a casino app interface title should compare navigation, layout, clarity, trust cues, safety controls, and mobile usability.
- Suitable topic angles include gaming platforms, game discovery, online entertainment tools, player experience, app technology, payment security, account safety, AI in games, mobile performance, web platforms, and other technology topics.
- For Tier 1 placements, write like a neutral publication explaining, comparing, or teaching a topic.
- Write in third person. Do not write as the brand or from the brand's point of view.
- Mention the brand name no more than once in the full article, and only as a natural example.
- Mention the primary keyword no more than once in the full article, and only as a natural example.
- Do not put the brand name or exact keyword in headings.
- Avoid brand-name stuffing. After the single example mention, use neutral category language like "a gaming platform", "a games site", "a mobile app", "a digital entertainment tool", or "an online platform" when the meaning stays clear.
- Do not repeat the exact article title in the body unless absolutely necessary. However, keep the content closely aligned with the title and main topic.
- Avoid keyword stuffing and never force keywords into awkward sentences.
- Use the main keyword no more than once per paragraph.
- Do not repeat the same keyword multiple times in a single paragraph.
- Use a natural, human, conversational tone.
- Write in active voice with short, clear sentences.
- Write for readability using compact paragraphs, not many tiny one-line paragraphs.
- Avoid excessive line breaks. Do not place each sentence on a separate line.
- Keep sections tidy: one heading followed by 1-2 meaningful paragraphs, not a long stack of single-sentence lines.
- Keep examples educational. A brand or keyword may appear once as an example, but the article must remain about the broader informational topic.

{format_rules}

- If a brand is provided, use the brand context only to understand audience and category. Do not write an advertisement.
- If a brand is provided, mention the brand at most once as an example and avoid repeating it.
- If a medium publication name is provided, treat it as the blog or publication name and mention it naturally when relevant, but do not force it repeatedly.
- If a writer name is provided, use it naturally as the article byline or writer identity when it fits.
- If the medium tier is Tier 1 and a blog name is provided, include that blog name only when it feels natural.
- Do not stuff the brand name, blog name, or writer name into every heading or paragraph.
- When brand, blog name, and writer name are provided, make them feel intentional and editorially natural.
- Match the writing style to the website type:
  - forum: discussion-oriented, practical, community-style
  - social_media: punchy, skimmable, conversational
  - review: balanced, criteria-focused, informational
  - news: informative, publication-style, neutral
  - directory: concise, utility-focused
  - community: helpful, shared-insight tone
- If brand database context is provided, avoid repeating existing keyword angles and keep the content aligned with current brand pages.
- Include the required brand link once in a natural way with relevant anchor text.
- The required brand URL must appear exactly once total in the content output.
- Do not include the medium URL or any other URL in the output.
- If a max word count is provided for the medium, use it as a soft guide for concision, but do not cut the article below the minimum word count.
- Return only valid JSON with this format: {{"content":"..."}}.
- The value of "content" must contain complete content in the selected post type format.
- Do not add any explanation, notes, or text before or after the JSON object.
- Start the response with "{{" and end it with "}}".
- Close every HTML tag and every quotation mark properly.
- Do not truncate, abbreviate, or cut off the article.
- Do not guess what a brand, game, or platform is.
- When the selected post type supports HTML attributes, external links and the required brand link must use rel='nofollow noopener noreferrer' and target='_blank'.
{completion_word_rule}
- If minimum and maximum word guidance conflict, prioritize staying over the minimum word count.

Return valid JSON only in this format:
{{
  {return_example},
  "word_count": 850
}}
"""
