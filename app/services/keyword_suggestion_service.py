import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from logger import logger
from prompts.keyword_suggestions import build_keyword_suggestions_prompt
from utils import extract_json_string


GOOGLE_SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
QUESTION_PREFIXES = ("what is", "how to", "why", "where", "when", "best", "top", "near me")


def fetch_google_autocomplete_keywords(topic: str, timeout: int = 8) -> list[str]:
    seed = " ".join((topic or "").split()).strip()
    if not seed:
        return []

    queries = [seed, *(f"{prefix} {seed}" for prefix in QUESTION_PREFIXES)]
    suggestions = []
    seen = set()
    for query in queries:
        params = urlencode({"client": "firefox", "q": query})
        request = Request(
            f"{GOOGLE_SUGGEST_URL}?{params}",
            headers={"User-Agent": "Mozilla/5.0 (compatible; KeywordSuggestions/1.0)"},
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            logger.warning("Could not fetch autocomplete suggestions for %s: %s", query, exc)
            continue
        for value in data[1] if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) else []:
            cleaned = _clean_keyword(value)
            normalized = cleaned.lower()
            if cleaned and normalized not in seen:
                seen.add(normalized)
                suggestions.append(cleaned)
    return suggestions[:80]


def generate_keyword_suggestions(
    provider,
    topic: str,
    target_country: str = "Worldwide",
    count: int = 30,
    progress_callback=None,
) -> dict:
    cleaned_topic = _clean_keyword(topic)
    if not cleaned_topic:
        raise ValueError("Enter a topic to generate keyword suggestions.")

    _publish_progress(progress_callback, "Fetching autocomplete keyword ideas...")
    autocomplete_keywords = fetch_google_autocomplete_keywords(cleaned_topic)
    source = "Google autocomplete + AI estimates" if autocomplete_keywords else "AI estimates"

    prompt = build_keyword_suggestions_prompt(
        topic=cleaned_topic,
        autocomplete_keywords=autocomplete_keywords,
        target_country=target_country,
        count=count,
    )
    _publish_progress(progress_callback, prompt, kind="prompt")
    _publish_progress(progress_callback, "Generating keyword estimates...")
    raw = provider.generate_json(prompt)
    try:
        data = json.loads(extract_json_string(raw))
    except Exception as exc:
        logger.exception("keyword suggestions failed. Raw response: %s", raw)
        raise ValueError("Could not parse keyword suggestions from model output.") from exc

    keywords = []
    seen = set()
    for item in data.get("keywords", []):
        if not isinstance(item, dict):
            continue
        keyword = _clean_keyword(item.get("keyword", ""))
        normalized = keyword.lower()
        if not keyword or normalized in seen:
            continue
        seen.add(normalized)
        keywords.append({
            "keyword": keyword,
            "intent": _choice(item.get("intent", ""), {"informational", "commercial", "transactional", "navigational", "news"}, "informational"),
            "difficulty": _choice(item.get("difficulty", ""), {"easy", "medium", "hard"}, "medium"),
            "difficulty_score": _int_range(item.get("difficulty_score", 50), 0, 100, 50),
            "estimated_monthly_searches": str(item.get("estimated_monthly_searches", "unknown")).strip() or "unknown",
            "content_angle": " ".join(str(item.get("content_angle", "")).split()).strip(),
            "notes": " ".join(str(item.get("notes", "")).split()).strip(),
        })

    return {
        "topic": cleaned_topic,
        "target_country": target_country,
        "source": source,
        "autocomplete_keywords": autocomplete_keywords,
        "keywords": keywords[:count],
    }


def _clean_keyword(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _choice(value: str, allowed: set[str], default: str) -> str:
    cleaned = str(value or "").strip().lower()
    return cleaned if cleaned in allowed else default


def _int_range(value, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _publish_progress(progress_callback, message: str, kind: str = "status") -> None:
    if not progress_callback:
        return
    try:
        progress_callback(message, kind=kind)
    except TypeError:
        progress_callback(message)
    except Exception:
        logger.exception("keyword suggestions progress callback failed")
