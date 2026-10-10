from app.services.content_format_service import html_to_markdown, markdown_to_html
from app.services.page_layout_service import group_page_html


def test_groups_keep_related_content_and_are_safe_to_apply_twice():
    html = markdown_to_html('# VIP Center\n\nOverview.\n\n## Period\n\nApril 1.\n\n## Requirements\n\n### Profile\n\n- Link email\n- Link phone')
    result = group_page_html(html)
    assert result.count('data-page-group=') == 3
    assert result.count('<h1>') == 1
    assert '<h3>Profile</h3><ul>' in result
    assert html_to_markdown(result) == html_to_markdown(html)
    assert group_page_html(result) == result


def test_nested_elements_links_and_entities_remain_in_their_section():
    html = '<h2>Terms &amp; Conditions</h2><div><p>See <a href="https://example.com">terms</a>.</p></div><h2>Help</h2><p>Contact us.</p>'
    result = group_page_html(html)
    assert result.count('data-page-group=') == 2
    assert '<div><p>See <a href="https://example.com">terms</a>.</p></div></div>' in result
    assert 'Terms &amp; Conditions' in result


def test_insertable_section_is_one_group_and_incomplete_draft_is_unchanged():
    assert group_page_html('<h2>Requirements</h2><p>Details.</p>').count('data-page-group=') == 1
    assert group_page_html('<div><p>Incomplete') == '<div><p>Incomplete'
    assert group_page_html('') == ''
