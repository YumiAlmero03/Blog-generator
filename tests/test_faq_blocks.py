import pytest

from app.services.faq_block_service import convert_faq_blocks
from app.services.content_format_service import markdown_to_html, html_to_gutenberg
from app.services.post_export_service import normalize_post, export_post


@pytest.mark.parametrize('heading', ['FAQ', 'FAQs', 'Frequently Asked Questions', 'Product FAQs'])
def test_faq_conversion_preserves_answers_links_and_following_sections(heading):
    before = '<p>Intro</p>'
    after = '<h2>Conclusion</h2><p>Finish</p>'
    source = before + f'<h2>{heading}</h2><p>FAQ introduction.</p><h3>How does it work?</h3><p>Read <a href="/guide" rel="noopener">our guide</a>.</p><ul><li>Step one</li></ul><h3>Is it free?</h3><p>Yes.</p>' + after
    result = convert_faq_blocks(source)
    assert result.startswith(before + '<section class="faq-block"')
    assert result.endswith('</section>' + after)
    assert result.count('<details ') == 2
    assert '<summary>How does it work?</summary>' in result
    assert '<a href="/guide" rel="noopener">our guide</a>' in result
    assert '<ul><li>Step one</li></ul>' in result
    assert 'FAQ introduction.' in result
    assert convert_faq_blocks(result) == result


def test_bold_questions_and_markdown_generation():
    result = markdown_to_html('## FAQs\n\n**Can I start?**\n\nYes.\n\n**What next?**\n\nRead the guide.')
    assert result.count('<details ') == 2
    assert '<summary>Can I start?</summary>' in result


@pytest.mark.parametrize('source', [
    '<h2>Guide</h2><h3>Question?</h3><p>Answer</p>',
    '<p>FAQ is mentioned in prose.</p><h3>Question?</h3><p>Answer</p>',
    '<h2>FAQ</h2><p>No question structure.</p>',
    '<h2>FAQ</h2><h3>Missing answer?</h3>',
    '<h2>FAQ</h2><h3>One?</h3><p>Yes.</p><h3>Two?</h3>',
])
def test_unrelated_or_incomplete_content_is_unchanged(source):
    assert convert_faq_blocks(source) == source


def test_gutenberg_contains_one_portable_html_faq_block():
    source = '<h2>FAQ</h2><h3>Question?</h3><p>Answer</p><h2>End</h2><p>Done</p>'
    result = html_to_gutenberg(source)
    faq = result.split('<!-- /wp:html -->')[0]
    assert faq.startswith('<!-- wp:html --><section')
    assert '<!-- wp:paragraph -->' not in faq
    assert '<!-- wp:heading --><h2>End</h2>' in result


def test_saved_and_exported_content_uses_python_faq_conversion():
    post = normalize_post({'generator': 'blog', 'selected_title': 'Guide', 'category': 'General',
                           'meta_description_choice': 'Description',
                           'content_html': '<h2>FAQ</h2><h3>Question?</h3><p>Answer with <a href="/guide">guide</a>.</p>'})
    assert '<summary>Question?</summary>' in post['content_html']
    assert 'nofollow' not in post['content_html']
    assert b'faq-block' in export_post(post, 'json')[0]
    assert b'faq-block' in export_post(post, 'wordpress')[0]
