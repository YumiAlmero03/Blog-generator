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
