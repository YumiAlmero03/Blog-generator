import re
from html.parser import HTMLParser

from word_bank import find_banned_terms_in_text


class GeneratedContentParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.headings = {f"h{level}": [] for level in range(1, 7)}
        self.links = []
        self.images = []
        self.text_parts = []
        self._tag_stack = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_dict = {name.lower(): (value or "") for name, value in attrs}
        self._tag_stack.append(tag)
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "a" and attrs_dict.get("href", "").strip():
            self.links.append(attrs_dict.get("href", "").strip())
        if tag == "img":
            self.images.append(
                {
                    "src": attrs_dict.get("src", "").strip(),
                    "alt": attrs_dict.get("alt", "").strip(),
                    "has_alt": "alt" in attrs_dict and bool(attrs_dict.get("alt", "").strip()),
                }
            )

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data):
        text = " ".join(data.split())
        if not text or self._skip_depth:
            return
        current_tag = self._tag_stack[-1] if self._tag_stack else ""
        if current_tag in self.headings:
            self.headings[current_tag].append(text)
        elif current_tag not in {"head", "meta", "link"}:
            self.text_parts.append(text)

    @property
    def text(self) -> str:
        return " ".join(self.text_parts).strip()


def analyze_generated_content(
    content: str,
    title: str = "",
    keyword: str = "",
    meta_description: str = "",
    min_words: int = 0,
    max_words: int = 0,
    required_url: str = "",
) -> dict:
    parser = GeneratedContentParser()
    parser.feed(content or "")
    visible_text = parser.text or _strip_markup(content)
    word_count = _word_count(visible_text)
    keyword_count = _phrase_count(visible_text, keyword)
    missing_alt_count = sum(1 for image in parser.images if not image["has_alt"])
    banned_terms = find_banned_terms_in_text("\n".join([title or "", meta_description or "", visible_text]))
    required_url_count = (content or "").count(required_url) if required_url else 0

    checks = [
        _check(
            "Word count",
            _range_status(word_count, min_words, max_words),
            _range_detail(word_count, min_words, max_words),
            "Adjust section depth so the content fits the configured word range.",
        ),
        _check(
            "Headings",
            "pass" if sum(len(items) for items in parser.headings.values()) >= 2 else "warn",
            f"{len(parser.headings['h1'])} H1, {len(parser.headings['h2'])} H2, {len(parser.headings['h3'])} H3",
            "Use clear H2/H3 sections so the content is easier to scan.",
        ),
        _check(
            "Keyword usage",
            "pass" if not keyword or 1 <= keyword_count <= 5 else "warn",
            f"{keyword_count} exact use(s)" if keyword else "No keyword supplied",
            "Use the main keyword naturally without repeating it in every section.",
        ),
        _check(
            "Meta length",
            "pass" if not meta_description or 120 <= len(meta_description) <= 140 else "warn",
            f"{len(meta_description)} characters" if meta_description else "No meta description selected",
            "Keep meta descriptions useful and within 120-140 characters.",
        ),
        _check(
            "Images",
            "pass" if missing_alt_count == 0 else "warn",
            f"{missing_alt_count} of {len(parser.images)} images missing alt text",
            "Add descriptive alt text to meaningful generated images.",
        ),
        _check(
            "Links",
            "pass" if not required_url or required_url_count == 1 else "warn",
            f"{len(parser.links)} link(s); required URL appears {required_url_count} time(s)" if required_url else f"{len(parser.links)} link(s)",
            "Check that required URLs appear exactly once when the generator asks for it.",
        ),
        _check(
            "Banned terms",
            "pass" if not banned_terms else "fail",
            "None found" if not banned_terms else ", ".join(banned_terms[:8]),
            "Regenerate or edit any banned terms before publishing.",
        ),
    ]

    return {
        "word_count": word_count,
        "h1_count": len(parser.headings["h1"]),
        "h2_count": len(parser.headings["h2"]),
        "h3_count": len(parser.headings["h3"]),
        "link_count": len(parser.links),
        "image_count": len(parser.images),
        "missing_alt_count": missing_alt_count,
        "keyword_count": keyword_count,
        "banned_terms": banned_terms,
        "checks": checks,
    }


def _check(name: str, status: str, detail: str, recommendation: str) -> dict:
    return {"name": name, "status": status, "detail": detail, "recommendation": recommendation}


def _range_status(word_count: int, min_words: int, max_words: int) -> str:
    if min_words and word_count < min_words:
        return "warn"
    if max_words and word_count > max_words:
        return "warn"
    return "pass"


def _range_detail(word_count: int, min_words: int, max_words: int) -> str:
    if min_words and max_words:
        return f"{word_count} words, target {min_words}-{max_words}"
    if min_words:
        return f"{word_count} words, minimum {min_words}"
    if max_words:
        return f"{word_count} words, maximum {max_words}"
    return f"{word_count} words"


def _strip_markup(content: str) -> str:
    return re.sub(r"<[^>]+>|[#*_>`~-]+", " ", content or "")


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


def _phrase_count(text: str, phrase: str) -> int:
    cleaned_phrase = (phrase or "").strip()
    if not cleaned_phrase:
        return 0
    return len(re.findall(re.escape(cleaned_phrase), text or "", flags=re.IGNORECASE))
