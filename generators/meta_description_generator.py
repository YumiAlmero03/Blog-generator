import json
from prompts import build_meta_description_prompt
from utils import extract_json_string
from logger import logger

def generate_meta_descriptions(provider, title: str, keyword: str = "", count: int = 3):
    prompt = build_meta_description_prompt(title=title, keyword=keyword, count=count)
    raw = provider.generate_json(prompt)

    try:
        json_text = extract_json_string(raw)
        data = json.loads(json_text)
        meta_descriptions = data.get("meta_descriptions", [])
        return meta_descriptions
    except Exception as exc:
        logger.exception("generate_meta_descriptions failed. Raw response: %s", raw)
        raise ValueError("Could not parse JSON from model output.") from exc

def generate_meta_description(provider, title: str, keyword: str = ""):
    """Legacy function for single meta description"""
    descriptions = generate_meta_descriptions(provider, title, keyword, count=1)
    return descriptions[0]["text"] if descriptions else ""
