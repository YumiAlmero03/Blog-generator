import json
from prompts import build_title_prompt

def generate_titles(provider, keyword: str, tone: str = "natural", count: int = 10):
    prompt = build_title_prompt(keyword=keyword, tone=tone, count=count)
    raw = provider.generate_json(prompt)

    try:
        data = json.loads(raw)
        titles = data.get("titles", [])
        return titles
    except Exception:
        print("Raw response:")
        print(raw)
        raise ValueError("Could not parse JSON from model output.")