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
