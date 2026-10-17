"""Apply article link relationships without rewriting the surrounding HTML."""
import html
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit


def _host(url):
    try:
        return (urlsplit(url).hostname or '').lower().removeprefix('www.')
    except ValueError:
        return ''


def apply_article_link_rules(content, links=None, money_site_url=''):
    records = [{**item, 'type': item.get('type') or 'internal'}
               for item in (links or []) if isinstance(item, dict)]
    internal_hosts = {_host(item.get('url', '')) for item in records if item.get('type') == 'internal'} - {''}
    explicit = {item.get('url', '').rstrip('/'): item.get('type') for item in records}
    money_host = _host(money_site_url)

    class AnchorParser(HTMLParser):
        attrs = []
        def handle_starttag(self, tag, attrs):
            self.attrs = attrs

    def replace(match):
        parser = AnchorParser()
        parser.feed(match.group(0))
        attrs = dict(parser.attrs)
        href = attrs.get('href') or ''
        host = _host(href)
        kind = explicit.get(href.rstrip('/'))
        relative = not urlsplit(href).scheme and not href.startswith('//')
        internal = relative or kind == 'internal' or (kind not in {'external', 'reference'} and host in internal_hosts)
        # An explicit Internal selection must win over money-site domain matching.
        money = kind != 'internal' and bool(host and host == money_host) and (
            href.rstrip('/') == money_site_url.rstrip('/') or host not in internal_hosts
        )
        nofollow = money or not internal
        rel = [token for token in (attrs.get('rel') or '').split() if token.lower() != 'nofollow']
        if nofollow:
            rel.append('nofollow')
        if attrs.get('target') == '_blank':
            rel.extend(token for token in ('noopener', 'noreferrer') if token not in rel)
        attrs.pop('rel', None)
        if rel:
            attrs['rel'] = ' '.join(dict.fromkeys(rel))
        return '<a' + ''.join(' ' + key + ('' if value is None else '="' + html.escape(value, quote=True) + '"') for key, value in attrs.items()) + '>'

    return re.sub(r'<a\b(?:[^>\"\']|"[^"]*"|\'[^\']*\')*>', replace, content or '', flags=re.I)
