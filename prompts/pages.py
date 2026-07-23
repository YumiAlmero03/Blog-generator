from word_bank import build_banned_words_prompt_section

from prompts.shared import build_brand_context_section, build_language_instruction

def build_page_prompt(
    keyword: str,
    supporting_keywords: str = "",
    page_type: str = "",
    expectations: str = "",
    brand: str = "",
    brand_context: str = "",
    change_request: str = "",
    min_words: int | str = 1000,
    max_words: int | str = 19000,
    language: str = "English",
) -> str:
    context_section = build_brand_context_section(brand_context)
    language_section = build_language_instruction(language)
    banned_words_section = build_banned_words_prompt_section()
    min_word_count = _positive_int(min_words, 1000)
    max_word_count = _positive_int(max_words, 19000)
    if max_word_count < min_word_count:
        max_word_count = min_word_count
    change_request_section = ""
    cleaned_change_request = (change_request or "").strip()
    if cleaned_change_request:
        change_request_section = f"""
Minor change request from the user:
{cleaned_change_request}

Apply this request while keeping the page complete, conversion-focused, and aligned with all rules below.
"""
    return f"""
You are an expert SEO landing page writer for WordPress.

Create a complete WordPress page for this primary keyword:
{keyword}

Supporting keywords:
{supporting_keywords}

Brand:
{brand}
{context_section}
{language_section}
{banned_words_section}

Page type:
{page_type}

What to expect in the page:
{expectations}
{change_request_section}

Rules:
- Keep the main keyword exactly as provided. Do not split, rearrange, or alter it. Use it naturally in the title and content.
- Write for real users, not just search engines.
- Write as the website owner: use first-person plural language like we, our, and us when referring to the brand, team, service, process, support, or promises.
- Do not refer to the website, brand, team, or service as they, them, or their. Avoid third-person wording for the page owner.
- Use the main keyword naturally 3–5 times in total: once in the title, once in the introduction, once in a subheading, and once in the conclusion.
- Include supporting keywords naturally where they fit.
- Avoid keyword stuffing, repeated exact-match phrases, and unnatural keyword placement.
- Follow Yoast-style SEO and readability rules: one clear H1, logical H2/H3 structure, concise paragraphs, transition words, active voice, clear internal intent, and helpful user-first copy.

- Title should be catchy, include the main keyword naturally, and be 45–55 characters when possible.
- Meta description must be useful for search snippets, natural, and between 120 and 140 characters.
- Introduction should be 60–80 words, engaging, and include the main keyword naturally once.
- Content must be more than {min_word_count} words, structured with clear sections and subheadings. Treat {max_word_count} words as a soft guide, but prioritize staying over the minimum.
- Do not finish at exactly {min_word_count} words; the content must exceed that minimum.
- Paragraphs should be short and easy to read.

- If a brand is provided, match the brand’s voice, positioning, and audience naturally.
- When brand database context is provided, avoid duplicating existing pages too closely.

- Return clean Markdown source. The app will convert it to HTML or Gutenberg after generation.
- Use Markdown headings, paragraphs, lists, bold, emphasis, and blockquotes only.
- Do not use <b> tags.
- Use Markdown bold only for emphasis on non-keyword phrases.
- Never apply bold or emphasis to the main or supporting keywords.

- Include exactly one # H1 heading at the top.
- Structure the page clearly for readability and conversions.
- Adapt the structure based on the page type naturally.
- Keep paragraphs short and easy to read.
- Use bullet points and subheadings to break up content.

- Include at least 5 sections after the introduction with relevant subheadings.
- Follow Yoast SEO guidelines for keyword usage and structure without forcing exact-match keywords.
- Use the "What to expect in the page" notes as guidance for sections, tone, and key details.

- If helpful, insert image placeholders using:
  [IMAGE: alt text describing the image here]
- Add no more than 3 image placeholders.

- Do not use raw HTML.
- Do not add explanations before or after the JSON.
- Ensure the content is complete and over {min_word_count} words.
- Start your response with '{{' and end with '}}'

Return valid JSON only in this format:
{{
  "title": "Page Title",
  "meta_description": "SEO meta description here",
  "content": "# Page Title\\n\\nParagraph...",
  "image_count": 2
}}
"""


