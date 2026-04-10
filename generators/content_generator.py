import json
import re
from prompts import build_content_prompt
from utils import extract_json_string
from logger import logger

def count_html_words(html_text: str) -> int:
    """Count words in HTML content by removing tags."""
    # Remove HTML tags
    clean_text = re.sub(r'<[^>]+>', '', html_text)
    # Remove extra whitespace and split
    words = clean_text.split()
    return len(words)

def generate_content(
    provider,
    title: str,
    keyword: str = "",
    supporting_keyword: str = "",
    tone: str = "natural",
    links: list = None,
    brand: str = "",
    brand_context: str = "",
):
    prompt = build_content_prompt(
        title=title,
        keyword=keyword,
        supporting_keyword=supporting_keyword,
        tone=tone,
        links=links,
        brand=brand,
        brand_context=brand_context,
    )
    raw = provider.generate_json(prompt)

    try:
        json_text = extract_json_string(raw)
        data = json.loads(json_text)
        content = data.get("content", "")
        word_count = count_html_words(content)
        
        # Log warning if content is below target
        if word_count < 800:
            logger.warning(
                "Content word count is %d (target: 800-1000). Response may be incomplete. Raw response length: %d chars",
                word_count,
                len(raw)
            )
        else:
            logger.info("Content generated successfully with %d words", word_count)
        
        return content
    except Exception as exc:
        logger.exception("generate_content failed. Raw response: %s", raw)
        raise ValueError("Could not parse JSON from model output.") from exc
