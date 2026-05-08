import re
from pathlib import Path


WORD_BANK_FILE = Path(__file__).resolve().parent / "banned_words.txt"


def load_banned_word_bank() -> list[str]:
    terms = []
    seen = set()

    def add_term(raw_term: str):
        cleaned_term = raw_term.strip()
        if not cleaned_term or cleaned_term.startswith("#"):
            return
        lowered = cleaned_term.lower()
        if lowered in seen:
            return
        seen.add(lowered)
        terms.append(cleaned_term)

    if not WORD_BANK_FILE.exists():
        return _load_custom_banned_words(terms, seen)

    for raw_line in WORD_BANK_FILE.read_text(encoding="utf-8").splitlines():
        add_term(raw_line)

    _load_custom_banned_words(terms, seen)
    return terms


def _load_custom_banned_words(terms: list[str], seen: set[str]) -> list[str]:
    try:
        from database import list_custom_banned_words
    except Exception:
        return terms

    for custom_term in list_custom_banned_words():
        cleaned = custom_term.strip()
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        seen.add(lowered)
        terms.append(cleaned)

    return terms


def build_banned_words_prompt_section() -> str:
    banned_terms = load_banned_word_bank()
    if not banned_terms:
        return ""

    banned_lines = "\n".join(f"- {term}" for term in banned_terms)
    return f"""
Forbidden word bank:
- Never use any of the following banned words or phrases anywhere in the response.
- This rule applies to titles, meta descriptions, headings, body copy, CTAs, labels, and summaries.
- If a sentence would naturally use one of them, rewrite the sentence to avoid it completely.
{banned_lines}
"""


def find_banned_terms_in_text(text: str) -> list[str]:
    content = text or ""
    found = []

    for term in load_banned_word_bank():
        pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        if pattern.search(content):
            found.append(term)

    return found
