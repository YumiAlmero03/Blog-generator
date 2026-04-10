import json
from prompts import build_title_prompt
from utils import extract_json_string
from logger import logger

def generate_titles(
    provider,
    keyword: str,
    supporting_keyword: str = "",
    tone: str = "natural",
    count: int = 10,
    brand: str = "",
    brand_context: str = "",
):
    prompt = build_title_prompt(
        keyword=keyword,
        supporting_keyword=supporting_keyword,
        tone=tone,
        count=count,
        brand=brand,
        brand_context=brand_context,
    )
    raw = provider.generate_json(prompt)

    try:
        json_text = extract_json_string(raw)
        data = json.loads(json_text)
        titles = data.get("titles", [])
        return titles
    except Exception as exc:
        logger.exception("generate_titles failed. Raw response: %s", raw)
        raise ValueError("Could not parse JSON from model output.") from exc
