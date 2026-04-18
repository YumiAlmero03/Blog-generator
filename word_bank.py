import re
from pathlib import Path


WORD_BANK_FILE = Path(__file__).resolve().parent / "banned_words.txt"


def load_banned_word_bank() -> list[str]:
    if not WORD_BANK_FILE.exists():
        return []

    terms = []
    seen = set()

    for raw_line in WORD_BANK_FILE.read_text(encoding="utf-8").splitlines():
        cleaned = raw_line.strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        lowered = cleaned.lower()
        if lowered in seen:
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
