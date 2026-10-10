"""Portable section styling for generated page HTML."""
from html.parser import HTMLParser


class _PageBlocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.blocks = []
        self.parts = []
        self.depth = 0
        self.tag = ""

    def handle_starttag(self, tag, attrs):
        if not self.parts:
            self.tag = tag
        self.parts.append(self.get_starttag_text())
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.depth += 1
        self.flush()

    def handle_startendtag(self, tag, attrs):
        self.parts.append(self.get_starttag_text())
        self.flush()

    def handle_endtag(self, tag):
        self.parts.append(f"</{tag}>")
        self.depth = max(0, self.depth - 1)
        self.flush()

    def handle_data(self, data):
        self.parts.append(data)
        self.flush()

    def handle_entityref(self, name):
        self.handle_data(f"&{name};")

    def handle_charref(self, name):
        self.handle_data(f"&#{name};")

    def handle_comment(self, data):
        self.handle_data(f"<!--{data}-->")

    def flush(self):
        if not self.depth and self.parts:
            self.blocks.append((self.tag, "".join(self.parts)))
            self.parts = []
            self.tag = ""


def group_page_html(content: str) -> str:
    """Group top-level headings without changing their text, links or hierarchy.

    Inline styles deliberately travel with copied HTML into WordPress. Inherited
    text/background colors let the destination theme control light/dark mode.
    """
    if not content or 'data-page-group="' in content:
        return content
    parser = _PageBlocks()
    parser.feed(content)
    parser.close()
    if parser.parts:  # Leave incomplete drafts intact until valid HTML is available.
        return content
    groups = []
    parts = []
    hero = False

    def finish():
        if not "".join(parts).strip():
            return
        kind = "hero" if hero else "section"
        style = (
            "box-sizing:border-box;min-width:0;max-width:100%;"
            "margin:0 0 24px;padding:clamp(16px,4vw,32px);"
            "border:1px solid currentColor;border-radius:20px;"
            "color:inherit;background:inherit;overflow-wrap:anywhere;"
        )
        if hero:
            style += "border-top-width:4px;"
        groups.append(f'<div class="generated-page-{kind}" data-page-group="{kind}" style="{style}">' + "".join(parts) + "</div>")

    for tag, block in parser.blocks:
        if tag in {"h1", "h2"}:
            finish()
            parts = []
            hero = tag == "h1"
        parts.append(block)
    finish()
    return "".join(groups)
