from html.parser import HTMLParser

from app.services.article_link_service import apply_article_link_rules


class Links(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.links = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.append(dict(attrs))


def test_internal_external_and_money_site_rules():
    content = '''<p>Read <a href="https://site.test/guide" rel="nofollow sponsored" target="_blank">guide</a>,
    <a href="https://site.test/other" rel="nofollow">other</a>,
    <a href="/local" rel="nofollow">local</a>,
    <a href="https://outside.test/">source</a>,
    <a href="https://money.test/offer">offer</a>.</p>'''
    links = [{'url': 'https://site.test/guide', 'type': 'internal'}]
    result = apply_article_link_rules(content, links, 'https://money.test')
    anchors = Links(result).links
    assert anchors[0]['rel'] == 'sponsored noopener noreferrer'
    assert 'rel' not in anchors[1]
    assert 'rel' not in anchors[2]
    assert anchors[3]['rel'] == 'nofollow'
    assert anchors[4]['rel'] == 'nofollow'
    assert '>guide</a>' in result
    assert apply_article_link_rules(result, links, 'https://money.test') == result


def test_explicit_external_overrides_internal_host_and_preserves_entities():
    content = '<a href="https://site.test/external?a=1&amp;b=2">A &amp; B</a>'
    links = [{'url': 'https://site.test/a', 'type': 'internal'}, {'url': 'https://site.test/external?a=1&b=2', 'type': 'external'}]
    result = apply_article_link_rules(content, links)
    assert Links(result).links[0]['rel'] == 'nofollow'
    assert 'a=1&amp;b=2' in result
    assert '>A &amp; B</a>' in result


def test_internal_selection_wins_on_money_site_domain():
    content = '<a href="https://money.test/guide" rel="nofollow noopener">Guide</a><a href="https://money.test/other" rel="nofollow">Other</a><a href="https://money.test/">Money site</a>'
    records = [{'url': 'https://money.test/guide', 'type': 'internal'}]
    result = Links(apply_article_link_rules(content, records, 'https://money.test/')).links
    assert result[0]['rel'] == 'noopener'
    assert 'rel' not in result[1]
    assert result[2]['rel'] == 'nofollow'


def test_explicit_internal_money_url_stays_followable_in_export():
    import json
    from app.services.post_export_service import normalize_post
    post = normalize_post({
        'generator': 'blog', 'selected_title': 'Guide', 'meta_description_choice': 'Description',
        'category': 'General', 'content_html': '<p><a href="https://money.test/" rel="nofollow">Home</a></p>',
        'links_json': json.dumps([{'url': 'https://money.test/', 'type': 'internal'}]),
        'money_site_url': 'https://money.test/',
    })
    assert 'nofollow' not in post['content_html']
