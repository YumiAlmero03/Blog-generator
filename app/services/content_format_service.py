import html
import re

from app.services.faq_block_service import convert_faq_blocks


def markdown_to_output(content: str, output_format: str = "html") -> str:
    cleaned_format = (output_format or "html").strip().lower()
    if cleaned_format == "markdown":
        return content or ""
    if cleaned_format == "gutenberg":
        return html_to_gutenberg(markdown_to_html(content or ""))
    if cleaned_format == "text":
        return markdown_to_text(content or "")
    return markdown_to_html(content or "")


def _table_cells(line: str) -> list[str]:
    return [cell.strip().replace(r"\|", "|") for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def _markdown_table_headers_and_rows(lines: list[str], start_index: int) -> tuple[list[str], list[list[str]], int] | None:
    if start_index + 1 >= len(lines):
        return None
    line = lines[start_index].strip()
    if "|" not in line:
        return None
    headers = _table_cells(line)
    separators = _table_cells(lines[start_index + 1])
    if len(headers) != len(separators) or not all(re.fullmatch(r":?-{2,}:?", cell) for cell in separators):
        return None
    next_index = start_index + 2
    rows = []
    while next_index < len(lines) and "|" in lines[next_index] and lines[next_index].strip():
        cells = _table_cells(lines[next_index])
        if len(cells) != len(headers):
            break
        rows.append(cells)
        next_index += 1
    return headers, rows, next_index


def _render_table_html(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f'<th scope="col">{_inline_markdown_to_html(cell)}</th>' for cell in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_inline_markdown_to_html(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def convert_markdown_tables_to_html(content: str) -> str:
    lines = (content or "").replace("\r\n", "\n").split("\n")
    output = []
    index = 0
    while index < len(lines):
        parsed = _markdown_table_headers_and_rows(lines, index)
        if parsed:
            headers, rows, next_index = parsed
            output.append(_render_table_html(headers, rows))
            index = next_index
            continue
        output.append(lines[index])
        index += 1
    return "\n".join(output)


def markdown_to_html(markdown: str) -> str:
    lines = (markdown or "").replace("\r\n", "\n").split("\n")
    blocks = []
    paragraph = []
    list_items = []
    list_tag = "ul"
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
            blocks.append(f"<{list_tag}>{items}</{list_tag}>")
            list_items = []

    def flush_quote():
        nonlocal quote_lines
        if quote_lines:
            text = " ".join(item.strip() for item in quote_lines if item.strip())
            blocks.append(f"<blockquote>{_inline_markdown_to_html(text)}</blockquote>")
            quote_lines = []

    index = 0
    while index < len(lines):
        parsed_table = _markdown_table_headers_and_rows(lines, index)
        if parsed_table:
            headers, rows, index = parsed_table
            flush_paragraph()
            flush_list()
            flush_quote()
            blocks.append(_render_table_html(headers, rows))
            continue
        raw_line = lines[index]
        index += 1
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
            next_list_tag = "ol" if ordered else "ul"
            if next_list_tag != list_tag:
                flush_list()
            list_tag = next_list_tag
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
    return convert_faq_blocks("".join(blocks))


def html_to_gutenberg(html_content: str) -> str:
    output = convert_faq_blocks(html_content or "")
    faq_blocks = []
    def stash_faq(match):
        faq_blocks.append(match.group(0))
        return f"@@FAQ_BLOCK_{len(faq_blocks) - 1}@@"
    output = re.sub(r'<section\b[^>]*data-faq-block="true"[^>]*>.*?</section>', stash_faq, output, flags=re.I | re.S)
    output = re.sub(r"<table\b[^>]*>.*?</table>", lambda match: '<!-- wp:table --><figure class="wp-block-table">' + match.group(0) + '</figure><!-- /wp:table -->', output, flags=re.IGNORECASE | re.DOTALL)
    output = re.sub(r"<p\b([^>]*)>(.*?)</p>", r"<!-- wp:paragraph --><p\1>\2</p><!-- /wp:paragraph -->", output, flags=re.IGNORECASE | re.DOTALL)
    output = re.sub(r"<h2\b([^>]*)>(.*?)</h2>", r"<!-- wp:heading --><h2\1>\2</h2><!-- /wp:heading -->", output, flags=re.IGNORECASE | re.DOTALL)
    output = re.sub(r"<h3\b([^>]*)>(.*?)</h3>", r"<!-- wp:heading {\"level\":3} --><h3\1>\2</h3><!-- /wp:heading -->", output, flags=re.IGNORECASE | re.DOTALL)
    output = re.sub(r"<ol\b([^>]*)>(.*?)</ol>", r'<!-- wp:list {"ordered":true} --><ol\1>\2</ol><!-- /wp:list -->', output, flags=re.IGNORECASE | re.DOTALL)
    output = re.sub(r"<ul\b([^>]*)>(.*?)</ul>", r"<!-- wp:list --><ul\1>\2</ul><!-- /wp:list -->", output, flags=re.IGNORECASE | re.DOTALL)
    output = re.sub(r"<blockquote\b([^>]*)>(.*?)</blockquote>", r"<!-- wp:quote --><blockquote\1>\2</blockquote><!-- /wp:quote -->", output, flags=re.IGNORECASE | re.DOTALL)
    for index, block in enumerate(faq_blocks):
        output = output.replace(f"@@FAQ_BLOCK_{index}@@", "<!-- wp:html -->" + block + "<!-- /wp:html -->")
    return output


def html_to_markdown(html_content: str) -> str:
    text = html_content or ""
    text = re.sub(r"<summary\b[^>]*>(.*?)</summary>", r"### \1\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<h1\b[^>]*>(.*?)</h1>", r"# \1\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<h2\b[^>]*>(.*?)</h2>", r"## \1\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<h3\b[^>]*>(.*?)</h3>", r"### \1\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    def ordered_list(match):
        items = re.findall(r"<li\b[^>]*>(.*?)</li>", match.group(1), flags=re.IGNORECASE | re.DOTALL)
        return "\n" + "\n".join(f"{index}. {item}" for index, item in enumerate(items, 1)) + "\n\n"
    text = re.sub(r"<ol\b[^>]*>(.*?)</ol>", ordered_list, text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<li\b[^>]*>(.*?)</li>", r"- \1\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"</ul>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p\b[^>]*>(.*?)</p>", r"\1\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<blockquote\b[^>]*>(.*?)</blockquote>", r"> \1\n\n", text, flags=re.IGNORECASE | re.DOTALL)
    def _table_to_markdown(match):
        row_matches = re.findall(r"<tr\b[^>]*>(.*?)</tr>", match.group(0), flags=re.IGNORECASE | re.DOTALL)
        markdown_rows = []
        col_count = 0
        for row_html in row_matches:
            cells = re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", row_html, flags=re.IGNORECASE | re.DOTALL)
            if not cells:
                continue
            cleaned_cells = []
            for cell_html in cells:
                cell_text = re.sub(r"<br\s*/?>", " ", cell_html, flags=re.IGNORECASE)
                cell_text = re.sub(r"<[^>]+>", "", cell_text)
                cell_text = html.unescape(re.sub(r"\s+", " ", cell_text)).strip().replace("|", r"\|")
                cleaned_cells.append(cell_text)
            col_count = max(col_count, len(cleaned_cells))
            markdown_rows.append("| " + " | ".join(cleaned_cells) + " |")
        if not markdown_rows or not col_count:
            return ""
        separator = "| " + " | ".join(["---"] * col_count) + " |"
        markdown_rows.insert(1, separator)
        return "\n".join(markdown_rows) + "\n\n"

    text = re.sub(r"<a\b[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", r"[\2](\1)", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<(?:strong|b)\b[^>]*>(.*?)</(?:strong|b)>", r"**\1**", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<(?:em|i)\b[^>]*>(.*?)</(?:em|i)>", r"*\1*", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<table\b[^>]*>.*?</table>", _table_to_markdown, text, flags=re.IGNORECASE | re.DOTALL)
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