def build_page_title_prompt(
    keyword: str,
    supporting_keywords: str = "",
    page_type: str = "",
    expectations: str = "",
    brand: str = "",
    brand_context: str = "",
    language: str = "English",
) -> str:
    context_section = build_brand_context_section(brand_context)
    language_section = build_language_instruction(language)
    banned_words_section = build_banned_words_prompt_section()
    return f"""
You are an expert SEO landing page title writer.

Create one strong WordPress page title for this primary keyword:
{keyword}

Brand:
{brand}
{context_section}
{language_section}
{banned_words_section}

Page type:
{page_type}


Rules:
- Keep the main keyword exactly as provided. Do not split, rearrange, or alter it.
- Start the title with the exact main keyword as the first words.
- Format it like: "{keyword} generated title".
- Make the title catchy, clear, and useful for real users.
- The title must be between 50 and 60 characters.
- Do not use banned words.
- Do not add explanations before or after the JSON.
- Start your response with '{{' and end with '}}'

Return valid JSON only in this format:
{{
  "title": "Page Title"
}}
"""


def build_page_meta_description_prompt(
    keyword: str,
    title: str,
    supporting_keywords: str = "",
    page_type: str = "",
    expectations: str = "",
    brand: str = "",
    brand_context: str = "",
    language: str = "English",
) -> str:
    context_section = build_brand_context_section(brand_context)
    language_section = build_language_instruction(language)
    banned_words_section = build_banned_words_prompt_section()
    return f"""
You are an expert SEO meta description writer.

Write one meta description for this WordPress page title:
{title}

Primary keyword:
{keyword}

{context_section}
{language_section}
{banned_words_section}

Page type:
{page_type}

What to expect in the page:
{expectations}

Rules:
- Make the description useful for search snippets and natural for readers.
- Keep it between 120 and 140 characters.
- Use the primary keyword naturally if it fits.
- Do not use banned words.
- Do not add explanations before or after the JSON.
- Start your response with '{{' and end with '}}'

Return valid JSON only in this format:
{{
  "meta_description": "SEO meta description here"
}}
"""


def build_page_content_prompt(
    keyword: str,
    title: str,
    meta_description: str,
    supporting_keywords: str = "",
    page_type: str = "",
    expectations: str = "",
    brand: str = "",
    brand_context: str = "",
    change_request: str = "",
    min_words: int | str = 1000,
    max_words: int | str = 19000,
    language: str = "English",
) -> str:
    context_section = build_brand_context_section(brand_context)
    language_section = build_language_instruction(language)
    banned_words_section = build_banned_words_prompt_section()
    min_word_count = _positive_int(min_words, 1000)
    max_word_count = _positive_int(max_words, 19000)
    if max_word_count < min_word_count:
        max_word_count = min_word_count
    change_request_section = ""
    cleaned_change_request = (change_request or "").strip()
    if cleaned_change_request:
        change_request_section = f"""
Minor change request from the user:
{cleaned_change_request}

Apply this request while keeping the page complete, conversion-focused, and aligned with all rules below.
"""
    return f"""
You are an expert SEO landing page writer for WordPress.

Use this selected page title exactly:{title}
Primary keyword:{keyword}
Supporting keywords:{supporting_keywords}

{context_section}
{language_section}
{banned_words_section}

Page type:{page_type}

What to expect in the page:
{expectations}
{change_request_section}

Rules:
- Keep the main keyword exactly as provided. Do not split, rearrange, or alter it.
- Write for real users, not just search engines.
- Write as the website owner: use first-person plural language like we, our, and us when referring to the brand, team, service, process, support, or promises.
- Do not refer to the website, brand, team, or service as they, them, or their. Avoid third-person wording for the page owner.
- Use the main keyword naturally 3-5 times in total: once in the introduction, once in a subheading, and once in the conclusion when natural.
- Include supporting keywords naturally where they fit.
- Avoid keyword stuffing, repeated exact-match phrases, and unnatural keyword placement.
- Follow Yoast-style SEO and readability rules: one clear H1, logical H2/H3 structure, concise paragraphs, transition words, active voice, clear internal intent, and helpful user-first copy.
- Introduction should be 60-80 words, engaging, and include the main keyword naturally once.
- Content must be more than {min_word_count} words, structured with clear sections and subheadings. Treat {max_word_count} words as a soft guide, but prioritize staying over the minimum.
- Do not finish at exactly {min_word_count} words; the content must exceed that minimum.
- Paragraphs should be short and easy to read.
- Include at least 5 or more sections after the introduction with relevant subheadings.
- Follow Yoast SEO guidelines for keyword usage and structure without forcing exact-match keywords.
- Use the "What to expect in the page" notes as guidance for sections, tone, and key details.
- If a brand is provided, match the brand’s voice, positioning, and audience naturally.
- When brand database context is provided, avoid duplicating existing pages too closely.
- Return clean Markdown.
- Use bold only for emphasis on non-keyword phrases.
- Never apply bold or emphasis to the main or supporting keywords.
- Do not add explanations before or after the JSON.
- Start your response with '{{' and end with '}}'

Return valid JSON only in this format:
{{
  "content": "# {title}\\n\\nParagraph...",
  "image_count": 2
}}
"""


