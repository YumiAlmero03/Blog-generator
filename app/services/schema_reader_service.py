from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from app.services.seo_checker_service import FETCH_TIMEOUT, SSL_CONTEXT, USER_AGENT, _validate_public_http_url


def _validate_url(url):
    parsed = urlparse(url)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Use a URL without credentials.")
    _validate_public_http_url(url)


class _PublicRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_schema_page(url):
    """Read public page HTML without executing scripts or following private redirects."""
    _validate_url(url)
    opener = build_opener(_PublicRedirectHandler(), HTTPSHandler(context=SSL_CONTEXT))
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with opener.open(request, timeout=FETCH_TIMEOUT) as response:
        if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
            raise ValueError("That URL did not return an HTML page.")
        raw = response.read(2_000_000)
        charset = response.headers.get_content_charset() or "utf-8"
        return {"html": raw.decode(charset, errors="replace"), "final_url": response.geturl()}
