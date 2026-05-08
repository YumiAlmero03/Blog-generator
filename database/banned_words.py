from database.common import get_connection


def normalize_banned_word(term: str) -> str:
    return " ".join((term or "").strip().lower().split())


def list_custom_banned_words() -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT term FROM banned_words ORDER BY LOWER(term)"
        ).fetchall()
        return [row["term"] for row in rows if row["term"].strip()]


def replace_custom_banned_words(terms: list[str]) -> list[str]:
    cleaned_terms = []
    seen = set()
    for term in terms:
        cleaned = " ".join((term or "").strip().split())
        normalized = normalize_banned_word(cleaned)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned_terms.append(cleaned)

    with get_connection() as connection:
        connection.execute("DELETE FROM banned_words")
        connection.executemany(
            "INSERT INTO banned_words (term, normalized_term) VALUES (?, ?)",
            [(term, normalize_banned_word(term)) for term in cleaned_terms],
        )

    return cleaned_terms