def build_simple_page_prompt(
    page_title: str,
    page_type: str = "",
    brand: str = "",
    supporting_keywords: str = "",
    expectations: str = "",
    brand_context: str = "",
    change_request: str = "",
    min_words: int | str = 900,
    max_words: int | str = 1200,
    language: str = "English",
) -> str:
    context_section = build_brand_context_section(brand_context)
    language_section = build_language_instruction(language)
    banned_words_section = build_banned_words_prompt_section()
    min_word_count = _positive_int(min_words, 900)
    max_word_count = _positive_int(max_words, 1200)
    if max_word_count < min_word_count:
        max_word_count = min_word_count
    change_request_section = ""
    cleaned_change_request = (change_request or "").strip()
    if cleaned_change_request:
        change_request_section = f"""
Minor change request from the user:
{cleaned_change_request}

Apply this request while keeping the simple page complete, clear, and aligned with all rules below.
"""
    responsible_gaming_section = ""
    if (page_type or "").strip().lower() == "responsible gaming":
        responsible_gaming_section = """
Responsible Gaming page requirements:
- Frame the page around safer play, user control, age restrictions, support resources, self-exclusion, deposit/time limits, warning signs, and getting help.
- Do not make gambling sound exciting, profitable, guaranteed, or risk-free.
- Avoid promotional language, bonus language, jackpot language, or encouragement to play more.
- Include a clear reminder that gaming should be for adults only and should never be treated as a way to make money.
- Include practical steps readers can take if gaming stops feeling recreational.
- Keep the tone supportive, calm, factual, and non-judgmental.
"""
    return f"""
You are an expert WordPress page writer for simple website pages.

Create a complete simple WordPress page for:
{page_title}

Page type:
{page_type}

Supporting keywords:
{supporting_keywords}

Brand:
{brand}
{context_section}
{language_section}
{banned_words_section}

What to include:
{expectations}
{change_request_section}
{responsible_gaming_section}

Rules:
- This generator is for simple pages such as Privacy Policy, Terms and Conditions, Disclaimer, About Us, Contact Us, Refund Policy, Shipping Policy, Cookie Policy, Responsible Gaming, or similar low-complexity pages
- Write clear, structured Markdown source that the app can convert to HTML or Gutenberg
- Use Markdown headings, paragraphs, lists, bold, emphasis, and blockquotes only
- Include exactly one # H1 heading
- Include at least 3 ### H3 subheadings in the content.
- Keep the tone clear, professional, and easy to understand
- Include supporting keywords naturally where they fit, without keyword stuffing
- If a brand is provided, use the brand name naturally where relevant
- If brand context is provided, align the page with that brand only when it fits naturally
- Adapt the structure to the page type
- Do not add image placeholders
- Do not use raw HTML
- Ensure the content is complete and over {min_word_count} words.
- Generate exactly 3 meta description options for the page.
- Each meta description must be useful for search snippets, natural, and between 120 and 140 characters.
- Do not add explanations before or after the JSON
- Start your response with '{{' and end with '}}'

Return valid JSON only in this format:
{{
  "title": "Page Title",
  "meta_descriptions": [
    {{"text": "First meta description option here."}},
    {{"text": "Second meta description option here."}},
    {{"text": "Third meta description option here."}}
  ],
  "content": "# Page Title\\n\\nParagraph..."
}}
"""


