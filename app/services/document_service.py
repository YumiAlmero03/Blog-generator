import re
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from flask import make_response


def html_to_docx_paragraph(doc, html_content):
    html_content = html_content.strip()
    if not html_content:
        return

    for line in html_content.split("\n"):
        line = line.strip()
        if not line:
            continue

        if "<h2>" in line:
            text = re.sub(r"</?h2>", "", line)
            doc.add_paragraph(text.strip(), style="Heading 2")
            continue

        if "<h3>" in line:
            text = re.sub(r"</?h3>", "", line)
            doc.add_paragraph(text.strip(), style="Heading 3")
            continue

        paragraph = doc.add_paragraph()
        parse_inline_html(paragraph, line)


def parse_inline_html(paragraph, html_text):
    if not html_text:
        return

    html_text = html_text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    parts = re.split(r'(<a\s+href=["\']([^"\']+)["\']>|</a>|<strong>|</strong>|<b>|</b>)', html_text)

    current_bold = False
    current_url = None
    i = 0
    while i < len(parts):
        part = parts[i]

        if not part:
            i += 1
            continue

        if part.startswith("<a"):
            current_url = parts[i + 1] if i + 1 < len(parts) else None
            i += 2
            continue

        if part == "</a>":
            current_url = None
            i += 1
            continue

        if part in ["<strong>", "<b>"]:
            current_bold = True
            i += 1
            continue

        if part in ["</strong>", "</b>"]:
            current_bold = False
            i += 1
            continue

        if part and not part.startswith("<"):
            run = paragraph.add_run(part)
            if current_bold:
                run.bold = True
            if current_url:
                from docx.oxml import OxmlElement
                from docx.oxml.ns import qn

                r = run._element
                r_pr = r.get_or_add_rPr()
                r_style = OxmlElement("w:rStyle")
                r_style.set(qn("w:val"), "Hyperlink")
                r_pr.append(r_style)

                fld_char_1 = OxmlElement("w:fldChar")
                fld_char_1.set(qn("w:fldCharType"), "begin")
                r.addprevious(fld_char_1)

                instr_text = OxmlElement("w:instrText")
                instr_text.set(qn("xml:space"), "preserve")
                instr_text.text = f'HYPERLINK "{current_url}"'
                r.addprevious(instr_text)

                fld_char_2 = OxmlElement("w:fldChar")
                fld_char_2.set(qn("w:fldCharType"), "end")
                r.addnext(fld_char_2)
        i += 1


def build_docx_response(title: str, keyword: str, supporting_keyword: str, meta_description: str, content_html: str):
    doc = Document()

    title_para = doc.add_paragraph(title, style="Heading 1")
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph(f"Keyword: {keyword}")
    if supporting_keyword:
        doc.add_paragraph(f"Supporting Keyword: {supporting_keyword}")
    doc.add_paragraph(f"Meta Description: {meta_description}")
    doc.add_paragraph()
    html_to_docx_paragraph(doc, content_html)

    doc_io = BytesIO()
    doc.save(doc_io)
    doc_io.seek(0)

    filename = title.replace(" ", "_")[:50] or "blog_post"
    response = make_response(doc_io.getvalue())
    response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    response.headers["Content-Disposition"] = f"attachment; filename={filename}.docx"
    return response
