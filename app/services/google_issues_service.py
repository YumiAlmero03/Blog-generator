"""Evidence-based Google issue reports; add future checks to GOOGLE_ISSUE_CHECKS."""
from datetime import datetime, timezone
from urllib.parse import urljoin

from app.services.indexnow_service import inspect_google_index_status_by_url_domain
from logger import logger

ISSUE = "Duplicate, Google chose different canonical than user"
SOURCES = [
    {"title": "Google: Page indexing report", "url": "https://support.google.com/webmasters/answer/7440203?hl=en"},
    {"title": "Google: Fix canonicalization issues", "url": "https://developers.google.com/search/docs/crawling-indexing/canonicalization-troubleshooting"},
    {"title": "Google: Specify a canonical URL", "url": "https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls"},
]


def canonical_issue(page, inspection=None, unavailable="Search Console inspection was not enabled."):
    audit = page.get("result") or {}
    stats = audit.get("stats") or {}
    url = page["url"]
    live_url = audit.get("url") or url
    raw_canonical = stats.get("canonical") or ""
    live_canonical = urljoin(live_url, raw_canonical) if raw_canonical else ""
    user = getattr(inspection, "user_canonical", "") if inspection else ""
    google = getattr(inspection, "google_canonical", "") if inspection else ""
    coverage = getattr(inspection, "coverage_state", "") if inspection else ""
    status = "Not verified"
    reason = unavailable
    if inspection and inspection.status != "error":
        if coverage.casefold() == ISSUE.casefold():
            status = "Confirmed by Google"
            reason = "Google reports this exact indexing exclusion for the inspected URL."
        elif user and google and user != google:
            status = "Canonical mismatch detected"
            reason = "Google's indexed user-declared and selected canonical URLs differ. The coverage label below determines the exact indexing issue."
        elif user and google:
            status = "Not detected in indexed data"
            reason = "Google's indexed canonical URLs match. This does not guarantee that the page is indexed or that the current live page matches Google's last crawl."
        else:
            reason = "Google did not return both canonical URLs. Missing data is not evidence that this issue is absent."
    elif inspection:
        reason = inspection.detail
    evidence = [
        {"label": "Inspected URL", "value": url},
        {"label": "Live final URL", "value": live_url},
        {"label": "Live HTML canonical", "value": live_canonical or "Not found in fetched HTML"},
        {"label": "User-declared canonical (Google's indexed data)", "value": user or "Not returned"},
        {"label": "Google-selected canonical", "value": google or "Not returned"},
        {"label": "Google coverage state", "value": coverage or "Not returned"},
        {"label": "Google last crawl", "value": getattr(inspection, "last_crawl_time", "") or "Not returned"},
    ]
    observations = []
    if not audit:
        observations.append("The live page audit was unavailable. No conclusion about its current canonical tag can be made.")
    elif not raw_canonical:
        observations.append("The fetched HTML contains no canonical tag. Check rendered HTML and HTTP Link headers before concluding that no canonical is declared.")
    elif live_canonical != live_url:
        observations.append("The live HTML points to a different URL. This can be intentional; verify that this target is the equivalent page you want indexed.")
    else:
        observations.append("The fetched page declares itself canonical. This is a preference, not proof that Google accepts it.")
    if user and live_canonical and user != live_canonical:
        observations.append("The live canonical differs from Google's indexed declaration. The page may have changed since the last crawl, or Google may have seen different rendered content.")
    if live_url != url:
        observations.append("The fetched final URL differs from the requested URL. Review redirects and whether they agree with the preferred canonical.")
    return {
        "id": "google_canonical_mismatch", "title": ISSUE, "status": status, "reason": reason,
        "meaning": "Google grouped this URL with duplicate or very similar content and preferred a different representative URL from the one you declared. The inspected duplicate is excluded in favor of that representative. This is not by itself a manual penalty.",
        "evidence": evidence, "observations": observations,
        "limitations": "Google does not provide a complete causal explanation. These observations are evidence, not proof of why its algorithms chose another URL. This check does not compare the full content of all duplicate pages, HTTP canonical headers, JavaScript-rendered canonicals, or every internal link and sitemap entry.",
        "possible_causes": [
            "Duplicate content: URL parameters, print versions, host/protocol variants, or pages with substantially the same main content can belong to one duplicate cluster.",
            "Conflicting signals: redirects or canonical declarations may favor one URL while sitemaps and internal links favor another. A sitemap is a weaker signal than a redirect or canonical annotation.",
            "Incorrect target: a template or SEO plugin may declare an unrelated page, a redirected URL, or a target that cannot be indexed. A canonical should identify equivalent content.",
            "Google saw a different version: recent edits, rendering differences, server errors, or shared error-page content may explain a mismatch between today's HTML and indexed data.",
            "Cross-domain or regional duplication: copied content, host misconfiguration, or near-identical regional pages can cause unexpected clustering. Investigate an unfamiliar external canonical before attributing the cause.",
        ],
        "steps": [
            "In Search Console URL Inspection, inspect this exact URL's indexed result. Compare User-declared canonical and Google-selected canonical; the live test cannot predict Google's canonical choice.",
            "Inspect both canonical candidates and compare their main content, purpose, status codes, redirects, crawl access and indexing directives. Determine which URL should represent the duplicate set.",
            "For true duplicates, align canonical tags, permanent redirects where appropriate, internal links and sitemap URLs with the preferred accessible, indexable URL. Check both HTML and HTTP Link headers for conflicting canonicals.",
            "If both pages need separate indexing, make their main content meaningfully distinct and use appropriate self-canonicals. For regional variants, review hreflang. Merely changing a title is not a reliable fix.",
            "Do not use robots.txt or noindex as a substitute for canonicalization. Blocking crawling can prevent Google from seeing the signals you changed.",
            "After changes, use Search Console Request Indexing for important affected URLs and monitor indexed inspection after recrawling. A successful live test is not confirmation that the canonical choice has changed.",
        ], "sources": SOURCES,
    }


GOOGLE_ISSUE_CHECKS = (canonical_issue,)


def add_google_issues(result, enabled=False, access_token="", service_account_json="", progress_callback=None):
    pages = result.get("pages", [])
    inspections = {}
    unavailable = "Search Console inspection was not enabled. Enable it to verify Google's indexed canonical choice."
    if enabled:
        if not (access_token or service_account_json):
            unavailable = "Search Console credentials are missing. Configure Google OAuth or a service account in Settings with access to the site's Search Console domain property."
        elif pages:
            try:
                if progress_callback:
                    progress_callback("Checking Google issues with Search Console URL Inspection...")
                response = inspect_google_index_status_by_url_domain(
                    [page["url"] for page in pages], access_token=access_token,
                    service_account_json=service_account_json,
                )
                inspections = {item.url: item for item in response.items}
                unavailable = "No inspection result was returned for this URL."
            except Exception:
                logger.exception("Google issues inspection failed")
                unavailable = "Google inspection failed. Check Search Console credentials, property access and API availability. The page audit is still available."
    result["google_issues_checked_at"] = datetime.now(timezone.utc).isoformat()
    result["check_google_issues"] = enabled
    for page in pages:
        page["google_issues"] = [check(page, inspections.get(page["url"]), unavailable) for check in GOOGLE_ISSUE_CHECKS]