def build_simple_page_title_prompt(
    page_title: str,
    page_type: str = "",
    brand: str = "",
    supporting_keywords: str = "",
    expectations: str = "",
    brand_context: str = "",
    language: str = "English",
) -> str:
    context_section = build_brand_context_section(brand_context)
    language_section = build_language_instruction(language)
    banned_words_section = build_banned_words_prompt_section()
    return f"""
You are an expert WordPress page title writer.

Create one clear page title for:
{page_title}

Page type:
{page_type}

Supporting keywords:
{supporting_keywords}

Brand:
{brand}
{context_section}
{language_section}
{banned_words_section}

What to include:
{expectations}

Rules:
- Start the title with the exact page title as the first words.
- Format it like: "{page_title} generated title".
- Keep the title clear, professional, and suitable for the selected page type.
- Use supporting keywords only when they fit naturally.
- If a brand is provided, use it naturally only when it fits the page.
- Do not use banned words.
- Do not add explanations before or after the JSON.
- Start your response with '{{' and end with '}}'

Return valid JSON only in this format:
{{
  "title": "Page Title"
}}
"""


def build_simple_page_meta_prompt(
    page_title: str,
    generated_title: str,
    page_type: str = "",
    brand: str = "",
    supporting_keywords: str = "",
    expectations: str = "",
    brand_context: str = "",
    language: str = "English",
) -> str:
    context_section = build_brand_context_section(brand_context)
    language_section = build_language_instruction(language)
    banned_words_section = build_banned_words_prompt_section()
    return f"""
You are an expert SEO meta description writer.

Generate exactly 3 meta description options for this simple WordPress page.

Original page name:
{page_title}

Selected title:
{generated_title}

Page type:
{page_type}

Supporting keywords:
{supporting_keywords}

Brand:
{brand}
{context_section}
{language_section}
{banned_words_section}

What to include:
{expectations}

Rules:
- Each meta description must be natural, useful for search snippets, and between 120 and 140 characters.
- Include supporting keywords naturally where they fit, without keyword stuffing.
- Do not use banned words.
- Do not add explanations before or after the JSON.
- Start your response with '{{' and end with '}}'

Return valid JSON only in this format:
{{
  "meta_descriptions": [
    {{"text": "First meta description option here."}},
    {{"text": "Second meta description option here."}},
    {{"text": "Third meta description option here."}}
  ]
}}
"""


