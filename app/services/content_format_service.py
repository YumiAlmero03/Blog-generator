import html
import re


def markdown_to_output(content: str, output_format: str = "html") -> str:
    cleaned_format = (output_format or "html").strip().lower()
    if cleaned_format == "markdown":
        return content or ""
    if cleaned_format == "gutenberg":
        return html_to_gutenberg(markdown_to_html(content or ""))
    if cleaned_format == "text":
        return markdown_to_text(content or "")
    return markdown_to_html(content or "")


def markdown_to_html(markdown: str) -> str:
    lines = (markdown or "").replace("\r\n", "\n").split("\n")
    blocks = []
    paragraph = []
    list_items = []
    quote_lines = []

    def flush_paragraph():
        nonlocal paragraph
        if paragraph:
            text = " ".join(item.strip() for item in paragraph if item.strip())
            blocks.append(f"<p>{_inline_markdown_to_html(text)}</p>")
            paragraph = []

    def flush_list():
        nonlocal list_items
        if list_items:
            items = "".join(f"<li>{_inline_markdown_to_html(item)}</li>" for item in list_items)
            blocks.append(f"<ul>{items}</ul>")
            list_items = []

    def flush_quote():
        nonlocal quote_lines
        if quote_lines:
            text = " ".join(item.strip() for item in quote_lines if item.strip())
            blocks.append(f"<blockquote>{_inline_markdown_to_html(text)}</blockquote>")
            quote_lines = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            flush_list()
            flush_quote()
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        unordered = re.match(r"^[-*]\s+(.+)$", line)
        ordered = re.match(r"^\d+\.\s+(.+)$", line)

        if heading:
            flush_paragraph()
            flush_list()
            flush_quote()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_inline_markdown_to_html(heading.group(2).strip())}</h{level}>")
        elif unordered or ordered:
            flush_paragraph()
            flush_quote()
            list_items.append((unordered or ordered).group(1).strip())
        elif line.startswith(">"):
            flush_paragraph()
            flush_list()
            quote_lines.append(line.lstrip(">").strip())
        elif line.startswith("<") and line.endswith(">"):
            flush_paragraph()
            flush_list()
            flush_quote()
            blocks.append(line)
        else:
            flush_list()
            flush_quote()
            paragraph.append(line)

    flush_paragraph()
    flush_list()
    flush_quote()
    return "".join(blocks)


def html_to_gutenberg(html_content: str) -> str:
    output = html_content or ""
    output = re.sub(r"<p\b([^>]*)>(.*?)</p>", r"<!-- wp:paragraph --><p\1>\2</p><!-- /wp:paragraph -->", output, flags=re.IGNORECASE | re.DOTALL)
    output = re.sub(r"<h2\b([^>]*)>(.*?)</h2>", r"<!-- wp:heading --><h2\1>\2</h2><!-- /wp:heading -->", output, flags=re.IGNORECASE | re.DOTALL)
    output = re.sub(r"<h3\b([^>]*)>(.*?)</h3>", r"<!-- wp:heading {\"level\":3} --><h3\1>\2</h3><!-- /wp:heading -->", output, flags=re.IGNORECASE | re.DOTALL)
    output = re.sub(r"<ul\b([^>]*)>(.*?)</ul>", r"<!-- wp:list --><ul\1>\2</ul><!-- /wp:list -->", output, flags=re.IGNORECASE | re.DOTALL)
    output = re.sub(r"<blockquote\b([^>]*)>(.*?)</blockquote>", r"<!-- wp:quote --><blockquote\1>\2</blockquote><!-- /wp:quote -->", output, flags=re.IGNORECASE | re.DOTALL)
    return output


def html_to_markdown(html_content: str) -> str:
    text = html_content or ""
    text = re.sub(r"<h1\b[^>]*>(.*?)</h1>", r"# \1\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<h2\b[^>]*>(.*?)</h2>", r"## \1\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<h3\b[^>]*>(.*?)</h3>", r"### \1\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<li\b[^>]*>(.*?)</li>", r"- \1\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"</ul>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p\b[^>]*>(.*?)</p>", r"\1\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<blockquote\b[^>]*>(.*?)</blockquote>", r"> \1\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<a\b[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", r"[\2](\1)", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<(?:strong|b)\b[^>]*>(.*?)</(?:strong|b)>", r"**\1**", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<(?:em|i)\b[^>]*>(.*?)</(?:em|i)>", r"*\1*", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def markdown_to_text(markdown: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", markdown or "")
    text = re.sub(r"[*_`>#-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def count_markdown_words(markdown: str) -> int:
    text = markdown_to_text(markdown)
    return len(re.findall(r"\b[\w'-]+\b", text))


def count_markdown_heading_level(markdown: str, level: int) -> int:
    hashes = "#" * max(1, min(6, int(level or 1)))
    return len(re.findall(rf"^{re.escape(hashes)}\s+", markdown or "", flags=re.MULTILINE))


def _inline_markdown_to_html(text: str) -> str:
    placeholders = []

    def stash(value: str) -> str:
        placeholders.append(value)
        return f"@@PLACEHOLDER_{len(placeholders) - 1}@@"

    escaped = html.escape(text or "", quote=False)
    escaped = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        lambda match: stash(
            f"<a href='{html.escape(match.group(2), quote=True)}' rel='nofollow noopener noreferrer' target='_blank'>{html.escape(match.group(1), quote=False)}</a>"
        ),
        escaped,
    )
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
    for index, value in enumerate(placeholders):
        escaped = escaped.replace(f"@@PLACEHOLDER_{index}@@", value)
    return escaped
