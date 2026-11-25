from app.services.content_format_service import markdown_to_html


def test_table_keeps_surrounding_content_and_escapes_cells():
    result = markdown_to_html('Intro\n\n| Option | Detail |\n| --- | --- |\n| **A** | <script>alert(1)</script> |\n\n## Next\nText')
    assert result.startswith('<p>Intro</p><table>')
    assert '<th scope="col">Option</th>' in result
    assert '<td><strong>A</strong></td>' in result
    assert '&lt;script&gt;' in result
    assert result.endswith('</table><h2>Next</h2><p>Text</p>')


def test_ordinary_pipes_are_not_tables():
    assert markdown_to_html('A | B\nJust prose') == '<p>A | B Just prose</p>'


def test_table_supports_alignment_and_escaped_pipes():
    result = markdown_to_html('| A | B |\n| :--- | ---: |\n| x\\|y | z |')
    assert '<td>x|y</td><td>z</td>' in result


def test_numbered_sequences_stay_ordered_and_bullets_stay_unordered():
    result = markdown_to_html('1. First step\n2. Second step\n3. Third step\n\n- One option\n- Another option')
    assert result == '<ol><li>First step</li><li>Second step</li><li>Third step</li></ol><ul><li>One option</li><li>Another option</li></ul>'


def test_switching_list_types_without_blank_lines_keeps_separate_lists():
    result = markdown_to_html('- Option\n1. Step\n2. Next step\n- Other option')
    assert result == '<ul><li>Option</li></ul><ol><li>Step</li><li>Next step</li></ol><ul><li>Other option</li></ul>'


def test_ordered_list_exports_preserve_numbering():
    from app.services.content_format_service import html_to_gutenberg, html_to_markdown
    source = '<ol><li>First <strong>step</strong></li><li>Next step</li></ol>'
    assert html_to_markdown(source) == '1. First **step**\n2. Next step'
    assert '<!-- wp:list {"ordered":true} -->' in html_to_gutenberg(source)


def test_two_dash_markdown_table_separator_supported():
    result = markdown_to_html('| Match | Kickoff |\n| -- | -- |\n| Como vs Cagliari | 14:00 |')
    assert '<table><thead><tr><th scope="col">Match</th><th scope="col">Kickoff</th></tr></thead><tbody><tr><td>Como vs Cagliari</td><td>14:00</td></tr></tbody></table>' == result


def test_convert_markdown_tables_to_html_preserves_surrounding_html():
    from app.services.content_format_service import convert_markdown_tables_to_html

    source = '<h2>Schedule</h2>\n| Match | Date |\n| --- | --- |\n| Lazio vs Lecce | Sat, 21 Nov |\n<p>Coverage continues.</p>'
    converted = convert_markdown_tables_to_html(source)
    assert '<h2>Schedule</h2>' in converted
    assert '<table><thead><tr><th scope="col">Match</th><th scope="col">Date</th></tr></thead><tbody><tr><td>Lazio vs Lecce</td><td>Sat, 21 Nov</td></tr></tbody></table>' in converted
    assert '<p>Coverage continues.</p>' in converted


def test_html_to_markdown_preserves_table_and_links():
    from app.services.content_format_service import html_to_markdown

    source = '<h2>Fixtures</h2><table><thead><tr><th>Match</th><th>Guide</th></tr></thead><tbody><tr><td>Napoli vs Torino</td><td><a href="https://site.test/preview">Preview</a></td></tr></tbody></table>'
    md = html_to_markdown(source)
    assert '| Match | Guide |' in md
    assert '| --- | --- |' in md
    assert '| Napoli vs Torino | [Preview](https://site.test/preview) |' in md


def test_html_to_docx_creates_real_word_table():
    from docx import Document
    from app.services.document_service import html_to_docx_paragraph

    doc = Document()
    html_to_docx_paragraph(doc, '<p>Lead text</p><table><thead><tr><th>Match</th><th>Time</th></tr></thead><tbody><tr><td>Como vs Cagliari</td><td>14:00</td></tr></tbody></table><p>End text</p>')
    assert len(doc.tables) == 1
    table = doc.tables[0]
    assert table.rows[0].cells[0].text == 'Match'
    assert table.rows[0].cells[1].text == 'Time'
    assert table.rows[1].cells[0].text == 'Como vs Cagliari'
    assert table.rows[1].cells[1].text == '14:00'
    assert any(p.text == 'Lead text' for p in doc.paragraphs)
    assert any(p.text == 'End text' for p in doc.paragraphs)
