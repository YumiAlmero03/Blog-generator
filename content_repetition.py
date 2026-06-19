import re


def repeated_content_issue(content: str) -> str:
    text = _strip_markup(content)
    paragraphs = [_normalize_repeat_unit(item) for item in _paragraphs(content)]
    paragraph_counts = _duplicate_counts(item for item in paragraphs if _word_count(item) >= 10)
    if paragraph_counts:
        paragraph, count = paragraph_counts[0]
        return f"Repeated paragraph found {count} times: {_shorten(paragraph)}"

    sentences = [_normalize_repeat_unit(item) for item in _sentences(text)]
    sentence_counts = _duplicate_counts(item for item in sentences if _word_count(item) >= 8)
    if sentence_counts:
        sentence, count = sentence_counts[0]
        return f"Repeated sentence found {count} times: {_shorten(sentence)}"
    return ""


def _paragraphs(content: str) -> list[str]:
    raw = content or ""
    html_paragraphs = re.findall(r"<p\b[^>]*>(.*?)</p>", raw, flags=re.IGNORECASE | re.DOTALL)
    if html_paragraphs:
        return [_strip_markup(item) for item in html_paragraphs]
    blocks = re.split(r"\n\s*\n|(?:^|\n)#{2,3}\s+", raw)
    return [_strip_markup(item) for item in blocks]


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", text or "") if item.strip()]


def _normalize_repeat_unit(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", _strip_markup(text)).strip().lower()
    return re.sub(r"^[\"'“”‘’\s]+|[\"'“”‘’\s]+$", "", cleaned)


def _duplicate_counts(items) -> list[tuple[str, int]]:
    counts = {}
    for item in items:
        if not item:
            continue
        counts[item] = counts.get(item, 0) + 1
    return sorted(
        ((item, count) for item, count in counts.items() if count > 1),
        key=lambda item: item[1],
        reverse=True,
    )


def _strip_markup(content: str) -> str:
    return re.sub(r"<[^>]+>|[#*_>`~-]+", " ", content or "")


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def _shorten(text: str, limit: int = 120) -> str:
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."
