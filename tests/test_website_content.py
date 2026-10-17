import json
import re

import pytest
from flask import Flask

from app.controllers import website_content_controller as controller
from app.services import website_content_service as service
from app.services.seo_checker_service import FetchResult


def test_extract_metadata_and_readable_content():
    page, links = service.extract_page('''<html><head><title>A &amp; B</title>
      <meta name="description" content="A description">
      <script type="application/ld+json">{"@graph":[{"datePublished":"2026-01-02"}]}</script>
      </head><body><nav>Navigation</nav><article><h1>Heading</h1><p>Full content.</p>
      <script>secretScript()</script></article></body></html>''', 'https://example.com/blog/a')
    assert page['title'] == 'A & B'
    assert page['post_date'] == '2026-01-02'
    assert page['meta_description'] == 'A description'
    assert 'Full content.' in page['content']
    assert 'Navigation' not in page['content']
    assert 'secretScript' not in page['content']


def test_dates_missing_and_time_fallback():
    assert service.extract_page('<title>No date</title>', 'https://example.com/a')[0]['post_date'] == ''
    assert service.extract_page('<time datetime="2026-02-03">Feb 3</time>', 'https://example.com/a')[0]['post_date'] == '2026-02-03'


def test_crawl_combines_sitemaps_links_and_pagination_with_scope(monkeypatch):
    responses = {
        '/sitemap.xml': '<urlset><url><loc>https://example.com/blogs/sitemap-post</loc></url><url><loc>https://example.com/blogs-other/no</loc></url></urlset>',
        '/blogs': '<a href="/blogs/a#part">A</a><a href="/blogs?page=2">Next</a><a href="https://other.com/blogs/a">Other</a>',
        '/blogs?page=2': '<a href="/blogs/b">B</a><a href="/blogs/a">A again</a>',
        '/blogs/a': '<title>A</title><article>Full A</article>',
        '/blogs/b': '<title>B</title>',
        '/blogs/sitemap-post': '<title>Sitemap post</title>',
    }
    fetched = []
    def fetch(url):
        fetched.append(url)
        path = url.removeprefix('https://example.com')
        return FetchResult(url, 200 if path in responses else 404, 'application/xml' if path.endswith('.xml') else 'text/html', responses.get(path, ''))
    monkeypatch.setattr(service, 'fetch_url', fetch)
    result = service.collect_website_content('example.com/blogs')
    assert {page['title'] for page in result['pages']} == {'A', 'B', 'Sitemap post'}
    assert fetched.count('https://example.com/blogs/a') == 1
    assert not any('blogs-other' in url or 'other.com' in url for url in fetched)


def test_partial_failure_and_limit_are_reported(monkeypatch):
    def fetch(url):
        if url.endswith('/blogs'):
            return FetchResult(url, 200, 'text/html', '<a href="/blogs/bad">Bad</a><a href="/blogs/a">A</a><a href="/blogs/b">B</a>')
        if url.endswith('/a') or url.endswith('/b'):
            return FetchResult(url, 200, 'text/html', '<title>Post</title>')
        raise ValueError('private internal error')
    monkeypatch.setattr(service, 'fetch_url', fetch)
    result = service.collect_website_content('example.com/blogs', limit=1)
    assert len(result['pages']) == 1
    assert len(result['errors']) == 1
    assert 'private internal error' not in str(result)
    assert 'partial results' in result['notes'][0]


@pytest.mark.parametrize('url', ['https://user:pass@example.com/blogs', 'file:///etc/passwd', 'https://example.com:bad', ''])
def test_invalid_urls(url):
    with pytest.raises(ValueError):
        service.normalize_url(url)


def test_page_and_export_payload_exclude_content(monkeypatch):
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.add_url_rule('/website-content', view_func=controller.website_content, methods=['GET', 'POST'])
    client = app.test_client()
    assert client.get('/website-content').status_code == 200
    monkeypatch.setattr(controller, 'collect_website_content', lambda *args: {
        'pages': [{'url': 'https://example.com/blogs/a', 'post_date': '2026-01-02', 'title': '<script>alert(1)</script>', 'meta_description': 'Description', 'content': 'CONTENT MUST NOT BE EXPORTED'}],
        'errors': [], 'notes': []})
    response = client.post('/website-content', data={'site_url': 'example.com/blogs', 'limit': '10'})
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
    payload = re.search(r'id="website-content-rows" type="application/json">(.*?)</script>', html, re.S)[1]
    assert json.loads(payload) == [['2026-01-02', '<script>alert(1)</script>', 'Description']]
    assert 'CONTENT MUST NOT BE EXPORTED' not in payload
    assert 'Download CSV' in html
    assert b'Enter a valid' in client.post('/website-content', data={'limit': 'bad'}).data


def test_redirects_apply_public_url_validation(monkeypatch):
    def reject(url):
        raise ValueError('Private destination')
    monkeypatch.setattr(service, '_validate_public_http_url', reject)
    with pytest.raises(ValueError, match='Private destination'):
        service._PublicRedirectHandler().redirect_request(None, None, 302, '', {}, 'http://127.0.0.1/')
