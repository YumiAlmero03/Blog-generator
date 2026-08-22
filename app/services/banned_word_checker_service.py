import re

from app.services.seo_checker_service import PageSeoParser, fetch_url
from word_bank import load_banned_word_bank


MAX_SNIPPETS_PER_TERM = 5
SNIPPET_RADIUS = 70


def check_website_banned_words(url: str, verify_ssl: bool = True, allow_private: bool = False) -> dict:
    page = fetch_url(url, verify_ssl=verify_ssl, allow_private=allow_private)
    parser = PageSeoParser()
    parser.feed(page.text)

    checked_text = "\n".join(
        item
        for item in (
            parser.title,
            parser.meta_description,
            parser.body_text,
        )
        if item
    )
    terms = load_banned_word_bank()
    matches = _banned_word_matches(checked_text, terms)

    return {
        "url": page.url,
        "status_code": page.status_code,
        "content_type": page.content_type,
        "checked_character_count": len(checked_text),
        "banned_word_count": len(terms),
        "match_count": sum(item["count"] for item in matches),
        "matched_term_count": len(matches),
        "matches": matches,
    }


def _banned_word_matches(text: str, terms: list[str]) -> list[dict]:
    content = text or ""
    results = []
    for term in terms:
        pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        found = list(pattern.finditer(content))
        if not found:
            continue
        results.append(
            {
                "term": term,
                "count": len(found),
                "snippets": [_match_snippet(content, match) for match in found[:MAX_SNIPPETS_PER_TERM]],
            }
        )
    return sorted(results, key=lambda item: (-item["count"], item["term"].casefold()))


def _match_snippet(text: str, match: re.Match) -> str:
    start = max(0, match.start() - SNIPPET_RADIUS)
    end = min(len(text), match.end() + SNIPPET_RADIUS)
    snippet = " ".join(text[start:end].split())
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{snippet}{suffix}"