def build_simple_page_content_prompt(
    page_title: str,
    generated_title: str,
    selected_meta_description: str = "",
    page_type: str = "",
    brand: str = "",
    supporting_keywords: str = "",
    expectations: str = "",
    brand_context: str = "",
    change_request: str = "",
    min_words: int | str = 900,
    max_words: int | str = 1200,
    language: str = "English",
) -> str:
    context_section = build_brand_context_section(brand_context)
    language_section = build_language_instruction(language)
    banned_words_section = build_banned_words_prompt_section()
    min_word_count = _positive_int(min_words, 900)
    max_word_count = _positive_int(max_words, 1200)
    if max_word_count < min_word_count:
        max_word_count = min_word_count
    change_request_section = ""
    cleaned_change_request = (change_request or "").strip()
    if cleaned_change_request:
        change_request_section = f"""
Minor change request from the user:
{cleaned_change_request}

Apply this request while keeping the simple page complete, clear, and aligned with all rules below.
"""
    responsible_gaming_section = ""
    if (page_type or "").strip().lower() == "responsible gaming":
        responsible_gaming_section = """
Responsible Gaming page requirements:
- Frame the page around safer play, user control, age restrictions, support resources, self-exclusion, deposit/time limits, warning signs, and getting help.
- Do not make gambling sound exciting, profitable, guaranteed, or risk-free.
- Avoid promotional language, bonus language, jackpot language, or encouragement to play more.
- Include a clear reminder that gaming should be for adults only and should never be treated as a way to make money.
- Include practical steps readers can take if gaming stops feeling recreational.
- Keep the tone supportive, calm, factual, and non-judgmental.
"""
    return f"""
You are an expert WordPress page writer for simple website pages.

Use this selected title exactly as the H1:
{generated_title}

Original page name:
{page_title}

Selected meta description for context. Do not rewrite it:
{selected_meta_description}

Page type:
{page_type}

Supporting keywords:
{supporting_keywords}

Brand:
{brand}
{context_section}
{language_section}
{banned_words_section}

What to include:
{expectations}
{change_request_section}
{responsible_gaming_section}

Rules:
- This generator is for simple pages such as Privacy Policy, Terms and Conditions, Disclaimer, About Us, Contact Us, Refund Policy, Shipping Policy, Cookie Policy, Responsible Gaming, or similar low-complexity pages.
- Write clear, structured Markdown source that the app can convert to HTML or Gutenberg.
- Use Markdown headings, paragraphs, lists, bold, emphasis, and blockquotes only.
- Include exactly one # H1 heading using the selected title.
- Include at least 3 ### H3 subheadings in the content.
- Keep the tone clear, professional, and easy to understand.
- Include supporting keywords naturally where they fit, without keyword stuffing.
- If a brand is provided, use the brand name naturally where relevant.
- If brand context is provided, align the page with that brand only when it fits naturally.
- Adapt the structure to the page type.
- Do not add image placeholders.
- Do not use raw HTML.
- Ensure the content is complete and over {min_word_count} words.
- Do not add explanations before or after the JSON.
- Start your response with '{{' and end with '}}'

Return valid JSON only in this format:
{{
  "content": "# {generated_title}\\n\\nParagraph..."
}}
"""


def build_page_section_prompt(
    keyword: str,
    title: str,
    current_content: str,
    section_request: str,
    supporting_keywords: str = "",
    page_type: str = "",
    expectations: str = "",
    brand: str = "",
    brand_context: str = "",
    language: str = "English",
) -> str:
    context_section = build_brand_context_section(brand_context)
    language_section = build_language_instruction(language)
    banned_words_section = build_banned_words_prompt_section()
    return f"""
You are an expert SEO landing page section writer for WordPress.

Write one new insertable section for this existing page.

Selected page title:
{title}

Primary keyword:
{keyword}

Supporting keywords:
{supporting_keywords}

Page type:
{page_type}

Brand:
{brand}
{context_section}
{language_section}
{banned_words_section}

Original page expectations:
{expectations}

Existing page content for context:
{current_content}

Section request:
{section_request}

Rules:
- Return only the new section, not the full page.
- Start the section with one ## H2 heading.
- Use ### H3 subheadings only if they genuinely help.
- Write 120-450 words unless the request clearly needs a shorter section.
- Match the existing page voice and structure.
- Write as the website owner: use first-person plural language like we, our, and us where relevant.
- Include the primary keyword and supporting keywords only where they fit naturally.
- Avoid keyword stuffing and repeated exact-match phrasing.
- Do not use banned words.
- Return clean Markdown only inside JSON.
- Do not include a # H1 heading.
- Do not use raw HTML.
- Do not add explanations before or after the JSON.
- Start your response with '{{' and end with '}}'

Return valid JSON only in this format:
{{
  "section_title": "Section Heading",
  "content": "## Section Heading\\n\\nParagraph..."
}}
"""


def _positive_int(value: int | str, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, parsed)
