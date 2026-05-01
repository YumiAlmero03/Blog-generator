from html import unescape
from html.parser import HTMLParser
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from flask import make_response


class HtmlToDocxParser(HTMLParser):
    def __init__(self, doc: Document):
        super().__init__(convert_charrefs=True)
        self.doc = doc
        self.current_paragraph = None
        self.current_href = None
        self.bold_depth = 0
        self.list_stack: list[str] = []
        self.in_list_item = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == "h1":
            self._start_paragraph(style="Heading 1")
        elif tag == "h2":
            self._start_paragraph(style="Heading 2")
        elif tag == "h3":
            self._start_paragraph(style="Heading 3")
        elif tag == "p":
            self._start_paragraph()
        elif tag == "ul":
            self.list_stack.append("bullet")
        elif tag == "ol":
            self.list_stack.append("number")
        elif tag == "li":
            style = "List Bullet" if self._current_list_type() == "bullet" else "List Number"
            self._start_paragraph(style=style)
            self.in_list_item = True
        elif tag == "br":
            if self.current_paragraph is None:
                self._start_paragraph()
            self.current_paragraph.add_run().add_break()
        elif tag in {"strong", "b"}:
            self.bold_depth += 1
        elif tag == "a":
            self.current_href = attrs_dict.get("href", "")

    def handle_endtag(self, tag):
        if tag in {"h1", "h2", "h3", "p", "li"}:
            self.current_paragraph = None
        if tag == "li":
            self.in_list_item = False
        elif tag in {"ul", "ol"} and self.list_stack:
            self.list_stack.pop()
        elif tag in {"strong", "b"} and self.bold_depth > 0:
            self.bold_depth -= 1
        elif tag == "a":
            self.current_href = None

    def handle_data(self, data):
        text = unescape(data)
        if not text:
            return

        if self.current_paragraph is None:
            if not text.strip():
                return
            self._start_paragraph()

        if self.current_href:
            self._add_hyperlink(self.current_paragraph, text, self.current_href, bold=self.bold_depth > 0)
            return

        run = self.current_paragraph.add_run(text)
        if self.bold_depth > 0:
            run.bold = True

    def _start_paragraph(self, style=None):
        self.current_paragraph = self.doc.add_paragraph(style=style)
        return self.current_paragraph

    def _current_list_type(self):
        if not self.list_stack:
            return None
        return self.list_stack[-1]

    def _add_hyperlink(self, paragraph, text: str, url: str, bold: bool = False):
        from docx.opc.constants import RELATIONSHIP_TYPE as RT
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        part = paragraph.part
        relation_id = part.relate_to(url, RT.HYPERLINK, is_external=True)

        hyperlink = OxmlElement("w:hyperlink")
        hyperlink.set(qn("r:id"), relation_id)

        run = OxmlElement("w:r")
        run_properties = OxmlElement("w:rPr")

        run_style = OxmlElement("w:rStyle")
        run_style.set(qn("w:val"), "Hyperlink")
        run_properties.append(run_style)

        if bold:
            bold_element = OxmlElement("w:b")
            run_properties.append(bold_element)

        run.append(run_properties)

        text_element = OxmlElement("w:t")
        text_element.text = text
        run.append(text_element)
        hyperlink.append(run)
        paragraph._p.append(hyperlink)


def html_to_docx_paragraph(doc, html_content):
    cleaned = (html_content or "").strip()
    if not cleaned:
        return

    parser = HtmlToDocxParser(doc)
    parser.feed(cleaned)
    parser.close()


def build_docx_response(
    title: str,
    keyword: str,
    supporting_keyword: str,
    meta_description: str,
    content_html: str,
    medium_name: str = "",
    tags: str = "",
):
    doc = Document()

    title_para = doc.add_paragraph(title, style="Heading 1")
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    metadata_paragraph = doc.add_paragraph()
    metadata_paragraph.add_run("Keyword: ").bold = True
    metadata_paragraph.add_run(keyword)

    if supporting_keyword:
        supporting_paragraph = doc.add_paragraph()
        supporting_paragraph.add_run("Supporting Keyword: ").bold = True
        supporting_paragraph.add_run(supporting_keyword)

    if medium_name:
        medium_paragraph = doc.add_paragraph()
        medium_paragraph.add_run("Medium: ").bold = True
        medium_paragraph.add_run(medium_name)

    meta_paragraph = doc.add_paragraph()
    meta_paragraph.add_run("Meta Description: ").bold = True
    meta_paragraph.add_run(meta_description)

    if tags:
        tags_paragraph = doc.add_paragraph()
        tags_paragraph.add_run("Tags: ").bold = True
        tags_paragraph.add_run(tags)

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
