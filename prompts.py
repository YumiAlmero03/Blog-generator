# Pro
def build_title_prompt(keyword: str, supporting_keyword: str = "", tone: str = "natural", count: int = 10) -> str:
    return f"""
You are an SEO blog title generator.

Generate exactly {count} blog title variants for this keyword/topic:
{keyword}

Supporting ideas: {supporting_keyword}

Rules:
- Return exactly {count} titles
- Dont seperate keyword with punctuation, use it naturally in the title
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
- Keep titles around 50 to 55 characters when possible
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

def build_meta_description_prompt(title: str, keyword: str = "", count: int = 3) -> str:
    return f"""
You are an SEO meta description writer.

Generate exactly {count} compelling meta description variants for this blog post title:
"{title}"

Keyword: {keyword}

Rules:
- Each meta description must be 120-150 characters exactly
- Include the main keyword naturally
- Be compelling and encourage clicks
- Avoid keyword stuffing
- Use active voice
- Include a call-to-action or value proposition
- Make it human and natural sounding
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
def build_content_prompt(title: str, keyword: str = "", supporting_keyword: str = "", tone: str = "natural", links: list = None) -> str:
    links_section = ""
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
Tone: {tone}
{links_section}

Rules:
- Write blog article between 800 - 1000 words
- Start with an engaging introduction (100-140 words) that explains the problem
- Use HTML headings: <h2> for sections and <h3> for sub-sections
- Use <b> for bold text
- Use <p> for paragraphs and <ul><li> for bullet lists
- Structure: introduction, 3-4 main sections with subheadings, conclusion
- Make it natural, human-sounding, and conversational
- Include the keyword naturally 2-4 times throughout the content, especially in the introduction and conclusion
- Avoid keyword stuffing; do not force the keyword into sentences where it does not fit
- Include the supporting keyword naturally where appropriate
- Use active voice, short sentences
- Avoid keyword stuffing and robotic language
- Write for readability with short paragraphs
- Add detailed explanations and examples in each section to reach word count
- End with a clear and short call-to-action (e.g. "Start your fitness journey today with our expert tips!")
- Do not use markdown headings like ## or ###
- Use HTML anchor tags with single quotes: <a href='URL'>anchor text</a>
- Return the content as valid HTML inside the JSON string
- CRITICAL: Do not truncate, abbreviate, or cut short the content
- Do not add any explanation, analysis, or notes before or after the JSON
- Start your response with '{' and end your response with '}'
- Close every open tag and quotation mark
- Make sure the JSON is complete and valid
- Verify the content word count is at least 800 words before finishing

Return valid JSON only in this format:
{{
  "content": "<h2>Your HTML content here</h2><p>...</p>",
  "word_count": 850
}}
"""
